"""Explicit, guarded setting/keymap writes with prior snapshot and read-back.

The 1.3.0 setter layouts come from published-image analysis and packet tests.
Hardware getters are checked separately. Setter behavior, physical actions,
and reboot persistence remain unverified on hardware.
The read-only channel admits getters only. Macro reset is restricted to a
validated, backed-up full replacement through this write path.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .channel import request
from .config import (
    DEVICE_FIELDS,
    DIAL_ORDER,
    POINTER_FIELDS,
    SLEEP_FIELDS,
    Change,
    NapeConfig,
    desired_settings,
    plan_changes,
    validate_config,
)
from .devices import configuration_transport, hid_backend
from .firmware import CUSTOM_DPI_RANGE, RECORD_LIMIT, SCROLL_DPI_RANGE, require_firmware
from .protocol import NapeCommand, build_request, orientation_units
from .snapshot import BUTTON_ORDER, POLLING_RATES, read_snapshot_from_device


def encode_change(change: Change, *, polling_rate_for_fr_index: int | None = None) -> bytes:
    """Encode a validated setter, never a caller-supplied raw packet."""
    if change.field in DEVICE_FIELDS and any(
        value is not None for value in (change.index, change.layer, change.binding)
    ):
        raise ValueError("device settings do not accept stage/layer/binding parameters")
    if change.field in ("custom_dpi", "scroll_dpi"):
        low, high = SCROLL_DPI_RANGE if change.field == "scroll_dpi" else CUSTOM_DPI_RANGE
        if type(change.after) is not int or not low <= change.after <= high:
            raise ValueError(f"{change.field} must be an integer in {low}..{high}")
        command = (
            NapeCommand.SET_SCROLL_DPI
            if change.field == "scroll_dpi"
            else NapeCommand.SET_CUSTOM_DPI
        )
        return build_request(command, change.after & 255, change.after >> 8)
    if change.field == "dpi_stage_count":
        if type(change.after) is not int or not 1 <= change.after <= 5:
            raise ValueError("DPI stage count must be an integer in 1..5")
        return build_request(NapeCommand.SET_DPI_STAGE_COUNT, change.after)
    if change.field == "sleep":
        if not isinstance(change.after, dict) or set(change.after) != set(SLEEP_FIELDS):
            raise ValueError("sleep setter requires all three fields")
        arguments = []
        for field in SLEEP_FIELDS:
            value = change.after[field]
            if type(value) is not int or not 0 <= value <= 65535:
                raise ValueError("sleep values must be unsigned 16-bit integers")
            arguments.extend((value & 255, value >> 8))
        return build_request(NapeCommand.SET_SLEEP, *arguments)
    if change.field == "active_layer":
        if type(change.after) is not int or not 0 <= change.after < 9:
            raise ValueError("active layer must be in 0..8")
        return build_request(NapeCommand.SET_LAYER, change.after)
    if change.field == "gesture":
        values = change.after
        if not isinstance(values, dict) or set(values) != {"up", "down", "left", "right"}:
            raise ValueError("gesture setter requires all four directions")
        arguments = []
        for direction in ("up", "down", "left", "right"):
            code = values[direction]
            if type(code) is not int or not 0 <= code <= 65535:
                raise ValueError("gesture keycodes must be 16-bit integers")
            arguments.extend((code & 0xFF, code >> 8))
        return build_request(NapeCommand.SET_GESTURE, *arguments)
    if change.field == "force_gesture_scroll":
        values = change.after
        if not isinstance(values, dict) or set(values) != {"gesture", "scroll"}:
            raise ValueError("force gesture-scroll setter requires both byte fields")
        if any(type(value) is not int or not 0 <= value <= 15 for value in values.values()):
            raise ValueError("force gesture/scroll values must be in 0..15")
        return build_request(
            NapeCommand.SET_FORCE_GESTURE_SCROLL, values["gesture"], values["scroll"]
        )
    if change.field == "tap_hold":
        if type(change.layer) is not int or not 0 <= change.layer < 9:
            raise ValueError("tap-hold layer must be in 0..8")
        if change.binding not in BUTTON_ORDER:
            raise ValueError("tap-hold button is invalid")
        column = BUTTON_ORDER.index(change.binding)
        if change.after is None:
            return build_request(NapeCommand.DELETE_TAP_HOLD, change.layer, 0, column)
        values = change.after
        tap, held = values.get("tap"), values.get("held")
        if any(type(code) is not int or not 0 <= code <= 65535 for code in (tap, held)):
            raise ValueError("tap-hold actions must be 16-bit keycodes")
        return build_request(
            NapeCommand.SET_TAP_HOLD,
            change.layer,
            0,
            column,
            tap & 0xFF,
            tap >> 8,
            held & 0xFF,
            held >> 8,
        )
    if change.field == "combo":
        if type(change.index) is not int or not 0 <= change.index < RECORD_LIMIT:
            raise ValueError("combo index must be in 0..29; bulk deletion is not exposed")
        if change.after is None:
            return build_request(NapeCommand.DELETE_COMBO, change.index)
        values = change.after
        layer, columns = values.get("layer"), values.get("columns")
        timeout, tap, held = (
            values.get("timeout_ms"),
            values.get("tap"),
            values.get("held"),
        )
        if type(layer) is not int or not 0 <= layer < 9:
            raise ValueError("combo layer must be in 0..8")
        if type(columns) is not int or not 1 <= columns <= 255:
            raise ValueError("combo columns must be a non-zero byte")
        if type(timeout) is not int or not 0 <= timeout <= 65535:
            raise ValueError("combo timeout must fit in 16 bits")
        if any(type(code) is not int or not 0 <= code <= 65535 for code in (tap, held)):
            raise ValueError("combo actions must be 16-bit keycodes")
        return build_request(
            NapeCommand.SET_COMBO,
            change.index,
            timeout & 0xFF,
            timeout >> 8,
            layer,
            columns,
            tap & 0xFF,
            tap >> 8,
            held & 0xFF,
            held >> 8,
        )
    if change.field == "layer_orientation":
        if type(change.after) is not int:
            raise ValueError("layer orientation must be an integer")
        if (
            type(change.layer) is not int
            or not 0 <= change.layer < 9
            or type(change.after) is not int
        ):
            raise ValueError("invalid layer orientation target")
        return build_request(
            NapeCommand.SET_LAYER_ORIENTATION,
            change.layer,
            orientation_units(change.after),
        )
    if change.field in ("buttons", "dial"):
        if type(change.after) is not int:
            raise ValueError("keymap setter value must be an integer")
        if type(change.layer) is not int or not 0 <= change.layer < 9:
            raise ValueError("keymap layer must be in 0..8")
        names = BUTTON_ORDER if change.field == "buttons" else DIAL_ORDER
        if (
            change.binding not in names
            or change.index is not None
            or not 0 <= change.after <= 65535
        ):
            raise ValueError("invalid keymap binding, keycode, or stage index")
        command = 0x05 if change.field == "buttons" else 0x15
        return bytes(
            (
                command,
                change.layer,
                0,
                names.index(change.binding),
                change.after >> 8,
                change.after & 0xFF,
            )
        ).ljust(32, b"\x00")
    if change.layer is not None or change.binding is not None:
        raise ValueError("pointer setters do not accept layer/binding parameters")
    if change.field == "dpi_values":
        if type(change.after) is not int:
            raise ValueError("DPI setter value must be an integer")
        if type(change.index) is not int or not 0 <= change.index < 5:
            raise ValueError("DPI stage index must be in 0..4")
        if not 1 <= change.after <= 65535:
            raise ValueError("DPI value must be in 1..65535")
        return build_request(
            NapeCommand.SET_DPI_VALUE, change.index, change.after & 0xFF, change.after >> 8
        )
    if change.index is not None:
        raise ValueError("only dpi_values setters accept a stage index")
    if change.field == "dpi_index":
        if type(change.after) is not int or not 0 <= change.after < 5:
            raise ValueError("DPI index must be in 0..4")
        return build_request(NapeCommand.SET_DPI, change.after)
    if change.field == "orientation":
        if type(change.after) is not int:
            raise ValueError("orientation must be an integer")
        return build_request(NapeCommand.SET_ORIENTATION, orientation_units(change.after))
    if change.field == "polling_rate":
        if type(change.after) is not int:
            raise ValueError("polling rate must be an integer")
        if change.after not in POLLING_RATES:
            raise ValueError("unknown polling rate")
        if type(polling_rate_for_fr_index) is not int or not 0 <= polling_rate_for_fr_index <= 255:
            raise ValueError("polling setter requires the device's secondary polling-rate index")
        return bytes(
            (0xA7, 0x0E, POLLING_RATES.index(change.after), polling_rate_for_fr_index)
        ).ljust(32, b"\x00")
    raise ValueError(f"unsupported setter: {change.field}")


def _encode_macro_update(value: str) -> list[bytes]:
    """Encode a complete replacement, reserving the last byte until finalization.

    Reset is internal to a backed-up macro replacement, never a standalone reset.
    """
    data = bytes.fromhex(value)
    if not 1 <= len(data) <= 65535 or data[-1] != 0:
        raise ValueError("macro replacement needs a full 1..65535-byte buffer ending in zero")
    last = len(data) - 1

    def chunk(offset: int, content: bytes) -> bytes:
        return bytes((0x0F, offset >> 8, offset & 255, len(content), *content)).ljust(32, b"\x00")

    packets = [b"\x10".ljust(32, b"\x00"), chunk(last, b"\xff")]
    for offset in range(0, last, 28):
        packets.append(chunk(offset, data[offset : min(offset + 28, last)]))
    packets.append(chunk(last, b"\x00"))
    return packets


def _wait_macro_buffer_ack(device: Any, payload: bytes, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        reply = bytes(device.read(64, remaining_ms))
        if reply and reply[0] == 0x0F:
            if reply != payload:
                raise ValueError(
                    "macro-buffer ACK did not echo the exact chunk; stopping without retry"
                )
            return
    raise TimeoutError("macro-buffer ACK timed out")


def _wait_keymap_ack(device: Any, payload: bytes, timeout_ms: int) -> None:
    """Drain a setter ACK; encoder ACKs must also match the direction.

    The subsequent full read-back, not the ACK, establishes the target values.
    """
    command = payload[0]
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        reply = bytes(device.read(64, remaining_ms))
        if reply and reply[0] == command:
            if len(reply) != 32:
                raise ValueError("keymap setter ACK must contain 32 payload bytes")
            if command == 0x15 and reply[3] != payload[3]:
                continue
            return
    raise TimeoutError(f"keymap setter 0x{command:02X} ACK timed out")


def _wait_nape_ack(
    device: Any, command: int, timeout_ms: int, *, success_status: int | None = None
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        reply = bytes(device.read(64, remaining_ms))
        if len(reply) != 32 or reply[:2] != bytes((0xA7, command)):
            continue
        if success_status is not None and reply[2] != success_status:
            raise ValueError(f"NAPE command 0x{command:02X} returned status {reply[2]}")
        return
    raise TimeoutError(f"NAPE command 0x{command:02X} ACK timed out")


def _validate_write_target(snapshot: dict[str, Any], transport: str) -> None:
    # The receiver channel does not expose target-slot selection. Limit those
    # writes to the exact, unambiguous slot/PID observed during read tests.
    if transport == "link-km-raw-hid":
        state = bytes.fromhex(snapshot["raw"]["b2"])
        if (
            len(state) != 32
            or state[:1] != b"\xb2"
            or state[2:7] != bytes.fromhex("34 34 40 04 01")
            or state[11] != 0
            or state[16] != 0
        ):
            raise ValueError("writes require only Nape 3434:4004 connected in receiver slot 0")
    require_firmware(snapshot["firmware"])


def _save_backup(path: Path, snapshot: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as file:
        file.write(json.dumps(snapshot, indent=2) + "\n")
        file.flush()
        os.fsync(file.fileno())


def apply_config(
    device_info: dict[str, Any],
    config: NapeConfig,
    *,
    write: bool = False,
    backup: Path | None = None,
    timeout_ms: int = 1500,
    on_plan: Callable[[list[Change]], None] | None = None,
) -> dict[str, Any]:
    """Default to planning; explicit writes affect only requested changed entries.

    Partial failure is not rolled back automatically: unknown firmware behavior
    and external edits make blind rollback unsafe. The backup is retained and
    the error reports whether write attempts started.
    """
    config = validate_config(config.to_dict())
    transport = configuration_transport(device_info)
    if timeout_ms <= 0:
        raise ValueError("timeout must be positive")
    if write and backup is None:
        raise ValueError("--write requires --backup with a new snapshot path")
    if not write and backup is not None:
        raise ValueError("--backup is only used with --write")
    if backup is not None and backup.exists():
        raise FileExistsError(f"backup already exists: {backup}")

    device = hid_backend().device()
    try:
        device.open_path(device_info["path"])
        layer_orientations = any(layer.orientation is not None for layer in config.layers)
        macro_buffer = config.macro_buffer is not None or config.macros is not None
        before = read_snapshot_from_device(
            device,
            transport=transport,
            include_backup=write,
            include_keymap=write or bool(config.layers or config.tap_holds),
            include_device_settings=config.requires_device_settings,
            include_layer_orientations=layer_orientations,
            include_macro_buffer=macro_buffer,
            include_gesture=bool(config.gesture),
            include_force_gesture_scroll=bool(config.force_gesture_scroll),
            tap_hold_targets=tuple((entry.layer, entry.button) for entry in config.tap_holds),
            combo_targets=tuple(entry.index for entry in config.combos),
            timeout_ms=timeout_ms,
        )
        if write:
            _validate_write_target(before, transport)
        changes = plan_changes(config, before)
        if on_plan is not None:
            on_plan(changes)
        result: dict[str, Any] = {
            "mode": "dry-run",
            "changes": [change.to_dict() for change in changes],
        }
        if not write:
            return result
        if not changes:
            return {**result, "mode": "no-op", "backup": None}
        assert backup is not None
        expected = desired_settings(config, before)
        packets = []
        for change in changes:
            payloads = (
                _encode_macro_update(change.after)
                if change.field == "macro_buffer"
                else [
                    encode_change(
                        change,
                        polling_rate_for_fr_index=before["polling_rate_for_fr_index"],
                    )
                ]
            )
            packets.extend(b"\x00" + payload for payload in payloads)
        # Save and flush the complete supported snapshot before attempting a setter.
        _save_backup(backup, before)
        attempts = 0
        try:
            for packet in packets:
                if packet[1:3] == b"\xa7\x3d":
                    # A zero status does not prove acceptance; check before shrinking.
                    current_index = request(device, b"\xa7\x21", timeout_ms)[2]
                    if current_index >= packet[3]:
                        raise ValueError(
                            "active DPI stage would be disabled; stopping before count setter"
                        )
                attempts += 1
                if device.write(packet) != len(packet):
                    raise OSError("incomplete HID setter write")
                if packet[1] in (0x05, 0x15, 0x10):
                    _wait_keymap_ack(device, packet[1:], timeout_ms)
                elif packet[1] == 0x0F:
                    _wait_macro_buffer_ack(device, packet[1:], timeout_ms)
                elif packet[1] == 0xA7:
                    subcommand = packet[2]
                    if subcommand != 0x0E:
                        _wait_nape_ack(device, subcommand, timeout_ms, success_status=0)
                    if subcommand == 0x3D:
                        # Do not select a newly enabled stage if firmware rejected the growth.
                        time.sleep(0.05)
                        reply = request(device, b"\xa7\x3c", timeout_ms)
                        if reply[2] != packet[3]:
                            raise ValueError(
                                "DPI stage count did not change; stopping before next setter"
                            )
                time.sleep(0.05)
            # Neither zero-status ACKs nor immediate read-back prove persistence.
            time.sleep(0.2)
            after = read_snapshot_from_device(
                device, transport=transport, include_backup=True, timeout_ms=timeout_ms
            )
            _validate_write_target(after, transport)
            verified_fields = (
                *POINTER_FIELDS,
                "polling_rate_for_fr_index",
                "layers",
                "active_layer",
                "gesture",
                "force_gesture_scroll",
                "tap_holds",
                "combos",
                *DEVICE_FIELDS,
                "macro_buffer",
                "default_layer",
            )
            mismatches = [field for field in verified_fields if after[field] != expected[field]]
            if mismatches:
                raise ValueError(f"read-back mismatch: {', '.join(mismatches)}")
        except (OSError, RuntimeError, ValueError, KeyboardInterrupt) as exc:
            raise RuntimeError(
                f"apply failed after {attempts}/{len(packets)} write attempts: {exc}. "
                f"Device may be partially changed; backup: {backup}. No automatic rollback."
            ) from exc
        return {**result, "mode": "applied", "backup": str(backup), "verified": True}
    finally:
        device.close()
