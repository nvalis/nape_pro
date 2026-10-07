"""Read Nape settings and the nine-layer dynamic keymap via Link-KM.

Core wire layouts were cross-checked against ky0209/NapeBar's protocol code and
read replies from Nape firmware v1.1.6-ZK. VIA macro reads are hardware-tested.
Per-layer orientation is Launcher-derived, but the tested firmware echoes the
requested layer instead of returning a usable angle. No writes occur here.
"""

from __future__ import annotations

from typing import Any

from .channel import request
from .devices import hid_backend
from .macros import decode_macros
from .receiver import validate_receiver

BUTTON_ORDER = ("03", "04", "01", "02", "M1", "M2", "Press")
POLLING_RATES = (8000, 4000, 2000, 1000, 500, 250, 125)


def read_snapshot(
    device_info: dict[str, Any],
    *,
    include_device_settings: bool = False,
    include_keymap: bool = False,
    include_layer_orientations: bool = False,
    include_macro_buffer: bool = False,
    include_gesture: bool = False,
    include_force_gesture_scroll: bool = False,
    tap_hold_targets: tuple[tuple[int, str], ...] = (),
    combo_targets: tuple[int, ...] = (),
    allow_missing_tap_holds: bool = False,
    allow_missing_combos: bool = False,
    timeout_ms: int = 1500,
) -> dict[str, Any]:
    """Open one receiver collection and always close it after reading."""
    validate_receiver(device_info)
    device = hid_backend().device()
    try:
        device.open_path(device_info["path"])
        return read_snapshot_from_device(
            device,
            include_device_settings=include_device_settings,
            include_keymap=include_keymap,
            include_layer_orientations=include_layer_orientations,
            include_macro_buffer=include_macro_buffer,
            include_gesture=include_gesture,
            include_force_gesture_scroll=include_force_gesture_scroll,
            tap_hold_targets=tap_hold_targets,
            combo_targets=combo_targets,
            allow_missing_tap_holds=allow_missing_tap_holds,
            allow_missing_combos=allow_missing_combos,
            timeout_ms=timeout_ms,
        )
    finally:
        device.close()


