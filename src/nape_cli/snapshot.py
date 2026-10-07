"""Read Nape 1.3.0 settings over receiver or USB Raw HID. No setters occur here."""

from __future__ import annotations

from typing import Any

from .channel import request
from .devices import configuration_transport, hid_backend
from .firmware import CUSTOM_DPI_RANGE, RECORD_LIMIT, SCROLL_DPI_RANGE, require_firmware
from .macros import decode_macros

BUTTON_ORDER = ("03", "04", "01", "02", "M1", "M2", "Press")
POLLING_RATES = (8000, 4000, 2000, 1000, 500, 250, 125)


def read_snapshot(
    device_info: dict[str, Any],
    *,
    include_records: bool = False,
    include_backup: bool = False,
    include_device_settings: bool = False,
    include_keymap: bool = False,
    include_layer_orientations: bool = False,
    include_macro_buffer: bool = False,
    include_gesture: bool = False,
    include_force_gesture_scroll: bool = False,
    tap_hold_targets: tuple[tuple[int, str], ...] = (),
    combo_targets: tuple[int, ...] = (),
    timeout_ms: int = 1500,
) -> dict[str, Any]:
    """Open one supported Raw HID collection and always close it after reading."""
    transport = configuration_transport(device_info)
    if timeout_ms <= 0:
        raise ValueError("timeout must be positive")
    device = hid_backend().device()
    try:
        device.open_path(device_info["path"])
        return read_snapshot_from_device(
            device,
            transport=transport,
            include_records=include_records,
            include_backup=include_backup,
            include_device_settings=include_device_settings,
            include_keymap=include_keymap,
            include_layer_orientations=include_layer_orientations,
            include_macro_buffer=include_macro_buffer,
            include_gesture=include_gesture,
            include_force_gesture_scroll=include_force_gesture_scroll,
            tap_hold_targets=tap_hold_targets,
            combo_targets=combo_targets,
            timeout_ms=timeout_ms,
        )
    finally:
        device.close()


