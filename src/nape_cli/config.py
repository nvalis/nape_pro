"""Strict partial configuration and side-effect-free settings/keymap planning."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .macros import MacroStep, decode_macros, encode_macros
from .protocol import orientation_units
from .snapshot import BUTTON_ORDER, POLLING_RATES

POINTER_FIELDS = ("dpi_values", "dpi_index", "orientation", "polling_rate")
DEVICE_FIELDS = ("custom_dpi", "dpi_stage_count", "sleep")
SLEEP_FIELDS = ("backlight", "sleep", "magnet_scan")
DIAL_ORDER = ("ccw", "cw")
GESTURE_DIRECTIONS = ("up", "down", "left", "right")
FORCE_SCROLL_FIELDS = ("gesture", "scroll")


@dataclass(frozen=True)
class LayerConfig:
    layer: int
    buttons: tuple[tuple[str, int], ...] = ()
    dial: tuple[tuple[str, int], ...] = ()
    orientation: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"layer": self.layer}
        for field in ("buttons", "dial"):
            bindings = getattr(self, field)
            if bindings:
                result[field] = {name: f"0x{code:04X}" for name, code in bindings}
        if self.orientation is not None:
            result["orientation"] = self.orientation
        return result


@dataclass(frozen=True)
class TapHoldConfig:
    layer: int
    button: str
    tap: int | None = None
    held: int | None = None
    delete: bool = False
    create: bool = False

    def to_dict(self) -> dict[str, Any]:
        if self.delete:
            return {"layer": self.layer, "button": self.button, "delete": True}
        result = {
            "layer": self.layer,
            "button": self.button,
            "tap": f"0x{self.tap:04X}",
            "held": f"0x{self.held:04X}",
        }
        if self.create:
            result["create"] = True
        return result


@dataclass(frozen=True)
class ComboConfig:
    index: int
    layer: int | None = None
    columns: int | None = None
    tap: int | None = None
    held: int | None = None
    timeout_ms: int = 200
    delete: bool = False
    create: bool = False

    def to_dict(self) -> dict[str, Any]:
        if self.delete:
            return {"index": self.index, "delete": True}
        result = {
            "index": self.index,
            "layer": self.layer,
            "columns": self.columns,
            "tap": f"0x{self.tap:04X}",
            "held": f"0x{self.held:04X}",
            "timeout_ms": self.timeout_ms,
        }
        if self.create:
            result["create"] = True
        return result


@dataclass(frozen=True)
class NapeConfig:
    orientation: int | None = None
    dpi_index: int | None = None
    dpi_values: tuple[int, ...] | None = None
    polling_rate: int | None = None
    active_layer: int | None = None
    custom_dpi: int | None = None
    dpi_stage_count: int | None = None
    sleep: tuple[tuple[str, int], ...] = ()
    layers: tuple[LayerConfig, ...] = ()
    tap_holds: tuple[TapHoldConfig, ...] = ()
    combos: tuple[ComboConfig, ...] = ()
    gesture: tuple[tuple[str, int], ...] = ()
    force_gesture_scroll: tuple[tuple[str, int], ...] = ()
    macro_buffer: str | None = None
    macros: tuple[tuple[MacroStep, ...], ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"schema_version": 1}
        for name in (*POINTER_FIELDS, "custom_dpi", "dpi_stage_count"):
            value = getattr(self, name)
            if value is not None:
                result[name] = list(value) if isinstance(value, tuple) else value
        if self.active_layer is not None:
            result["active_layer"] = self.active_layer
        if self.sleep:
            result["sleep"] = dict(self.sleep)
        if self.layers:
            result["layers"] = [layer.to_dict() for layer in self.layers]
        if self.tap_holds:
            result["tap_holds"] = [entry.to_dict() for entry in self.tap_holds]
        if self.combos:
            result["combos"] = [entry.to_dict() for entry in self.combos]
        if self.gesture:
            result["gesture"] = {name: f"0x{code:04X}" for name, code in self.gesture}
        if self.force_gesture_scroll:
            result["force_gesture_scroll"] = dict(self.force_gesture_scroll)
        if self.macro_buffer is not None:
            result["macro_buffer"] = self.macro_buffer
        if self.macros is not None:
            result["macros"] = [[step.to_dict() for step in macro] for macro in self.macros]
        return result

    @property
    def requires_device_settings(self) -> bool:
        return self.custom_dpi is not None or self.dpi_stage_count is not None or bool(self.sleep)


@dataclass(frozen=True)
class Change:
    field: str
    before: Any
    after: Any
    index: int | None = None
    layer: int | None = None
    binding: str | None = None

    def to_dict(self) -> dict[str, Any]:
        keymap = self.field in ("buttons", "dial")
        if self.field == "macro_buffer":
            before = _macro_summary(self.before)
            after = _macro_summary(self.after)
        elif self.field in ("gesture", "force_gesture_scroll"):
            before = _format_bindings(self.before)
            after = _format_bindings(self.after)
        elif self.field in ("tap_hold", "combo"):
            before = _format_action_record(self.before)
            after = _format_action_record(self.after)
        else:
            before = f"0x{self.before:04X}" if keymap else self.before
            after = f"0x{self.after:04X}" if keymap else self.after
        return {"setting": self.setting, "before": before, "after": after}

    @property
    def setting(self) -> str:
        if self.field in ("buttons", "dial"):
            return f"layers[{self.layer}].{self.field}.{self.binding}"
        if self.field == "layer_orientation":
            return f"layers[{self.layer}].orientation"
        if self.field == "tap_hold":
            return f"tap_holds[{self.layer}].{self.binding}"
        if self.field == "combo":
            return f"combos[{self.index}]"
        return f"{self.field}[{self.index}]" if self.index is not None else self.field


def _tap_hold_key(layer: int, button: str) -> str:
    return f"{layer}:{button}"


def _macro_summary(value: str) -> dict[str, Any]:
    raw = bytes.fromhex(value)
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _format_bindings(value: dict[str, int]) -> dict[str, str]:
    return {name: f"0x{code:04X}" for name, code in value.items()}


def _format_action_record(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        name: f"0x{code:04X}" if name in ("tap", "held") else code for name, code in value.items()
    }


def _integer(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def _bindings(value: object, field: str, names: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field} must be a non-empty binding object")
    if set(value) - set(names):
        raise ValueError(f"unknown {field} binding name")
    result = []
    for name in names:
        if name not in value:
            continue
        code = value[name]
        if not isinstance(code, str) or re.fullmatch(r"0[xX][0-9a-fA-F]{4}", code) is None:
            raise ValueError(f"{field}.{name} must be a four-digit hex keycode, e.g. 0x0068")
        result.append((name, int(code, 16)))
    return tuple(result)


def _keycode(value: object, name: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0[xX][0-9a-fA-F]{4}", value) is None:
        raise ValueError(f"{name} must be a four-digit hex keycode, e.g. 0x0068")
    return int(value, 16)


def _tap_holds(value: object) -> tuple[TapHoldConfig, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("tap_holds must be a non-empty list")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each tap_holds entry must be an object")
        layer = _integer(item.get("layer"), "tap_holds.layer", 0, 8)
        button = item.get("button")
        if button not in BUTTON_ORDER:
            raise ValueError("tap_holds.button must be one of the seven button names")
        key = (layer, button)
        if key in seen:
            raise ValueError(f"duplicate tap-hold target: layer {layer}, button {button}")
        seen.add(key)
        delete = item.get("delete", False)
        if type(delete) is not bool:
            raise ValueError("tap_holds.delete must be boolean")
        if delete:
            if set(item) != {"layer", "button", "delete"}:
                raise ValueError("deleted tap-hold entries accept only layer, button, delete")
            result.append(TapHoldConfig(layer, button, delete=True))
            continue
        create = item.get("create", False)
        if type(create) is not bool:
            raise ValueError("tap_holds.create must be boolean")
        if set(item) - {"layer", "button", "tap", "held", "create"}:
            raise ValueError("tap-hold entries contain unknown fields")
        if not {"layer", "button", "tap", "held"}.issubset(item):
            raise ValueError("tap-hold entries require layer, button, tap, and held")
        tap = _keycode(item["tap"], "tap_holds.tap")
        held = _keycode(item["held"], "tap_holds.held")
        if tap == 0 and held == 0:
            raise ValueError("use delete: true to remove an empty tap-hold")
        result.append(TapHoldConfig(layer, button, tap, held, create=create))
    return tuple(result)


def _combos(value: object) -> tuple[ComboConfig, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("combos must be a non-empty list")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each combo entry must be an object")
        index = _integer(item.get("index"), "combos.index", 0, 255)
        if index in seen:
            raise ValueError(f"duplicate combo index: {index}")
        seen.add(index)
        delete = item.get("delete", False)
        if type(delete) is not bool:
            raise ValueError("combos.delete must be boolean")
        if delete:
            if set(item) != {"index", "delete"}:
                raise ValueError("deleted combo entries accept only index and delete")
            result.append(ComboConfig(index, delete=True))
            continue
        create = item.get("create", False)
        if type(create) is not bool:
            raise ValueError("combos.create must be boolean")
        if set(item) - {"index", "layer", "columns", "tap", "held", "timeout_ms", "create"}:
            raise ValueError("combo entries contain unknown fields")
        required = {"index", "layer", "columns", "tap", "held"}
        if not required.issubset(item):
            raise ValueError("combo entries require index, layer, columns, tap, and held")
        layer = _integer(item["layer"], "combos.layer", 0, 8)
        columns = _integer(item["columns"], "combos.columns", 1, 255)
        timeout = _integer(item.get("timeout_ms", 200), "combos.timeout_ms", 0, 65535)
        result.append(
            ComboConfig(
                index,
                layer,
                columns,
                _keycode(item["tap"], "combos.tap"),
                _keycode(item["held"], "combos.held"),
                timeout,
                create=create,
            )
        )
    return tuple(result)


def _gesture(value: object) -> tuple[tuple[str, int], ...]:
    return _bindings(value, "gesture", GESTURE_DIRECTIONS)


def _force_scroll(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, dict) or not value or set(value) - set(FORCE_SCROLL_FIELDS):
        raise ValueError("force_gesture_scroll must contain gesture and/or scroll bytes")
    return tuple(
        (field, _integer(value[field], f"force_gesture_scroll.{field}", 0, 255))
        for field in FORCE_SCROLL_FIELDS
        if field in value
    )


def _macros(value: object) -> tuple[tuple[MacroStep, ...], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("macros must be a non-empty list of macro step lists")
    macros: list[tuple[MacroStep, ...]] = []
    for macro_index, macro in enumerate(value):
        if not isinstance(macro, list):
            raise ValueError(f"macros[{macro_index}] must be a list")
        steps = []
        for step_index, step in enumerate(macro):
            name = f"macros[{macro_index}][{step_index}]"
            if not isinstance(step, dict) or not isinstance(step.get("type"), str):
                raise ValueError(f"{name} must be a typed action object")
            kind = step["type"]
            if kind in ("tap", "down", "up") and set(step) == {"type", "keycode"}:
                code = _keycode(step["keycode"], f"{name}.keycode")
                if code > 255:
                    raise ValueError(f"{name}.keycode must fit in one macro byte (0x0000..0x00FF)")
                steps.append(MacroStep(kind, keycode=code))
            elif kind == "delay" and set(step) == {"type", "ms"}:
                steps.append(
                    MacroStep(kind, milliseconds=_integer(step["ms"], f"{name}.ms", 0, 65535))
                )
            elif kind == "text" and set(step) == {"type", "text"} and isinstance(step["text"], str):
                if any(ord(char) > 255 for char in step["text"]):
                    raise ValueError(f"{name}.text supports only code points 0..255")
                if any(char in "\x00\x01" for char in step["text"]):
                    raise ValueError(f"{name}.text cannot contain a reserved macro opcode (00/01)")
                steps.append(MacroStep(kind, text=step["text"]))
            else:
                raise ValueError(f"{name} has invalid fields or action type")
        macros.append(tuple(steps))
    return tuple(macros)


def _layers(value: object) -> tuple[LayerConfig, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("layers must be a non-empty list of partial layer configs")
    result = []
    seen = set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) - {"layer", "buttons", "dial", "orientation"}:
            raise ValueError("each layer accepts only layer, buttons, dial, and orientation fields")
        layer = _integer(entry.get("layer"), "layer", 0, 8)
        if layer in seen:
            raise ValueError(f"duplicate layer index: {layer}")
        seen.add(layer)
        if not {"buttons", "dial", "orientation"}.intersection(entry):
            raise ValueError(f"layer {layer} must specify bindings or an orientation")
        buttons = _bindings(entry["buttons"], "buttons", BUTTON_ORDER) if "buttons" in entry else ()
        dial = _bindings(entry["dial"], "dial", DIAL_ORDER) if "dial" in entry else ()
        orientation = None
        if "orientation" in entry:
            orientation = _integer(entry["orientation"], f"layers[{layer}].orientation", 0, 315)
            orientation_units(orientation)
        result.append(LayerConfig(layer, buttons, dial, orientation))
    return tuple(sorted(result, key=lambda entry: entry.layer))


def validate_config(data: object) -> NapeConfig:
    if not isinstance(data, dict):
        raise ValueError("configuration must be a JSON object")
    config_fields = {
        "schema_version",
        "layers",
        "macro_buffer",
        "macros",
        "active_layer",
        "tap_holds",
        "combos",
        "gesture",
        "force_gesture_scroll",
        *POINTER_FIELDS,
        *DEVICE_FIELDS,
    }
    unknown = set(data) - config_fields
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(sorted(map(str, unknown)))}")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if not any(name in data for name in config_fields - {"schema_version"}):
        raise ValueError("configuration must specify at least one setting or binding")

    orientation = None
    if "orientation" in data:
        orientation = _integer(data["orientation"], "orientation", 0, 315)
        orientation_units(orientation)
    dpi_index = None
    if "dpi_index" in data:
        dpi_index = _integer(data["dpi_index"], "dpi_index", 0, 4)
    dpi_values = None
    if "dpi_values" in data:
        values = data["dpi_values"]
        if not isinstance(values, list) or len(values) != 5:
            raise ValueError("dpi_values must be a list of exactly five integers")
        dpi_values = tuple(_integer(v, f"dpi_values[{i}]", 1, 65535) for i, v in enumerate(values))
    polling_rate = None
    if "polling_rate" in data:
        polling_rate = _integer(data["polling_rate"], "polling_rate", 125, 8000)
        if polling_rate not in POLLING_RATES:
            raise ValueError(f"polling_rate must be one of {POLLING_RATES}")
    active_layer = (
        _integer(data["active_layer"], "active_layer", 0, 8) if "active_layer" in data else None
    )
    custom_dpi = (
        _integer(data["custom_dpi"], "custom_dpi", 1, 65535) if "custom_dpi" in data else None
    )
    dpi_stage_count = (
        _integer(data["dpi_stage_count"], "dpi_stage_count", 1, 5)
        if "dpi_stage_count" in data
        else None
    )
    sleep = ()
    if "sleep" in data:
        values = data["sleep"]
        if not isinstance(values, dict) or not values or set(values) - set(SLEEP_FIELDS):
            raise ValueError("sleep must be a non-empty map of backlight, sleep, magnet_scan")
        sleep = tuple(
            (name, _integer(values[name], f"sleep.{name}", 0, 65535))
            for name in SLEEP_FIELDS
            if name in values
        )
    if dpi_index is not None and dpi_stage_count is not None and dpi_index >= dpi_stage_count:
        raise ValueError("dpi_index must be below dpi_stage_count")
    layers = _layers(data["layers"]) if "layers" in data else ()
    tap_holds = _tap_holds(data["tap_holds"]) if "tap_holds" in data else ()
    combos = _combos(data["combos"]) if "combos" in data else ()
    gesture = _gesture(data["gesture"]) if "gesture" in data else ()
    force_scroll = (
        _force_scroll(data["force_gesture_scroll"]) if "force_gesture_scroll" in data else ()
    )
    macro_buffer = None
    if "macro_buffer" in data:
        value = data["macro_buffer"]
        if (
            not isinstance(value, str)
            or len(value) % 2
            or re.fullmatch(r"(?:[0-9a-fA-F]{2})+", value) is None
        ):
            raise ValueError("macro_buffer must be a non-empty string of whole-byte hex data")
        macro_buffer = value.lower()
    macros = _macros(data["macros"]) if "macros" in data else None
    if macros is not None and macro_buffer is not None:
        raise ValueError("specify either macros or macro_buffer, not both")
    return NapeConfig(
        orientation=orientation,
        dpi_index=dpi_index,
        dpi_values=dpi_values,
        polling_rate=polling_rate,
        active_layer=active_layer,
        custom_dpi=custom_dpi,
        dpi_stage_count=dpi_stage_count,
        sleep=sleep,
        layers=layers,
        tap_holds=tap_holds,
        combos=combos,
        gesture=gesture,
        force_gesture_scroll=force_scroll,
        macro_buffer=macro_buffer,
        macros=macros,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON field: {name}")
        result[name] = value
    return result


def load_config(path: Path) -> NapeConfig:
    return validate_config(
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    )


def desired_settings(config: NapeConfig, current: dict[str, Any]) -> dict[str, Any]:
    """Merge only requested settings/bindings, never modifying the snapshot."""
    config = validate_config(config.to_dict())
    if (
        config.polling_rate is not None
        and config.polling_rate not in current["supported_polling_rates"]
    ):
        raise ValueError(f"device does not report support for {config.polling_rate} Hz")
    if config.polling_rate is not None and "polling_rate_for_fr_index" not in current:
        raise ValueError("secondary polling-rate state is required to preserve polling settings")
    result = {field: copy.deepcopy(current[field]) for field in POINTER_FIELDS}
    if "polling_rate_for_fr_index" in current:
        result["polling_rate_for_fr_index"] = current["polling_rate_for_fr_index"]
    result.update({key: value for key, value in config.to_dict().items() if key in POINTER_FIELDS})
    if "active_layer" in current:
        result["active_layer"] = current["active_layer"]
    if config.active_layer is not None:
        if "active_layer" not in current:
            raise ValueError("active-layer state is required to plan layer switching")
        if config.orientation is not None and current["active_layer"] != config.active_layer:
            raise ValueError(
                "switch active_layer and set orientation in separate applies; "
                "orientation is layer-dependent on the tested firmware"
            )
        result["active_layer"] = config.active_layer
    for field in DEVICE_FIELDS:
        if field in current:
            result[field] = copy.deepcopy(current[field])
    if config.requires_device_settings and any(field not in current for field in DEVICE_FIELDS):
        raise ValueError("custom DPI, stage-count, and sleep state must be read before planning")
    if config.custom_dpi is not None and current.get("custom_dpi") is None:
        raise ValueError("device returned no usable custom DPI value; refusing to plan or write it")
    if config.dpi_stage_count is not None and current.get("dpi_stage_count") is None:
        raise ValueError("device returned no usable DPI stage count; refusing to plan or write it")
    for field in ("custom_dpi", "dpi_stage_count"):
        value = getattr(config, field)
        if value is not None:
            result[field] = value
    if config.sleep:
        result["sleep"].update(dict(config.sleep))
        if result["sleep"]["backlight"] == 0 and result["sleep"]["sleep"] == 0:
            raise ValueError("sleep/backlight cannot both be zero: Launcher read-back is unusable")
    if (
        result.get("dpi_stage_count") is not None
        and (config.dpi_stage_count is not None or config.dpi_index is not None)
        and result["dpi_index"] >= result["dpi_stage_count"]
    ):
        raise ValueError("select a dpi_index below the requested DPI stage count")
    if "layers" in current:
        result["layers"] = copy.deepcopy(current["layers"])
    if "gesture" in current:
        result["gesture"] = copy.deepcopy(current["gesture"])
    if config.gesture:
        if "gesture" not in result:
            raise ValueError("gesture state must be read before planning gesture changes")
        result["gesture"].update(dict(config.gesture))
    if "force_gesture_scroll" in current:
        result["force_gesture_scroll"] = copy.deepcopy(current["force_gesture_scroll"])
    if config.force_gesture_scroll:
        if "force_gesture_scroll" not in result:
            raise ValueError("force-scroll state must be read before planning changes")
        result["force_gesture_scroll"].update(dict(config.force_gesture_scroll))
    if config.layers:
        if "layers" not in result:
            raise ValueError("a full keymap snapshot is required to plan layer changes")
        for layer in config.layers:
            target = result["layers"][layer.layer]
            for field in ("buttons", "dial"):
                for name, code in getattr(layer, field):
                    target[field][name] = f"0x{code:04X}"
            if layer.orientation is not None:
                if "orientation" not in target:
                    raise ValueError("per-layer orientation data is required to plan this change")
                target["orientation"] = layer.orientation
    if config.tap_holds:
        if "tap_holds" not in current:
            raise ValueError("tap-hold state must be read before planning this change")
        result["tap_holds"] = copy.deepcopy(current["tap_holds"])
        for item in config.tap_holds:
            key = _tap_hold_key(item.layer, item.button)
            if item.create and result["tap_holds"].get(key) is not None:
                raise ValueError(f"tap-hold {key} is not empty; refusing to overwrite it")
            result["tap_holds"][key] = (
                None
                if item.delete
                else {
                    "tap": item.tap,
                    "held": item.held,
                }
            )
    if config.combos:
        if "combos" not in current:
            raise ValueError("combo state must be read before planning this change")
        result["combos"] = copy.deepcopy(current["combos"])
        for item in config.combos:
            if item.create and result["combos"].get(str(item.index)) is not None:
                raise ValueError(f"combo index {item.index} is not empty; refusing to overwrite it")
            result["combos"][str(item.index)] = (
                None
                if item.delete
                else {
                    "layer": item.layer,
                    "columns": item.columns,
                    "tap": item.tap,
                    "held": item.held,
                    "timeout_ms": item.timeout_ms,
                }
            )
    macro_buffer = config.macro_buffer
    if config.macros is not None:
        required = ("macro_count", "macro_buffer_size", "via_protocol_version")
        if any(field not in current for field in required):
            raise ValueError("macro metadata must be read before planning structured macros")
        target = encode_macros(
            config.macros,
            count=current["macro_count"],
            size=current["macro_buffer_size"],
            protocol_version=current["via_protocol_version"],
        )
        macro_buffer = target.hex()
    if macro_buffer is not None:
        if "macro_buffer" not in current:
            raise ValueError("a macro-buffer snapshot is required to plan macro changes")
        if len(macro_buffer) != len(current["macro_buffer"]):
            raise ValueError(
                "macro_buffer must contain exactly the device's full macro-buffer size"
            )
        if "macro_buffer_size" in current and not macro_buffer.endswith("00"):
            raise ValueError("the final macro-buffer byte must be zero (Launcher finalization)")
        if "macro_count" in current and "via_protocol_version" in current:
            decode_macros(
                bytes.fromhex(macro_buffer),
                count=current["macro_count"],
                protocol_version=current["via_protocol_version"],
            )
        result["macro_buffer"] = macro_buffer
    return result


def plan_changes(config: NapeConfig, current: dict[str, Any]) -> list[Change]:
    desired = desired_settings(config, current)
    changes = []
    if config.active_layer is not None and current["active_layer"] != desired["active_layer"]:
        changes.append(Change("active_layer", current["active_layer"], desired["active_layer"]))
    count_change = (
        config.dpi_stage_count is not None
        and current["dpi_stage_count"] != desired["dpi_stage_count"]
    )
    # Grow before selecting a newly enabled stage; shrink only after moving off disabled stages.
    if count_change and desired["dpi_stage_count"] > current["dpi_stage_count"]:
        changes.append(
            Change("dpi_stage_count", current["dpi_stage_count"], desired["dpi_stage_count"])
        )
    for field in POINTER_FIELDS:
        if field == "dpi_values":
            for index, (before, after) in enumerate(
                zip(current[field], desired[field], strict=True)
            ):
                if before != after:
                    changes.append(Change(field, before, after, index))
        elif current[field] != desired[field]:
            changes.append(Change(field, current[field], desired[field]))
    if count_change and desired["dpi_stage_count"] < current["dpi_stage_count"]:
        changes.append(
            Change("dpi_stage_count", current["dpi_stage_count"], desired["dpi_stage_count"])
        )
    if config.custom_dpi is not None and current["custom_dpi"] != desired["custom_dpi"]:
        changes.append(Change("custom_dpi", current["custom_dpi"], desired["custom_dpi"]))
    if config.sleep and current["sleep"] != desired["sleep"]:
        changes.append(Change("sleep", current["sleep"], desired["sleep"]))
    for layer in config.layers:
        for field in ("buttons", "dial"):
            for name, _ in getattr(layer, field):
                before = int(current["layers"][layer.layer][field][name], 16)
                after = int(desired["layers"][layer.layer][field][name], 16)
                if before != after:
                    changes.append(Change(field, before, after, layer=layer.layer, binding=name))
        if layer.orientation is not None:
            before = current["layers"][layer.layer]["orientation"]
            after = desired["layers"][layer.layer]["orientation"]
            if before != after:
                changes.append(Change("layer_orientation", before, after, layer=layer.layer))
    if config.gesture and current["gesture"] != desired["gesture"]:
        changes.append(Change("gesture", current["gesture"], desired["gesture"]))
    if (
        config.force_gesture_scroll
        and current["force_gesture_scroll"] != desired["force_gesture_scroll"]
    ):
        changes.append(
            Change(
                "force_gesture_scroll",
                current["force_gesture_scroll"],
                desired["force_gesture_scroll"],
            )
        )
    for item in config.tap_holds:
        key = _tap_hold_key(item.layer, item.button)
        before = current["tap_holds"][key]
        after = desired["tap_holds"][key]
        if before != after:
            changes.append(Change("tap_hold", before, after, layer=item.layer, binding=item.button))
    for item in config.combos:
        before = current["combos"][str(item.index)]
        after = desired["combos"][str(item.index)]
        if before != after:
            changes.append(Change("combo", before, after, index=item.index))
    has_macro_target = config.macro_buffer is not None or config.macros is not None
    if has_macro_target and current["macro_buffer"] != desired["macro_buffer"]:
        changes.append(Change("macro_buffer", current["macro_buffer"], desired["macro_buffer"]))
    return changes
