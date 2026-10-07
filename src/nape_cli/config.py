"""Strict partial configuration and side-effect-free settings/keymap planning."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocol import orientation_units
from .snapshot import BUTTON_ORDER, POLLING_RATES

POINTER_FIELDS = ("dpi_values", "dpi_index", "orientation", "polling_rate")
DIAL_ORDER = ("ccw", "cw")


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
class NapeConfig:
    orientation: int | None = None
    dpi_index: int | None = None
    dpi_values: tuple[int, ...] | None = None
    polling_rate: int | None = None
    layers: tuple[LayerConfig, ...] = ()
    macro_buffer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"schema_version": 1}
        for name in POINTER_FIELDS:
            value = getattr(self, name)
            if value is not None:
                result[name] = list(value) if isinstance(value, tuple) else value
        if self.layers:
            result["layers"] = [layer.to_dict() for layer in self.layers]
        if self.macro_buffer is not None:
            result["macro_buffer"] = self.macro_buffer
        return result


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
        return f"{self.field}[{self.index}]" if self.index is not None else self.field


def _macro_summary(value: str) -> dict[str, Any]:
    raw = bytes.fromhex(value)
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


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
    unknown = set(data) - {"schema_version", "layers", "macro_buffer", *POINTER_FIELDS}
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(sorted(map(str, unknown)))}")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if not any(name in data for name in (*POINTER_FIELDS, "layers", "macro_buffer")):
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
    layers = _layers(data["layers"]) if "layers" in data else ()
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
    return NapeConfig(orientation, dpi_index, dpi_values, polling_rate, layers, macro_buffer)


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
    result = {field: copy.deepcopy(current[field]) for field in POINTER_FIELDS}
    result.update({key: value for key, value in config.to_dict().items() if key in POINTER_FIELDS})
    if "layers" in current:
        result["layers"] = copy.deepcopy(current["layers"])
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
    if config.macro_buffer is not None:
        if "macro_buffer" not in current:
            raise ValueError("a macro-buffer snapshot is required to plan macro changes")
        if len(config.macro_buffer) != len(current["macro_buffer"]):
            raise ValueError(
                "macro_buffer must contain exactly the device's full macro-buffer size"
            )
        result["macro_buffer"] = config.macro_buffer
    return result


def plan_changes(config: NapeConfig, current: dict[str, Any]) -> list[Change]:
    desired = desired_settings(config, current)
    changes = []
    for field in POINTER_FIELDS:
        if field == "dpi_values":
            for index, (before, after) in enumerate(
                zip(current[field], desired[field], strict=True)
            ):
                if before != after:
                    changes.append(Change(field, before, after, index))
        elif current[field] != desired[field]:
            changes.append(Change(field, current[field], desired[field]))
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
    if config.macro_buffer is not None and current["macro_buffer"] != desired["macro_buffer"]:
        changes.append(Change("macro_buffer", current["macro_buffer"], desired["macro_buffer"]))
    return changes
