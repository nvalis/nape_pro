"""Command-line interface for Nape HID discovery and protocol exploration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .apply import apply_config
from .config import Change, load_config, plan_changes
from .devices import LINK_KM_PRODUCT_ID, RAW_USAGE_PAGE, enumerate_devices, path_text
from .protocol import NapeCommand, build_request, orientation_units
from .receiver import receiver_info
from .snapshot import read_snapshot
from .transport import probe


def _int_value(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer (decimal or 0x-prefixed)") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nape", description="Explore and configure Keychron Nape devices"
    )
    parser.add_argument("--version", action="version", version=f"nape {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    devices_parser = commands.add_parser("devices", help="list matching Keychron HID interfaces")
    devices_parser.add_argument(
        "--all", action="store_true", help="show all interfaces with Keychron VID 0x3434"
    )
    devices_parser.add_argument(
        "--json", action="store_true", help="print machine-readable device details"
    )

    protocol_parser = commands.add_parser(
        "protocol", help="show a candidate protocol packet without sending it"
    )
    protocol_parser.add_argument(
        "operation", choices=("get-orientation", "get-dpi", "set-orientation")
    )
    protocol_parser.add_argument(
        "--angle", type=int, help="orientation angle for set-orientation (0..315 in 45° steps)"
    )

    probe_parser = commands.add_parser(
        "probe", help="send a read-only protocol probe and show raw response bytes"
    )
    probe_parser.add_argument(
        "--index", type=int, required=True, help="interface index from `nape devices`"
    )
    probe_parser.add_argument(
        "--command", dest="probe_command", choices=("orientation", "dpi"), default="orientation"
    )
    probe_parser.add_argument(
        "--report-id", type=_int_value, default=0, help="HID report ID (default: 0)"
    )
    probe_parser.add_argument("--timeout-ms", type=int, default=1000)

    receiver_parser = commands.add_parser(
        "receiver-info", help="read Link-KM receiver version and paired-device state"
    )
    receiver_parser.add_argument("--index", type=int, help="collection index from `nape devices`")
    receiver_parser.add_argument("--timeout-ms", type=int, default=1500)
    receiver_parser.add_argument("--json", action="store_true", help="include raw reply packets")
    status_parser = commands.add_parser("status", help="read Nape pointer settings and battery")
    status_parser.add_argument("--json", action="store_true", help="include raw reply packets")
    export_parser = commands.add_parser(
        "export", help="save pointer settings and all nine keymap layers"
    )
    export_parser.add_argument(
        "output", type=Path, help="new JSON snapshot file (never overwritten)"
    )
    export_parser.add_argument(
        "--advanced",
        action="store_true",
        help="also read per-layer orientation and the VIA macro buffer (experimental)",
    )
    validate_parser = commands.add_parser(
        "validate", help="validate a partial pointer/keymap JSON config offline"
    )
    validate_parser.add_argument("config", type=Path)
    validate_parser.add_argument(
        "--json", action="store_true", help="print normalized configuration"
    )
    plan_parser = commands.add_parser(
        "plan", help="preview configuration changes without writing settings"
    )
    plan_parser.add_argument("config", type=Path)
    plan_parser.add_argument("--json", action="store_true", help="print a machine-readable diff")
    apply_parser = commands.add_parser(
        "apply", help="preview configuration changes; writes require --write and --backup"
    )
    apply_parser.add_argument("config", type=Path)
    apply_parser.add_argument("--json", action="store_true", help="print the result as JSON")
    apply_mode = apply_parser.add_mutually_exclusive_group()
    apply_mode.add_argument(
        "--write", action="store_true", help="explicitly authorize settings writes"
    )
    apply_mode.add_argument("--dry-run", action="store_true", help="preview only (the default)")
    apply_parser.add_argument(
        "--backup", type=Path, help="new pre-write snapshot file; required for --write"
    )
    for subparser in (status_parser, export_parser, plan_parser, apply_parser):
        subparser.add_argument("--index", type=int, help="receiver Raw HID collection index")
        subparser.add_argument("--timeout-ms", type=int, default=1500)
    return parser


def _device_record(device: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "vendor_id": device.get("vendor_id"),
        "product_id": device.get("product_id"),
        "product_string": device.get("product_string"),
        "manufacturer_string": device.get("manufacturer_string"),
        "usage_page": device.get("usage_page"),
        "usage": device.get("usage"),
        "interface_number": device.get("interface_number"),
        "path": path_text(device.get("path", "")),
    }


def _select_receiver(index: int | None) -> dict[str, Any]:
    devices = enumerate_devices()
    if index is not None:
        if not 0 <= index < len(devices):
            raise ValueError("device index is out of range; run `nape devices` first")
        return devices[index]
    candidates = [
        device
        for device in devices
        if device.get("product_id") == LINK_KM_PRODUCT_ID
        and device.get("usage_page") == RAW_USAGE_PAGE
        and device.get("usage") == 0x61
    ]
    if len(candidates) != 1:
        raise ValueError("expected one Link-KM Raw HID collection; use --index to select")
    return candidates[0]


def _run(args: argparse.Namespace) -> int:
    if args.command == "devices":
        devices = enumerate_devices(all_collections=args.all)
        records = [_device_record(device, index) for index, device in enumerate(devices)]
        if args.json:
            print(json.dumps(records, indent=2))
        elif not records:
            print(
                "No matching HID interfaces found. Check USB connection and host HID visibility "
                "(WSL may require USB passthrough)."
            )
        else:
            for record in records:
                print(
                    f"[{record['index']}] {record['product_string'] or '(unnamed)'} "
                    f"VID:PID={record['vendor_id']:04X}:{record['product_id']:04X} "
                    f"usage_page={record['usage_page']:#06x} usage={record['usage']:#04x} "
                    f"interface={record['interface_number']}\n    path={record['path']}"
                )
        return 0

    if args.command == "apply":
        config = load_config(args.config)
        # Reject missing/irrelevant backup flags before selecting any hardware.
        if args.write and args.backup is None:
            raise ValueError("--write requires --backup with a new snapshot path")
        if not args.write and args.backup is not None:
            raise ValueError("--backup is only used with --write")
        if args.backup is not None and args.backup.exists():
            raise FileExistsError(f"backup already exists: {args.backup}")

        def show_plan(changes: list[Change]) -> None:
            output = sys.stderr if args.json else sys.stdout
            mode = "Experimental write requested" if args.write else "Dry-run: no settings written"
            print(mode + ".", file=output, flush=True)
            for change in changes:
                entry = change.to_dict()
                print(
                    f"{entry['setting']}: {entry['before']} -> {entry['after']}",
                    file=output,
                    flush=True,
                )
            if args.write and changes:
                print(f"Pre-write snapshot path: {args.backup}", file=output, flush=True)
            if not changes:
                print("No changes needed.", file=output, flush=True)

        result = apply_config(
            _select_receiver(args.index),
            config,
            write=args.write,
            backup=args.backup,
            timeout_ms=args.timeout_ms,
            on_plan=show_plan,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        elif result["mode"] == "applied":
            print(f"Applied and read-back verified. Snapshot: {result['backup']}")
        return 0

    if args.command in ("validate", "plan"):
        config = load_config(args.config)
        if args.command == "validate":
            print(json.dumps(config.to_dict(), indent=2) if args.json else "Configuration valid.")
            return 0
        current = read_snapshot(
            _select_receiver(args.index),
            include_keymap=bool(config.layers),
            include_layer_orientations=any(
                layer.orientation is not None for layer in config.layers
            ),
            include_macro_buffer=config.macro_buffer is not None,
            timeout_ms=args.timeout_ms,
        )
        changes = plan_changes(config, current)
        if args.json:
            print(
                json.dumps({"mode": "dry-run", "changes": [c.to_dict() for c in changes]}, indent=2)
            )
        else:
            print("Dry-run: no settings written.")
            for change in changes:
                entry = change.to_dict()
                print(f"{entry['setting']}: {entry['before']} -> {entry['after']}")
            if not changes:
                print("No changes needed.")
        return 0

    if args.command == "protocol":
        if args.operation == "set-orientation":
            if args.angle is None:
                raise ValueError("--angle is required for set-orientation")
            units = orientation_units(args.angle)
            request = build_request(NapeCommand.SET_ORIENTATION, units)
        else:
            command = {
                "get-orientation": NapeCommand.GET_ORIENTATION,
                "get-dpi": NapeCommand.GET_DPI,
            }[args.operation]
            request = build_request(command)
        print("Candidate 32-byte payload (not sent; Nape Pro framing is unverified):")
        print(request.hex(" "))
        return 0

    if args.command in ("status", "export"):
        if args.command == "export" and args.output.exists():
            raise FileExistsError(f"snapshot already exists: {args.output}")
        result = read_snapshot(
            _select_receiver(args.index),
            include_keymap=args.command == "export",
            include_layer_orientations=args.command == "export" and args.advanced,
            include_macro_buffer=args.command == "export" and args.advanced,
            timeout_ms=args.timeout_ms,
        )
        if args.command == "export":
            with args.output.open("x", encoding="utf-8") as output:
                output.write(json.dumps(result, indent=2) + "\n")
            scope = "pointer settings and "
            scope += f"{result['layer_count']} layers"
            if args.advanced:
                scope += ", per-layer orientation, and macro buffer"
            print(f"Saved {scope} to {args.output}")
        elif args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Firmware: {result['firmware']}")
            print(f"Battery: {result['battery_percent']}% (charging: {result['charging']})")
            print(f"Layer: {result['active_layer']} (zero-based; {result['layer_count']} layers)")
            print(f"Orientation: {result['orientation']}°")
            print(f"DPI: {result['dpi']} (stage {result['dpi_index']}, zero-based)")
            print(f"DPI stages: {', '.join(map(str, result['dpi_values']))}")
            print(f"Polling rate: {result['polling_rate']} Hz")
        return 0

    if args.command == "receiver-info":
        result = receiver_info(_select_receiver(args.index), timeout_ms=args.timeout_ms)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Receiver protocol: {result['protocol_version']}")
            print(f"Firmware: {result['firmware']}")
            for slot in result["slots"]:
                if slot["vendor_id"] or slot["product_id"]:
                    status = "connected" if slot["connected"] else f"status={slot['status']}"
                    print(
                        f"Slot {slot['slot']}: {slot['vendor_id']:04X}:{slot['product_id']:04X} "
                        f"({status})"
                    )
        return 0

    if args.command == "probe":
        if args.index < 0:
            raise ValueError("--index must be non-negative")
        if args.timeout_ms <= 0:
            raise ValueError("--timeout-ms must be positive")
        devices = enumerate_devices()
        if args.index >= len(devices):
            raise ValueError(f"device index {args.index} is out of range; run `nape devices` first")
        selected = _device_record(devices[args.index], args.index)
        print(
            "Experimental read-only probe: this uses an unverified 32-byte HID envelope; "
            "a timeout does not necessarily mean the device is incompatible."
        )
        response = probe(
            devices[args.index],
            args.probe_command,
            report_id=args.report_id,
            timeout_ms=args.timeout_ms,
        )
        device_name = selected["product_string"] or "(unnamed)"
        device_id = f"{selected['vendor_id']:04X}:{selected['product_id']:04X}"
        print(f"device: {device_name} ({device_id})")
        response_text = response.hex(" ") if response else "<no response>"
        print(f"response ({len(response)} bytes): {response_text}")
        return 0

    raise AssertionError(f"unhandled command {args.command}")


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        exit_code = _run(args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"nape: error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
