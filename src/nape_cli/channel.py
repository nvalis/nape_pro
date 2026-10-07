"""Serialized, read-only requests on the Link-KM Raw HID channel."""

from __future__ import annotations

import time
from typing import Any

READ_COMMANDS = {0x01, 0x11, 0x12, 0x14, 0xA0, 0xA1, 0xA3, 0xB1, 0xB2, 0xB3}
MISC_READ_COMMANDS = {0x0D, 0x20, 0x21, 0x24, 0x31}


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
    elif command in READ_COMMANDS:
        prefix = payload[:1]
    else:
        raise ValueError("command is not in the read-only allowlist")
    if command in (0x12, 0x14):
        if len(payload) != 4:
            raise ValueError("keymap/encoder read requires four request bytes")
        prefix = payload

    packet = b"\x00" + payload.ljust(32, b"\x00")
    if device.write(packet) != len(packet):
        raise OSError("incomplete HID request write")
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        response = bytes(device.read(64, remaining_ms))
        if response.startswith(prefix):
            if len(response) != 32:
                raise ValueError(f"expected 32 response bytes, got {len(response)}")
            return response
    raise TimeoutError(f"read request {payload.hex(' ')} timed out")
