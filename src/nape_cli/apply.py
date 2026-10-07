"""Explicit, experimental pointer writes with prior snapshot and read-back.

Setter layouts are from NapeBar; active DPI-stage selection/restoration has
passed a hardware test. Other setters remain unverified on-device.
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
    POINTER_FIELDS,
    Change,
    PointerConfig,
    desired_settings,
    plan_changes,
    validate_config,
)
from .devices import hid_backend
from .protocol import NapeCommand, build_request, orientation_units
from .receiver import validate_receiver
from .snapshot import POLLING_RATES, read_snapshot_from_device


def encode_change(change: Change) -> bytes:
    """Encode only a validated pointer setter, never a caller-supplied raw packet."""
    if type(change.after) is not int:
        raise ValueError("setter value must be an integer")
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


def apply_pointer_config(
    device_info: dict[str, Any],
    config: PointerConfig,
    *,
    write: bool = False,
    backup: Path | None = None,
    timeout_ms: int = 1500,
    on_plan: Callable[[list[Change]], None] | None = None,
) -> dict[str, Any]:
    """Default to planning; explicit writes affect only changed pointer fields.

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
        before = read_snapshot_from_device(device, include_keymap=write, timeout_ms=timeout_ms)
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
        packets = [b"\x00" + encode_change(change) for change in changes]
        # Save and flush the complete supported snapshot before attempting a setter.
        _save_backup(backup, before)
        attempts = 0
        try:
            for packet in packets:
                attempts += 1
                if device.write(packet) != len(packet):
                    raise OSError("incomplete HID setter write")
                time.sleep(0.05)
            # The source implementation uses fire-and-forget pointer setters.
            # A successful HID write is not proof of acceptance or persistence.
            time.sleep(0.2)
            after = read_snapshot_from_device(device, include_keymap=True, timeout_ms=timeout_ms)
            _validate_write_target(after)
            mismatches = [field for field in POINTER_FIELDS if after[field] != expected[field]]
            if after["layers"] != before["layers"]:
                mismatches.append("layers (not intentionally modified)")
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