def read_snapshot_from_device(
    device: Any,
    *,
    include_device_settings: bool = False,
    include_keymap: bool = False,
    include_layer_orientations: bool = False,
    include_macro_buffer: bool = False,
    include_gesture: bool = False,
    include_force_gesture_scroll: bool = False,
    tap_hold_targets: tuple[tuple[int, str], ...] = (),
    combo_targets: tuple[int, ...] = (),
    allow_missing_tap_holds: bool = False,
    allow_missing_combos: bool = False,
    timeout_ms: int = 1500,
) -> dict[str, Any]:
    """Read using an already-open channel, allowing apply to keep one handle."""
    raw: dict[str, str] = {}

    def read(*values: int, request_timeout_ms: int | None = None) -> bytes:
        payload = bytes(values)
        reply = request(device, payload, request_timeout_ms or timeout_ms)
        raw[payload.hex(" ")] = reply.hex(" ")
        return reply

    state = read(0xB2)
    if not any(state[offset] == 1 for offset in (6, 11, 16)):
        raise RuntimeError("no paired device is awake; wake the Nape in 2.4 GHz mode")
    firmware = read(0xA1)[1:].split(b"\x00", 1)[0].decode("ascii", errors="replace")
    layer_count = read(0x11)[1]
    if layer_count != 9:
        raise ValueError(f"expected the tested Nape's 9 layers, got {layer_count}")
    if include_layer_orientations and firmware.split(" ", 1)[0] == "v1.1.6-ZK":
        raise ValueError("per-layer orientation is unreadable on Nape firmware v1.1.6-ZK")
    # Launcher uses this wire value directly for both reads and SET_LAYER.
    active_layer = read(0xA3)[1]
    if not 0 <= active_layer < layer_count:
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
    if poll[10] and poll[11] >= len(POLLING_RATES):
        raise ValueError("unexpected secondary polling-rate index")
    result: dict[str, Any] = {
        "schema_version": 1,
        "transport": "link-km-raw-hid",
        "firmware": firmware,
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
        # Preserve the raw index even when the secondary capability bitmap is zero.
        "polling_rate_for_fr_index": poll[11],
        "polling_rate_for_fr": POLLING_RATES[poll[11]] if poll[10] else None,
        "supported_polling_rates_for_fr": [
            rate for bit, rate in enumerate(POLLING_RATES) if poll[10] & (1 << bit)
        ],
    }
    if include_device_settings:
        custom_dpi_reply = read(0xA7, 0x36)
        custom_dpi = int.from_bytes(custom_dpi_reply[2:4], "little")
        # This firmware echoes the zero-padded query for unsupported optional settings.
        # Zero is outside the configured value domain, so retain the raw reply and mark
        # the value unavailable rather than guessing a default or aborting other reads.
        result["custom_dpi"] = custom_dpi or None

        stage_count_reply = read(0xA7, 0x3C)
        stage_count = stage_count_reply[2]
        if stage_count == 0 and stage_count_reply == bytes((0xA7, 0x3C)).ljust(32, b"\x00"):
            result["dpi_stage_count"] = None
        elif 1 <= stage_count <= 5:
            result["dpi_stage_count"] = stage_count
        else:
            raise ValueError(f"invalid DPI stage count: {stage_count}")

        sleep = read(0xA7, 0x0B)
        result["sleep"] = {
            name: int.from_bytes(sleep[3 + i * 2 : 5 + i * 2], "little")
            for i, name in enumerate(("backlight", "sleep", "magnet_scan"))
        }
        # Launcher rejects this response rather than guessing disabled/default timers.
        if result["sleep"]["backlight"] == 0 and result["sleep"]["sleep"] == 0:
            raise ValueError("sleep query returned no usable state (backlight and sleep are zero)")
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
            layer_data = {"layer": layer, "buttons": buttons, "dial": encoder}
            if include_layer_orientations:
                reply = read(0xA7, 0x38, layer)
                units = reply[2]
                if units > 7:
                    raise ValueError(f"invalid orientation units for layer {layer}: {units}")
                layer_data["orientation"] = units * 45
            layers.append(layer_data)
        result["layers"] = layers
    elif include_layer_orientations:
        orientations = []
        for layer in range(layer_count):
            reply = read(0xA7, 0x38, layer)
            units = reply[2]
            if units > 7:
                raise ValueError(f"invalid orientation units for layer {layer}: {units}")
            orientations.append({"layer": layer, "orientation": units * 45})
        result["layer_orientations"] = orientations
    if include_gesture:
        reply = read(0xA7, 0x2A)
        result["gesture"] = {
            name: int.from_bytes(reply[2 + i * 2 : 4 + i * 2], "little")
            for i, name in enumerate(("up", "down", "left", "right"))
        }
    if include_force_gesture_scroll:
        reply = read(0xA7, 0x33)
        result["force_gesture_scroll"] = {"gesture": reply[2], "scroll": reply[3]}
    if tap_hold_targets:
        tap_holds = {}
        for layer, button in tap_hold_targets:
            if not 0 <= layer < layer_count or button not in BUTTON_ORDER:
                raise ValueError("invalid tap-hold target")
            column = BUTTON_ORDER.index(button)
            # A timeout is not evidence of absence, even for create/delete requests.
            reply = read(0xA7, 0x26, layer, 0, column)
            if reply[2] != layer or reply[3] != 0 or reply[4] != column:
                raise ValueError("tap-hold reply did not echo its target")
            tap = int.from_bytes(reply[5:7], "little")
            held = int.from_bytes(reply[7:9], "little")
            tap_holds[f"{layer}:{button}"] = (
                None if tap == 0 and held == 0 else {"tap": tap, "held": held}
            )
        result["tap_holds"] = tap_holds
    if combo_targets:
        combos = {}
        for index in combo_targets:
            if not 0 <= index <= 255:
                raise ValueError("combo index must be a byte")
            reply = read(0xA7, 0x28, index, request_timeout_ms=min(timeout_ms, 500))
            if reply[2] != index:
                raise ValueError("combo reply does not echo its index")
            if reply[6] == 0:
                if not allow_missing_combos:
                    raise ValueError("combo slot is empty; use create or delete explicitly")
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
        result["combos"] = combos
    if include_macro_buffer:
        via_protocol_version = int.from_bytes(read(0x01)[1:3], "big")
        macro_count = read(0x0C)[1]
        size_reply = read(0x0D)
        macro_size = int.from_bytes(size_reply[1:3], "big")
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
                    bytes(macro_bytes),
                    count=macro_count,
                    protocol_version=via_protocol_version,
                ),
            }
        )
    result["raw"] = raw
    return result
