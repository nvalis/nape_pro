"""Known NAPE command IDs and a conservative candidate request encoder.

The command IDs come from the reverse-engineered Keychron Launcher protocol
notes linked in README.md. Reads through the Link-KM Raw HID collection have
been verified on-device, as has active DPI-stage selection/restoration. Direct
USB framing and other pointer setters remain unverified.
"""

from __future__ import annotations

from enum import IntEnum

REPORT_SIZE = 32
KC_MISC_CMD_GROUP = 0xA7


class NapeCommand(IntEnum):
    GET_ORIENTATION = 0x20
    GET_DPI = 0x21
    SET_DPI = 0x22
    SET_DPI_VALUE = 0x23
    GET_DPI_VALUE = 0x24
    GET_PROFILE = 0x2C
    SET_ORIENTATION = 0x34
    GET_LAYER_ORIENTATION = 0x38
    SET_LAYER_ORIENTATION = 0x39


def build_request(command: NapeCommand, *arguments: int) -> bytes:
    """Build a zero-padded 32-byte candidate request (not a HID report ID)."""
    if len(arguments) > REPORT_SIZE - 2:
        raise ValueError(f"at most {REPORT_SIZE - 2} argument bytes are allowed")
    if any(not 0 <= value <= 0xFF for value in arguments):
        raise ValueError("command arguments must be bytes (0..255)")

    return bytes((KC_MISC_CMD_GROUP, command, *arguments)).ljust(REPORT_SIZE, b"\x00")


def orientation_units(degrees: int) -> int:
    """Convert a supported orientation angle to the wire's 45-degree units."""
    if degrees not in range(0, 360, 45):
        raise ValueError("orientation must be one of 0, 45, 90, 135, 180, 225, 270, 315")
    return degrees // 45
