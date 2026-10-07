"""Explicit, guarded setting/keymap writes with prior snapshot and read-back.

Most setter layouts are source-based; active DPI-stage selection/restoration
has passed a hardware test. Advanced and other setters remain unverified.
The existing read-only channel allowlist remains unchanged.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import (
    DIAL_ORDER,
    POINTER_FIELDS,
    Change,
    NapeConfig,
    desired_settings,
    plan_changes,
    validate_config,
)
from .devices import hid_backend
from .protocol import NapeCommand, build_request, orientation_units
from .receiver import validate_receiver
from .snapshot import BUTTON_ORDER, POLLING_RATES, read_snapshot_from_device


def encode_change(change: Change) -> bytes:
    """Encode a validated setter, never a caller-supplied raw packet."""
    if type(change.after) is not int:
        raise ValueError("setter value must be an integer")
    if change.field == "layer_orientation":
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
        if not 0 <= change.after < 5:
            raise ValueError("DPI index must be in 0..4")
        return build_request(NapeCommand.SET_DPI, change.after)
    if change.field == "orientation":
        return build_request(NapeCommand.SET_ORIENTATION, orientation_units(change.after))
    if change.field == "polling_rate":
        if change.after not in POLLING_RATES:
            raise ValueError("unknown polling rate")
        return bytes((0xA7, 0x0E, POLLING_RATES.index(change.after))).ljust(32, b"\x00")
    raise ValueError(f"unsupported setter: {change.field}")


def _encode_macro_buffer(value: str) -> list[bytes]:
    data = bytes.fromhex(value)
    if len(data) > 65535:
        raise ValueError("macro buffer exceeds the 16-bit VIA offset range")
    packets = []
    for offset in range(0, len(data), 28):
        chunk = data[offset : offset + 28]
        packets.append(
            bytes((0x0F, offset >> 8, offset & 0xFF, len(chunk), *chunk)).ljust(32, b"\x00")
        )
    return packets


def _encode_change_packets(change: Change) -> list[bytes]:
    if change.field == "macro_buffer":
        return _encode_macro_buffer(change.after)
    return [encode_change(change)]


def _wait_keymap_ack(device: Any, command: int, timeout_ms: int) -> None:
    """Drain a serialized keymap setter ACK before sending the next entry.

    As in the source implementation, ACK matching uses the setter command.
    The subsequent full read-back, not the ACK, establishes the target values.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        reply = bytes(device.read(64, remaining_ms))
        if reply and reply[0] == command:
            if len(reply) != 32:
                raise ValueError("keymap setter ACK must contain 32 payload bytes")
            return
    raise TimeoutError(f"keymap setter 0x{command:02X} ACK timed out")


def _validate_write_target(snapshot: dict[str, Any]) -> None:
    # The unnumbered channel does not expose target-slot selection. Limit writes
    # to the exact, unambiguous slot/PID and firmware observed during read tests.
    state = bytes.fromhex(snapshot["raw"]["b2"])
    if (
        len(state) != 32
        or state[:1] != b"\xb2"
        or state[2:7] != bytes.fromhex("34 34 40 04 01")
        or state[11] != 0
        or state[16] != 0
    ):
        raise ValueError("writes require only Nape 3434:4004 connected in receiver slot 0")
    if snapshot["firmware"].split(" ", 1)[0] != "v1.1.6-ZK":
        raise ValueError("writes are restricted to the read-tested Nape firmware v1.1.6-ZK")


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
    validate_receiver(device_info)
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
        before = read_snapshot_from_device(
            device,
            include_keymap=write or bool(config.layers),
            include_layer_orientations=layer_orientations,
            include_macro_buffer=config.macro_buffer is not None,
            timeout_ms=timeout_ms,
        )
        if write:
            _validate_write_target(before)
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
        packets = [
            b"\x00" + packet for change in changes for packet in _encode_change_packets(change)
        ]
        # Save and flush the complete supported snapshot before attempting a setter.
        _save_backup(backup, before)
        attempts = 0
        try:
            for packet in packets:
                attempts += 1
                if device.write(packet) != len(packet):
                    raise OSError("incomplete HID setter write")
                if packet[1] in (0x05, 0x15):
                    _wait_keymap_ack(device, packet[1], timeout_ms)
                time.sleep(0.05)
            # Pointer/orientation/macro setters are fire-and-forget; keymap setters wait
            # for ACKs. Neither writes nor ACKs prove acceptance or persistence.
            time.sleep(0.2)
            after = read_snapshot_from_device(
                device,
                include_keymap=True,
                include_layer_orientations=layer_orientations,
                include_macro_buffer=config.macro_buffer is not None,
                timeout_ms=timeout_ms,
            )
            _validate_write_target(after)
            mismatches = [field for field in POINTER_FIELDS if after[field] != expected[field]]
            if after["layers"] != expected["layers"]:
                mismatches.append("layers")
            if (
                config.macro_buffer is not None
                and after["macro_buffer"] != expected["macro_buffer"]
            ):
                mismatches.append("macro_buffer")
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
