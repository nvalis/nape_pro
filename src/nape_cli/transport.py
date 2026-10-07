"""Small hidapi adapter for explicitly read-only protocol probes."""

from __future__ import annotations

from typing import Any

from .devices import LINK_KM_PRODUCT_ID, NAPE_4K_USAGE_PAGE, NAPE_USAGE_PAGE, hid_backend
from .protocol import NapeCommand, build_request

READ_ONLY_COMMANDS = {
    "orientation": NapeCommand.GET_ORIENTATION,
    "dpi": NapeCommand.GET_DPI,
}


def probe(
    device_info: dict[str, Any], command_name: str, *, report_id: int, timeout_ms: int
) -> bytes:
    """Send one documented read command and return its raw HID response bytes.

    This intentionally exposes the raw reply: response layouts and the correct
    Nape Pro HID report envelope still need confirmation on-device.
    """
    if command_name not in READ_ONLY_COMMANDS:
        raise ValueError(f"unsupported read-only probe: {command_name}")
    if device_info.get("product_id") == LINK_KM_PRODUCT_ID or device_info.get("usage_page") not in (
        NAPE_USAGE_PAGE,
        NAPE_4K_USAGE_PAGE,
    ):
        raise ValueError(
            "this interface is not identified as a direct mouse collection; "
            "receiver tunneling is not implemented yet"
        )
    if not 0 <= report_id <= 0xFF:
        raise ValueError("report ID must be in the range 0..255")

    device = hid_backend().device()
    try:
        device.open_path(device_info["path"])
        # hidapi expects the report ID as byte zero. The 32-byte payload is a
        # candidate envelope from the Launcher's reverse-engineered command map.
        packet = build_request(READ_ONLY_COMMANDS[command_name])
        device.write(bytes((report_id,)) + packet)
        return bytes(device.read(64, timeout_ms))
    finally:
        device.close()
