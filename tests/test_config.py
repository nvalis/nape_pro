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
        {"schema_version": 1, "macro_buffer": None},
        {"schema_version": 1, "macro_buffer": "a"},
        {"schema_version": 1, "macro_buffer": "gg"},
        {"schema_version": 1, "layers": [{"layer": 0, "orientation": 91}]},
        {"schema_version": 1, "layers": [{"layer": 0, "orientation": True}]},
        {"schema_version": 1, "layers": [{"layer": 0}]},
        {"schema_version": 1, "layers": [{"layer": 0, "unknown": 1}]},
        {"schema_version": 1, "active_layer": True},
        {"schema_version": 1, "gesture": {"bad": "0x0001"}},
        {
            "schema_version": 1,
            "tap_holds": [{"layer": 0, "button": "M1", "tap": "0x0000", "held": "0x0000"}],
        },
        {
            "schema_version": 1,
            "combos": [{"index": 0, "layer": 0, "columns": 0, "tap": "0x0001", "held": "0x0002"}],
        },
        {"schema_version": 1, "macros": [[{"type": "tap", "keycode": "0x0100"}]]},
        {"schema_version": 1, "macros": [[{"type": "text", "text": "bad\u0000text"}]]},
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


def test_launcher_advanced_config_normalizes_wire_values() -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "active_layer": 2,
            "gesture": {"up": "0x00E9"},
            "force_gesture_scroll": {"gesture": 1, "scroll": 0},
            "tap_holds": [{"layer": 0, "button": "M1", "tap": "0x0004", "held": "0x00E1"}],
            "combos": [
                {
                    "index": 1,
                    "layer": 2,
                    "columns": 5,
                    "tap": "0x0004",
                    "held": "0x00E1",
                }
            ],
            "macros": [[{"type": "tap", "keycode": "0x0004"}]],
        }
    )
    normalized = config.to_dict()
    assert normalized["active_layer"] == 2
    assert normalized["gesture"] == {"up": "0x00E9"}
    assert normalized["tap_holds"][0]["held"] == "0x00E1"
    assert normalized["combos"][0]["timeout_ms"] == 200
    assert normalized["macros"] == [[{"type": "tap", "keycode": "0x0004"}]]


def test_advanced_plan_merges_only_requested_values() -> None:
    current = {
        **CURRENT,
        "active_layer": 0,
        "gesture": {"up": 0, "down": 0, "left": 0, "right": 0},
        "force_gesture_scroll": {"gesture": 0, "scroll": 0},
        "tap_holds": {"0:M1": None},
        "combos": {"0": {"layer": 0, "columns": 3, "tap": 4, "held": 5, "timeout_ms": 200}},
        "macro_count": 1,
        "macro_buffer_size": 32,
        "via_protocol_version": 12,
        "macro_buffer": bytes(32).hex(),
    }
    config = validate_config(
        {
            "schema_version": 1,
            "active_layer": 1,
            "gesture": {"up": "0x0001"},
            "tap_holds": [{"layer": 0, "button": "M1", "tap": "0x0004", "held": "0x00E1"}],
            "combos": [{"index": 0, "layer": 0, "columns": 3, "tap": "0x0006", "held": "0x0005"}],
            "macros": [[{"type": "tap", "keycode": "0x0004"}]],
        }
    )
    changes = plan_changes(config, current)
    assert [change.field for change in changes] == [
        "active_layer",
        "gesture",
        "tap_hold",
        "combo",
        "macro_buffer",
    ]
    assert changes[-1].after.startswith("01010400")


def test_combo_create_requires_confirmed_empty_slot() -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "combos": [
                {
                    "index": 3,
                    "layer": 0,
                    "columns": 3,
                    "tap": "0x0004",
                    "held": "0x0005",
                    "create": True,
                }
            ],
        }
    )
    current = {**CURRENT, "combos": {"3": None}}
    assert plan_changes(config, current)[0].field == "combo"
    with pytest.raises(ValueError, match="refusing to overwrite"):
        plan_changes(config, {**current, "combos": {"3": {"tap": 1}}})


def test_tap_hold_create_requires_confirmed_empty_target() -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "tap_holds": [
                {
                    "layer": 0,
                    "button": "M1",
                    "tap": "0x0004",
                    "held": "0x00E1",
                    "create": True,
                }
            ],
        }
    )
    current = {**CURRENT, "tap_holds": {"0:M1": None}}
    assert plan_changes(config, current)[0].field == "tap_hold"
    with pytest.raises(ValueError, match="refusing to overwrite"):
        plan_changes(config, {**current, "tap_holds": {"0:M1": {"tap": 4, "held": 5}}})


def test_macro_buffer_is_normalized_and_compared_as_binary() -> None:
    config = validate_config({"schema_version": 1, "macro_buffer": "A0b1"})
    assert config.to_dict()["macro_buffer"] == "a0b1"
    changes = plan_changes(
        config,
        {**CURRENT, "macro_buffer": "0000"},
    )
    assert changes[0].field == "macro_buffer"
    assert changes[0].to_dict()["after"] == {
        "bytes": 2,
        "sha256": "42dec0ac7505b626485e54ce1d1ee39459beb0c3368cf2b67f9bcd52246b81f6",
    }


def test_macro_buffer_must_match_device_capacity() -> None:
    config = validate_config({"schema_version": 1, "macro_buffer": "00"})
    with pytest.raises(ValueError, match="full macro-buffer size"):
        plan_changes(config, {**CURRENT, "macro_buffer": "0000"})


def test_layer_orientation_is_part_of_layer_diff() -> None:
    current = {
        **CURRENT,
        "layers": [
            {
                "layer": i,
                "buttons": {"M1": "0x0000"},
                "dial": {"ccw": "0x0000", "cw": "0x0000"},
                "orientation": 0,
            }
            for i in range(9)
        ],
    }
    config = validate_config({"schema_version": 1, "layers": [{"layer": 2, "orientation": 90}]})
    change = plan_changes(config, current)[0]
    assert change.setting == "layers[2].orientation"
    assert change.before == 0 and change.after == 90


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
