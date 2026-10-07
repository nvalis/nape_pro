"""HID device discovery, kept importable without the optional hidapi package."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Any

KEYCHRON_VENDOR_ID = 0x3434
NAPE_USAGE_PAGE = 0xFFC1
NAPE_4K_USAGE_PAGE = 0xFF0A
BRIDGE_USAGE_PAGE = 0x008C
RAW_USAGE_PAGE = 0xFF60
LINK_KM_PRODUCT_ID = 0xD026


def hid_backend() -> Any:
    """Use hidraw on Linux to preserve collection metadata and kernel drivers."""
    if sys.platform == "linux":
        try:
            return import_module("hidraw")
        except ImportError:
            pass
    try:
        return import_module("hid")
    except ImportError as exc:
        raise RuntimeError(
            "HID support is not installed; install with `uv sync --extra hardware`."
        ) from exc


def enumerate_devices(
    *, vendor_id: int = KEYCHRON_VENDOR_ID, all_collections: bool = False
) -> list[dict[str, Any]]:
    """Return Keychron HID interfaces, favoring known mouse/trackball collections."""
    devices = hid_backend().enumerate(vendor_id, 0)
    if all_collections:
        return devices

    recognized = [
        device
        for device in devices
        if device.get("usage_page") in (NAPE_USAGE_PAGE, NAPE_4K_USAGE_PAGE, BRIDGE_USAGE_PAGE)
        or (
            device.get("product_id") == LINK_KM_PRODUCT_ID
            and device.get("usage_page") == RAW_USAGE_PAGE
            and device.get("usage") == 0x61
        )
    ]
    if recognized:
        return recognized

    # The Linux libusb backend may omit top-level usage metadata entirely.
    # In that case, preserve Keychron interfaces for inspection rather than
    # hiding a receiver/mouse that hidapi cannot classify.
    if devices and all(not device.get("usage_page") for device in devices):
        return devices
    return []


def path_text(path: Any) -> str:
    """Format hidapi's bytes-or-string device path for display and CLI arguments."""
    if isinstance(path, bytes):
        return path.decode(errors="replace")
    return str(path)
