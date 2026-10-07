"""Strict partial configuration and side-effect-free pointer/keymap planning."""

from __future__ import annotations

import copy
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

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"layer": self.layer}
        for field in ("buttons", "dial"):
            bindings = getattr(self, field)
            if bindings:
                result[field] = {name: f"0x{code:04X}" for name, code in bindings}
        return result


@dataclass(frozen=True)
class NapeConfig:
    orientation: int | None = None
    dpi_index: int | None = None
    dpi_values: tuple[int, ...] | None = None
    polling_rate: int | None = None
    layers: tuple[LayerConfig, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"schema_version": 1}
        for name in POINTER_FIELDS:
            value = getattr(self, name)
            if value is not None:
                result[name] = list(value) if isinstance(value, tuple) else value
        if self.layers:
            result["layers"] = [layer.to_dict() for layer in self.layers]
        return result


@dataclass(frozen=True)
class Change:
    field: str
    before: int
    after: int
    index: int | None = None
    layer: int | None = None
    binding: str | None = None

    def to_dict(self) -> dict[str, Any]:
        keymap = self.field in ("buttons", "dial")
        return {
            "setting": self.setting,
            "before": f"0x{self.before:04X}" if keymap else self.before,
            "after": f"0x{self.after:04X}" if keymap else self.after,
        }

    @property
    def setting(self) -> str:
        if self.field in ("buttons", "dial"):
            return f"layers[{self.layer}].{self.field}.{self.binding}"
        return f"{self.field}[{self.index}]" if self.index is not None else self.field


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
        if not isinstance(entry, dict) or set(entry) - {"layer", "buttons", "dial"}:
            raise ValueError("each layer accepts only layer, buttons, and dial fields")
        layer = _integer(entry.get("layer"), "layer", 0, 8)
        if layer in seen:
            raise ValueError(f"duplicate layer index: {layer}")
        seen.add(layer)
        if "buttons" not in entry and "dial" not in entry:
            raise ValueError(f"layer {layer} must specify buttons or dial bindings")
        buttons = _bindings(entry["buttons"], "buttons", BUTTON_ORDER) if "buttons" in entry else ()
        dial = _bindings(entry["dial"], "dial", DIAL_ORDER) if "dial" in entry else ()
        result.append(LayerConfig(layer, buttons, dial))
    return tuple(sorted(result, key=lambda entry: entry.layer))


def validate_config(data: object) -> NapeConfig:
    if not isinstance(data, dict):
        raise ValueError("configuration must be a JSON object")
    unknown = set(data) - {"schema_version", "layers", *POINTER_FIELDS}
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(sorted(map(str, unknown)))}")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if not any(name in data for name in (*POINTER_FIELDS, "layers")):
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
    return NapeConfig(orientation, dpi_index, dpi_values, polling_rate, layers)


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
    return changes
