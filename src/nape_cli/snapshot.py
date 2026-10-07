"""Read Nape pointer settings and the nine-layer dynamic keymap via Link-KM.

Wire layouts were cross-checked against ky0209/NapeBar's protocol code and
read replies from Nape firmware v1.1.6-ZK. No write commands are issued.
"""

from __future__ import annotations

from typing import Any

from .channel import request
from .devices import hid_backend
from .receiver import validate_receiver

BUTTON_ORDER = ("03", "04", "01", "02", "M1", "M2", "Press")
POLLING_RATES = (8000, 4000, 2000, 1000, 500, 250, 125)


def read_snapshot(
    device_info: dict[str, Any], *, include_keymap: bool = False, timeout_ms: int = 1500
) -> dict[str, Any]:
    """Read supported settings; retain all replies to make decoding auditable."""
    validate_receiver(device_info)
    raw: dict[str, str] = {}
    device = hid_backend().device()

    def read(*values: int) -> bytes:
        payload = bytes(values)
        reply = request(device, payload, timeout_ms)
        raw[payload.hex(" ")] = reply.hex(" ")
        return reply

    try:
        device.open_path(device_info["path"])
        state = read(0xB2)
        if not any(state[offset] == 1 for offset in (6, 11, 16)):
            raise RuntimeError("no paired device is awake; wake the Nape in 2.4 GHz mode")
        firmware = read(0xA1)[1:].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        layer_count = read(0x11)[1]
        if layer_count != 9:
            raise ValueError(f"expected the tested Nape's 9 layers, got {layer_count}")
        active_layer = read(0xA3)[1]
        if not 1 <= active_layer <= layer_count:
            raise ValueError(f"unexpected active layer wire value: {active_layer}")
        orientation = read(0xA7, 0x20)[2]
        if orientation > 7:
            raise ValueError(f"invalid orientation units: {orientation}")
        dpi_index = read(0xA7, 0x21)[2]
        if dpi_index >= 5:
            raise ValueError(f"invalid DPI stage index: {dpi_index}")
        dpi_values = [int.from_bytes(read(0xA7, 0x24, i)[2:4], "little") for i in range(5)]
        battery = read(0xA7, 0x31)
        if battery[2] > 100:
            raise ValueError("invalid battery percentage")
        poll = read(0xA7, 0x0D)
        if poll[6] >= len(POLLING_RATES):
            raise ValueError("unexpected polling-rate index")
        result: dict[str, Any] = {
            "schema_version": 1,
            "transport": "link-km-raw-hid",
            "firmware": firmware,
            "layer_count": layer_count,
            "active_layer": active_layer - 1,
            "orientation": orientation * 45,
            "dpi_index": dpi_index,
            "dpi_values": dpi_values,
            "dpi": dpi_values[dpi_index],
            "battery_percent": battery[2],
            "charging": bool(battery[3]),
            "polling_rate": POLLING_RATES[poll[6]],
            "supported_polling_rates": [
                rate for bit, rate in enumerate(POLLING_RATES) if poll[5] & (1 << bit)
            ],
        }
        if include_keymap:
            layers = []
            for layer in range(layer_count):
                offset = layer * 14
                keys = read(0x12, offset >> 8, offset & 0xFF, 14)
                buttons = {
                    name: f"0x{int.from_bytes(keys[4 + i * 2 : 6 + i * 2], 'big'):04X}"
                    for i, name in enumerate(BUTTON_ORDER)
                }
                encoder = {}
                for direction, name in enumerate(("ccw", "cw")):
                    reply = read(0x14, layer, 0, direction)
                    encoder[name] = f"0x{int.from_bytes(reply[4:6], 'big'):04X}"
                layers.append({"layer": layer, "buttons": buttons, "dial": encoder})
            result["layers"] = layers
        result["raw"] = raw
        return result
    finally:
        device.close()