def read_snapshot_from_device(
    device: Any,
    *,
    include_records: bool = False,
    include_backup: bool = False,
    transport: str = "link-km-raw-hid",
    include_device_settings: bool = False,
    include_keymap: bool = False,
    include_layer_orientations: bool = False,
    include_macro_buffer: bool = False,
    include_gesture: bool = False,
    include_force_gesture_scroll: bool = False,
    tap_hold_targets: tuple[tuple[int, str], ...] = (),
    combo_targets: tuple[int, ...] = (),
    timeout_ms: int = 1500,
) -> dict[str, Any]:
    """Read an already-open channel, allowing apply to keep one handle."""
    if transport not in ("link-km-raw-hid", "usb-raw-hid"):
        raise ValueError("unsupported snapshot transport")
    if timeout_ms <= 0:
        raise ValueError("timeout must be positive")
    raw: dict[str, str] = {}

    def read(*values: int) -> bytes:
        payload = bytes(values)
        reply = request(device, payload, timeout_ms)
        raw[payload.hex(" ")] = reply.hex(" ")
        return reply

    if transport == "link-km-raw-hid":
        state = read(0xB2)
        if not any(state[offset] == 1 for offset in (6, 11, 16)):
            raise RuntimeError("no paired device is awake; wake the Nape in 2.4 GHz mode")
    firmware = read(0xA1)[1:].split(b"\x00", 1)[0].decode("ascii", errors="replace")
    support = require_firmware(firmware)
    layer_count = read(0x11)[1]
    if layer_count != 9:
        raise ValueError(f"expected the Nape's 9 layers, got {layer_count}")
    if any(
        not 0 <= layer < layer_count or button not in BUTTON_ORDER
        for layer, button in tap_hold_targets
    ):
        raise ValueError("invalid tap-hold target")
    if any(not 0 <= index < RECORD_LIMIT for index in combo_targets):
        raise ValueError("combo index must be in 0..29")
    if include_backup:
        include_device_settings = include_keymap = include_layer_orientations = True
        include_macro_buffer = include_gesture = include_force_gesture_scroll = True
        include_records = True
    if tap_hold_targets or combo_targets:
        include_records = True
    if include_records:
        tap_hold_targets = tuple(
            (layer, button) for layer in range(layer_count) for button in BUTTON_ORDER
        )
        combo_targets = tuple(range(RECORD_LIMIT))

    # A3 is the effective layer; A7 35 is the stored default layer.
    active_layer = read(0xA3)[1]
    if active_layer >= 12:
        raise ValueError(f"unexpected active layer wire value: {active_layer}")
    default_layer = read(0xA7, 0x35)[2]
    if default_layer >= 12:
        raise ValueError(f"unexpected default layer wire value: {default_layer}")
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
    if poll[10] and poll[11] >= len(POLLING_RATES):
        raise ValueError("unexpected secondary polling-rate index")
    result: dict[str, Any] = {
        "schema_version": 1,
        "transport": transport,
        "firmware": firmware,
        "capabilities": support.to_dict(),
        "default_layer": default_layer,
        "layer_count": layer_count,
        "active_layer": active_layer,
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
        # Preserve the raw secondary index even when its capability bitmap is zero.
        "polling_rate_for_fr_index": poll[11],
        "polling_rate_for_fr": POLLING_RATES[poll[11]] if poll[10] else None,
        "supported_polling_rates_for_fr": [
            rate for bit, rate in enumerate(POLLING_RATES) if poll[10] & (1 << bit)
        ],
    }
    if include_device_settings:
        custom_dpi = int.from_bytes(read(0xA7, 0x36)[2:4], "little")
        if not CUSTOM_DPI_RANGE[0] <= custom_dpi <= CUSTOM_DPI_RANGE[1]:
            raise ValueError(f"invalid custom DPI: {custom_dpi}")
        scroll_dpi = int.from_bytes(read(0xA7, 0x3A)[2:4], "little")
        if not SCROLL_DPI_RANGE[0] <= scroll_dpi <= SCROLL_DPI_RANGE[1]:
            raise ValueError(f"invalid scroll-mode DPI: {scroll_dpi}")
        stage_count = read(0xA7, 0x3C)[2]
        if not 1 <= stage_count <= 5:
            raise ValueError(f"invalid DPI stage count: {stage_count}")
        sleep = read(0xA7, 0x0B)
        result.update(
            {
                "custom_dpi": custom_dpi,
                "scroll_dpi": scroll_dpi,
                "dpi_stage_count": stage_count,
                "sleep": {
                    name: int.from_bytes(sleep[3 + i * 2 : 5 + i * 2], "little")
                    for i, name in enumerate(("backlight", "sleep", "magnet_scan"))
                },
            }
        )
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
    if include_layer_orientations:
        orientations = []
        for layer in range(layer_count):
            units = read(0xA7, 0x38, layer)[2]
            if units > 7:
                raise ValueError(f"invalid orientation units for layer {layer}: {units}")
            if include_keymap:
                result["layers"][layer]["orientation"] = units * 45
            else:
                orientations.append({"layer": layer, "orientation": units * 45})
        if not include_keymap:
            result["layer_orientations"] = orientations
    if include_gesture:
        reply = read(0xA7, 0x2A)
        result["gesture"] = {
            name: int.from_bytes(reply[2 + i * 2 : 4 + i * 2], "little")
            for i, name in enumerate(("up", "down", "left", "right"))
        }
    if include_force_gesture_scroll:
        reply = read(0xA7, 0x33)
        if reply[2] > 15 or reply[3] > 15:
            raise ValueError("invalid force gesture/scroll nibble")
        result["force_gesture_scroll"] = {"gesture": reply[2], "scroll": reply[3]}
    if include_records:
        tap_holds = {}
        for layer, button in tap_hold_targets:
            column = BUTTON_ORDER.index(button)
            # A timeout is not evidence of absence, even for create/delete requests.
            reply = read(0xA7, 0x26, layer, 0, column)
            if reply[2:5] != bytes((layer, 0, column)):
                raise ValueError("tap-hold reply did not echo its target")
            tap = int.from_bytes(reply[5:7], "little")
            held = int.from_bytes(reply[7:9], "little")
            if (
                tap == 0
                and held == 0
                and reply != bytes((0xA7, 0x26, layer, 0, column)).ljust(32, b"\x00")
            ):
                raise ValueError(f"malformed empty tap-hold record {layer}:{button}")
            tap_holds[f"{layer}:{button}"] = (
                None if tap == 0 and held == 0 else {"tap": tap, "held": held}
            )
        if sum(value is not None for value in tap_holds.values()) > RECORD_LIMIT:
            raise ValueError("invalid tap-hold inventory: capacity is 30 records")
        combos = {}
        for index in combo_targets:
            reply = read(0xA7, 0x28, index)
            if reply[2] != index:
                raise ValueError("combo reply does not echo its index")
            if reply[6] == 0:
                if reply != bytes((0xA7, 0x28, index)).ljust(32, b"\x00"):
                    raise ValueError(f"malformed empty combo record {index}")
                combos[str(index)] = None
                continue
            if reply[5] >= layer_count:
                raise ValueError(f"invalid layer in combo {index}: {reply[5]}")
            combos[str(index)] = {
                "timeout_ms": int.from_bytes(reply[3:5], "little"),
                "layer": reply[5],
                "columns": reply[6],
                "tap": int.from_bytes(reply[7:9], "little"),
                "held": int.from_bytes(reply[9:11], "little"),
            }
        result.update({"tap_holds": tap_holds, "combos": combos, "record_inventory": True})
    if include_macro_buffer:
        via_protocol_version = int.from_bytes(read(0x01)[1:3], "big")
        macro_count = read(0x0C)[1]
        macro_size = int.from_bytes(read(0x0D)[1:3], "big")
        macro_bytes = bytearray()
        for offset in range(0, macro_size, 28):
            size = min(28, macro_size - offset)
            reply = read(0x0E, offset >> 8, offset & 0xFF, size)
            if reply[3] != size:
                raise ValueError(f"macro-buffer read returned {reply[3]} bytes, expected {size}")
            macro_bytes.extend(reply[4 : 4 + size])
        result.update(
            {
                "via_protocol_version": via_protocol_version,
                "macro_count": macro_count,
                "macro_buffer_size": macro_size,
                "macro_buffer": macro_bytes.hex(),
                "macros": decode_macros(
                    bytes(macro_bytes), count=macro_count, protocol_version=via_protocol_version
                ),
            }
        )
    result["raw"] = raw
    return result
