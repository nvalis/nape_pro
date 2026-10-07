"""Read-only Link-KM queries verified on receiver 3434:D026.

This uses its unnumbered 32-byte Raw HID collection (FF60:61), not the
numbered B1/B2 bridge collection on the other interface. No paired-device
commands or settings writes are implemented here.
"""

from __future__ import annotations

from typing import Any

from .channel import request
from .devices import KEYCHRON_VENDOR_ID, LINK_KM_PRODUCT_ID, RAW_USAGE_PAGE, hid_backend


def query(device: Any, command: int, timeout_ms: int) -> bytes:
    """Wait for the requested response, skipping unsolicited state notifications."""
    return request(device, bytes((command,)), timeout_ms)


def parse_receiver_replies(version: bytes, state: bytes, firmware: bytes) -> dict[str, Any]:
    """Decode documented slot fields; preserve raw packets for verification."""
    for command, reply in ((0xB1, version), (0xB2, state), (0xB3, firmware)):
        if len(reply) != 32 or reply[0] != command:
            raise ValueError(f"invalid receiver response for 0x{command:02X}")
    slots = []
    for index, offset in enumerate((2, 7, 12)):
        vid = int.from_bytes(state[offset : offset + 2], "big")
        pid = int.from_bytes(state[offset + 2 : offset + 4], "big")
        status = state[offset + 4]
        slots.append(
            {
                "slot": index,
                "vendor_id": vid,
                "product_id": pid,
                "status": status,
                "connected": status == 1,
            }
        )
    return {
        "protocol_version": int.from_bytes(version[1:3], "little"),
        "feature_bytes": version[3:5].hex(" "),
        "firmware": firmware[1:].split(b"\x00", 1)[0].decode("ascii", errors="replace"),
        "slots": slots,
        "raw": {
            "version": version.hex(" "),
            "state": state.hex(" "),
            "firmware": firmware.hex(" "),
        },
    }


def validate_receiver(device_info: dict[str, Any]) -> None:
    """Restrict traffic to the hardware/collection tested on-device."""
    if (
        device_info.get("vendor_id") != KEYCHRON_VENDOR_ID
        or device_info.get("product_id") != LINK_KM_PRODUCT_ID
        or device_info.get("usage_page") != RAW_USAGE_PAGE
        or device_info.get("usage") != 0x61
    ):
        raise ValueError("requires the Link-KM 3434:D026 Raw HID collection FF60:61")


def receiver_info(device_info: dict[str, Any], *, timeout_ms: int = 1500) -> dict[str, Any]:
    """Query only the tested receiver PID and Raw HID collection."""
    validate_receiver(device_info)
    if timeout_ms <= 0:
        raise ValueError("timeout must be positive")
    device = hid_backend().device()
    try:
        device.open_path(device_info["path"])
        version = query(device, 0xB1, timeout_ms)
        state = query(device, 0xB2, timeout_ms)
        firmware = query(device, 0xB3, timeout_ms)
        return parse_receiver_replies(version, state, firmware)
    finally:
        device.close()
