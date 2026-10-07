"""Serialized, read-only requests on the Link-KM Raw HID channel."""

from __future__ import annotations

import time
from typing import Any

READ_COMMANDS = {0x01, 0x0C, 0x0D, 0x0E, 0x11, 0x12, 0x14, 0xA0, 0xA1, 0xA3, 0xB1, 0xB2, 0xB3}
MISC_READ_COMMANDS = {0x0B, 0x0D, 0x20, 0x21, 0x24, 0x26, 0x28, 0x2A, 0x31, 0x33, 0x36, 0x38, 0x3C}


def request(device: Any, payload: bytes, timeout_ms: int = 1500) -> bytes:
    """Send a permitted read request and skip notifications/unrelated replies.

    No transaction IDs exist on this channel. Callers must issue requests
    sequentially and stop on timeout, rather than immediately retrying a request
    with the same command whose late reply could be mistaken for a new reply.
    """
    if not payload or len(payload) > 32:
        raise ValueError("request must contain 1..32 bytes")
    if timeout_ms <= 0:
        raise ValueError("timeout must be positive")
    command = payload[0]
    if command == 0xA7:
        if len(payload) < 2 or payload[1] not in MISC_READ_COMMANDS:
            raise ValueError("misc command is not in the read-only allowlist")
        prefix = payload[:2]
        if payload[1] == 0x26:
            if (
                len(payload) != 5
                or not 0 <= payload[2] < 9
                or payload[3] != 0
                or not 0 <= payload[4] < 7
            ):
                raise ValueError("tap-hold read requires layer 0..8, row 0, and column 0..6")
        elif payload[1] == 0x28:
            if len(payload) != 3:
                raise ValueError("combo read requires one combo index")
        elif payload[1] in (0x0B, 0x2A, 0x33, 0x36, 0x3C) and len(payload) != 2:
            raise ValueError("settings query takes no arguments")
        elif payload[1] == 0x38 and (len(payload) != 3 or not 0 <= payload[2] < 9):
            raise ValueError("per-layer orientation read requires a layer index in 0..8")
    elif command in READ_COMMANDS:
        if command in (0x0C, 0x0D, 0x01) and len(payload) != 1:
            raise ValueError("macro/protocol version query takes no arguments")
        prefix = payload[:1]
    else:
        raise ValueError("command is not in the read-only allowlist")
    if command in (0x12, 0x14):
        if len(payload) != 4:
            raise ValueError("keymap/encoder read requires four request bytes")
        prefix = payload
    elif command == 0x0E:
        if (
            len(payload) != 4
            or not 1 <= payload[3] <= 28
            or int.from_bytes(payload[1:3], "big") + payload[3] > 65536
        ):
            raise ValueError("macro-buffer read requires a valid offset and size in 1..28")
        prefix = payload[:3]

    packet = b"\x00" + payload.ljust(32, b"\x00")
    if device.write(packet) != len(packet):
        raise OSError("incomplete HID request write")
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        response = bytes(device.read(64, remaining_ms))
        if not response.startswith(prefix):
            continue
        if len(response) != 32:
            raise ValueError(f"expected 32 response bytes, got {len(response)}")
        if command == 0xA7 and payload[1] == 0x26:
            if response[2] != payload[2] or response[4] != payload[4]:
                continue
        elif command == 0xA7 and payload[1] == 0x28:
            if response[2] != payload[2]:
                continue
        return response
    raise TimeoutError(f"read request {payload.hex(' ')} timed out")
