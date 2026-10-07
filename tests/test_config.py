import pytest

from nape_cli import cli
from nape_cli.config import load_config, plan_changes, validate_config

CURRENT = {
    "orientation": 90,
    "dpi_index": 2,
    "dpi_values": [450, 800, 1600, 3200, 4000],
    "polling_rate": 1000,
    "supported_polling_rates": [1000, 500, 125],
}


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"schema_version": True, "orientation": 90},
        {"schema_version": 2, "orientation": 90},
        {"schema_version": 1},
        {"schema_version": 1, "battery_percent": 100},
        {"schema_version": 1, "orientation": None},
        {"schema_version": 1, "orientation": 360},
        {"schema_version": 1, "orientation": 89},
        {"schema_version": 1, "orientation": "90"},
        {"schema_version": 1, "dpi_index": True},
        {"schema_version": 1, "dpi_index": -1},
        {"schema_version": 1, "dpi_index": 5},
        {"schema_version": 1, "dpi_values": [100] * 4},
        {"schema_version": 1, "dpi_values": [100, 100, 100, 100, 0]},
        {"schema_version": 1, "dpi_values": [100, 100, 100, 100, 65536]},
        {"schema_version": 1, "dpi_values": [100, 100, 100, 100, 100.0]},
        {"schema_version": 1, "polling_rate": 300},
    ],
)
def test_invalid_configs_are_rejected(data: object) -> None:
    with pytest.raises(ValueError):
        validate_config(data)


def test_partial_config_changes_only_specified_settings() -> None:
    config = validate_config({"schema_version": 1, "orientation": 135})
    changes = plan_changes(config, CURRENT)
    assert [c.to_dict() for c in changes] == [
        {"setting": "orientation", "before": 90, "after": 135}
    ]
    assert CURRENT["dpi_values"] == [450, 800, 1600, 3200, 4000]


def test_dpi_diff_contains_only_changed_stages() -> None:
    config = validate_config({"schema_version": 1, "dpi_values": [450, 900, 1600, 3200, 4000]})
    changes = plan_changes(config, CURRENT)
    assert [c.to_dict() for c in changes] == [
        {"setting": "dpi_values[1]", "before": 800, "after": 900}
    ]


def test_noop_config_has_empty_diff() -> None:
    assert plan_changes(validate_config({"schema_version": 1, "orientation": 90}), CURRENT) == []


def test_plan_rejects_rate_not_supported_by_device() -> None:
    config = validate_config({"schema_version": 1, "polling_rate": 8000})
    with pytest.raises(ValueError, match="support"):
        plan_changes(config, CURRENT)


def test_duplicate_fields_are_rejected(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version": 1, "orientation": 90, "orientation": 135}')
    with pytest.raises(ValueError, match="duplicate"):
        load_config(path)


def test_offline_validation_does_not_select_hardware(monkeypatch, tmp_path, capsys) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version": 1, "dpi_index": 1}')
    monkeypatch.setattr(cli, "_select_receiver", lambda _: pytest.fail("hardware queried"))
    assert cli._run(cli._parser().parse_args(["validate", str(path)])) == 0
    assert "valid" in capsys.readouterr().out


def test_invalid_plan_does_not_select_hardware(monkeypatch, tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version": 1, "orientation": 1}')
    monkeypatch.setattr(cli, "_select_receiver", lambda _: pytest.fail("hardware queried"))
    with pytest.raises(ValueError):
        cli._run(cli._parser().parse_args(["plan", str(path)]))
