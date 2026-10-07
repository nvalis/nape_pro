"""Strict partial pointer configuration and side-effect-free change planning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocol import orientation_units
from .snapshot import POLLING_RATES

POINTER_FIELDS = ("dpi_values", "dpi_index", "orientation", "polling_rate")


@dataclass(frozen=True)
class PointerConfig:
    orientation: int | None = None
    dpi_index: int | None = None
    dpi_values: tuple[int, ...] | None = None
    polling_rate: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"schema_version": 1}
        for name in POINTER_FIELDS:
            value = getattr(self, name)
            if value is not None:
                result[name] = list(value) if isinstance(value, tuple) else value
        return result


@dataclass(frozen=True)
class Change:
    field: str
    before: int
    after: int
    index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"setting": self.setting, "before": self.before, "after": self.after}

    @property
    def setting(self) -> str:
        return f"{self.field}[{self.index}]" if self.index is not None else self.field


def _integer(value: object, name: str, low: int, high: int) -> int:
    # bool is an int subclass but not a sensible hardware setting.
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def validate_config(data: object) -> PointerConfig:
    if not isinstance(data, dict):
        raise ValueError("configuration must be a JSON object")
    unknown = set(data) - {"schema_version", *POINTER_FIELDS}
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(sorted(map(str, unknown)))}")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if not any(name in data for name in POINTER_FIELDS):
        raise ValueError("configuration must specify at least one pointer setting")

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
    return PointerConfig(orientation, dpi_index, dpi_values, polling_rate)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON field: {name}")
        result[name] = value
    return result


def load_config(path: Path) -> PointerConfig:
    return validate_config(
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    )


def desired_settings(config: PointerConfig, current: dict[str, Any]) -> dict[str, Any]:
    """Merge only pointer fields; omitted settings retain their current values."""
    config = validate_config(config.to_dict())
    if (
        config.polling_rate is not None
        and config.polling_rate not in current["supported_polling_rates"]
    ):
        raise ValueError(f"device does not report support for {config.polling_rate} Hz")
    result = {field: current[field] for field in POINTER_FIELDS}
    result.update({key: value for key, value in config.to_dict().items() if key in POINTER_FIELDS})
    return result


def plan_changes(config: PointerConfig, current: dict[str, Any]) -> list[Change]:
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
    return changes
