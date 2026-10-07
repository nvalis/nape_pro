"""Source-backed custom DPI, cycling-stage count, sleep, and macro transaction tests."""

import json
from types import SimpleNamespace

import pytest
from test_apply import WritableNape
from test_snapshot import RECEIVER

from nape_cli import apply as apply_module
from nape_cli import cli, snapshot
from nape_cli.apply import apply_config, encode_change
from nape_cli.channel import request
from nape_cli.config import Change, desired_settings, validate_config


@pytest.fixture
def device(monkeypatch, tmp_path) -> WritableNape:
    fake = WritableNape()
    fake.backup_path = tmp_path / "before.json"
    monkeypatch.setattr(apply_module, "hid_backend", lambda: SimpleNamespace(device=lambda: fake))
    monkeypatch.setattr(snapshot, "hid_backend", lambda: SimpleNamespace(device=lambda: fake))
    monkeypatch.setattr(apply_module.time, "sleep", lambda _: None)
    return fake


def test_new_reads_match_launcher_offsets_and_preserve_raw(device) -> None:
    device.custom_dpi = 0x1234
    device.dpi_stage_count = 3
    result = snapshot.read_snapshot(RECEIVER, include_device_settings=True)
    assert result["custom_dpi"] == 0x1234
    assert result["dpi_stage_count"] == 3
    assert result["sleep"] == {"backlight": 0x0123, "sleep": 0x0456, "magnet_scan": 0x0789}
    for command in ("a7 36", "a7 3c", "a7 0b"):
        assert command in result["raw"]
    assert device.closed


def test_zero_echoed_optional_settings_are_unavailable_but_sleep_remains_readable(device) -> None:
    device.custom_dpi = 0
    device.dpi_stage_count = 0
    result = snapshot.read_snapshot(RECEIVER, include_device_settings=True)
    assert result["custom_dpi"] is None
    assert result["dpi_stage_count"] is None
    assert result["sleep"] == device.sleep_settings
    assert result["raw"]["a7 36"] == bytes.fromhex("a7 36").ljust(32, b"\x00").hex(" ")
    assert result["raw"]["a7 3c"] == bytes.fromhex("a7 3c").ljust(32, b"\x00").hex(" ")
    assert "a7 0b" in result["raw"]


def test_standard_status_avoids_unverified_device_settings_queries(device) -> None:
    result = snapshot.read_snapshot(RECEIVER)
    assert "custom_dpi" not in result and "sleep" not in result
    assert not any(p[:2] in (b"\xa7\x36", b"\xa7\x3c", b"\xa7\x0b") for p in device.requests)


@pytest.mark.parametrize("count", [6, 255])
def test_invalid_reported_stage_count_aborts_before_writes(device, count) -> None:
    device.dpi_stage_count = count
    with pytest.raises(ValueError, match="invalid DPI stage count"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "custom_dpi": 900}),
            write=True,
            backup=device.backup_path,
        )
    assert not device.setters and not device.backup_path.exists() and device.closed


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("custom_dpi", 900, "no usable custom DPI value"),
        ("dpi_stage_count", 3, "no usable DPI stage count"),
    ],
)
def test_unavailable_settings_cannot_be_planned_or_written(device, field, value, error) -> None:
    device.custom_dpi = 0
    device.dpi_stage_count = 0
    config = validate_config({"schema_version": 1, field: value})
    with pytest.raises(ValueError, match=error):
        apply_config(RECEIVER, config, write=True, backup=device.backup_path)
    assert not device.setters and not device.backup_path.exists() and device.closed


@pytest.mark.parametrize(
    "config",
    [
        {"custom_dpi": 0},
        {"custom_dpi": 65536},
        {"custom_dpi": True},
        {"dpi_stage_count": 0},
        {"dpi_stage_count": 6},
        {"dpi_stage_count": False},
        {"dpi_stage_count": 2, "dpi_index": 2},
        {"sleep": {}},
        {"sleep": None},
        {"sleep": {"sleep": -1}},
        {"sleep": {"sleep": 65536}},
        {"sleep": {"sleep": True}},
        {"sleep": {"magnetScan": 1}},
        {"sleep": {"sleep": "30"}},
        {"profile": 1},
        {"firmware": "new"},
    ],
)
def test_invalid_or_unknown_configuration_is_rejected(config) -> None:
    with pytest.raises(ValueError):
        validate_config({"schema_version": 1, **config})


def test_partial_device_settings_merge_preserves_unspecified_values(device) -> None:
    current = snapshot.read_snapshot(RECEIVER, include_device_settings=True)
    config = validate_config({"schema_version": 1, "custom_dpi": 1000, "sleep": {"sleep": 30}})
    expected = desired_settings(config, current)
    assert expected["custom_dpi"] == 1000
    assert expected["dpi_stage_count"] == 5
    assert expected["sleep"] == {"backlight": 0x0123, "sleep": 30, "magnet_scan": 0x0789}
    assert current["sleep"]["sleep"] == 0x0456
    assert validate_config(config.to_dict()) == config


@pytest.mark.parametrize(
    "field,value", [("custom_dpi", 900), ("dpi_stage_count", 4), ("sleep", {"sleep": 30})]
)
def test_new_settings_dry_run_sends_only_reads(device, field, value) -> None:
    result = apply_config(RECEIVER, validate_config({"schema_version": 1, field: value}))
    assert result["mode"] == "dry-run"
    assert result["changes"][0]["setting"] == field
    assert not device.setters and not device.backup_path.exists()


def test_sleep_plan_works_when_other_optional_getters_echo_zero(device) -> None:
    device.custom_dpi = 0
    device.dpi_stage_count = 0
    result = apply_config(RECEIVER, validate_config({"schema_version": 1, "sleep": {"sleep": 30}}))
    assert result["mode"] == "dry-run"
    assert result["changes"][0]["setting"] == "sleep"
    assert not device.setters and not device.backup_path.exists()


def test_sleep_and_stage_selection_plan_with_unavailable_optional_count(device) -> None:
    device.custom_dpi = 0
    device.dpi_stage_count = 0
    result = apply_config(
        RECEIVER,
        validate_config({"schema_version": 1, "dpi_index": 1, "sleep": {"sleep": 30}}),
    )
    assert [change["setting"] for change in result["changes"]] == ["dpi_index", "sleep"]
    assert not device.setters and not device.backup_path.exists()


def test_new_setters_use_launcher_little_endian_and_verify_all_device_fields(device) -> None:
    original_sleep = dict(device.sleep_settings)
    config = validate_config(
        {
            "schema_version": 1,
            "custom_dpi": 0x1234,
            "dpi_stage_count": 4,
            "sleep": {"sleep": 0x4567},
        }
    )
    result = apply_config(RECEIVER, config, write=True, backup=device.backup_path)
    assert result["verified"]
    assert [p[1:9] for p in device.setters] == [
        bytes.fromhex("a7 3d 04 00 00 00 00 00"),
        bytes.fromhex("a7 37 34 12 00 00 00 00"),
        bytes.fromhex("a7 0c 23 01 67 45 89 07"),
    ]
    assert device.sleep_settings["backlight"] == original_sleep["backlight"]
    assert device.sleep_settings["magnet_scan"] == original_sleep["magnet_scan"]
    backup = json.loads(device.backup_path.read_text())
    assert backup["custom_dpi"] == 800 and backup["dpi_stage_count"] == 5
    assert backup["sleep"] == original_sleep and len(backup["layers"]) == 9


@pytest.mark.parametrize(
    "old_count,new_count,old_index,new_index,commands",
    [
        (2, 5, 1, 4, [0x3D, 0x22]),
        (5, 2, 4, 1, [0x22, 0x3D]),
    ],
)
def test_count_and_selection_changes_are_ordered_safely(
    device, old_count, new_count, old_index, new_index, commands
) -> None:
    device.dpi_stage_count = old_count
    device.dpi_index = old_index
    config = validate_config(
        {"schema_version": 1, "dpi_stage_count": new_count, "dpi_index": new_index}
    )
    assert apply_config(RECEIVER, config, write=True, backup=device.backup_path)["verified"]
    assert [p[2] for p in device.setters] == commands


def test_rejected_count_growth_stops_before_selecting_a_disabled_stage(device) -> None:
    device.dpi_stage_count = 2
    device.dpi_index = 1
    device.reject_writes = True
    config = validate_config({"schema_version": 1, "dpi_stage_count": 5, "dpi_index": 4})
    with pytest.raises(RuntimeError, match="1/2 write attempts.*stage count did not change"):
        apply_config(RECEIVER, config, write=True, backup=device.backup_path)
    assert len(device.setters) == 1 and device.setters[0][2] == 0x3D
    assert device.dpi_index == 1 and device.closed


def test_rejected_stage_selection_stops_before_shrinking_count(device) -> None:
    device.dpi_index = 4
    device.reject_writes = True
    config = validate_config({"schema_version": 1, "dpi_stage_count": 2, "dpi_index": 1})
    with pytest.raises(
        RuntimeError, match="1/2 write attempts.*active DPI stage would be disabled"
    ):
        apply_config(RECEIVER, config, write=True, backup=device.backup_path)
    assert len(device.setters) == 1 and device.setters[0][2] == 0x22
    assert device.dpi_stage_count == 5 and device.closed


def test_shrinking_count_requires_explicit_valid_selection(device) -> None:
    device.dpi_index = 4
    with pytest.raises(ValueError, match="select a dpi_index"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "dpi_stage_count": 2}),
            write=True,
            backup=device.backup_path,
        )
    assert not device.setters and not device.backup_path.exists()


def test_unspecified_custom_dpi_drift_fails_sleep_write_verification(device, monkeypatch) -> None:
    monkeypatch.setattr(apply_module.time, "sleep", lambda _: setattr(device, "custom_dpi", 999))
    with pytest.raises(RuntimeError, match="read-back mismatch: custom_dpi"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "sleep": {"sleep": 30}}),
            write=True,
            backup=device.backup_path,
        )
    assert device.backup_path.exists() and device.closed


@pytest.mark.parametrize("field", ["custom_dpi", "sleep"])
def test_new_setter_ack_timeout_is_not_reported_as_success(device, monkeypatch, field) -> None:
    original = device.read
    monkeypatch.setattr(
        device, "read", lambda size, timeout: b"" if device.setters else original(size, timeout)
    )
    config = validate_config(
        {"schema_version": 1, field: 900 if field == "custom_dpi" else {"sleep": 30}}
    )
    with pytest.raises(RuntimeError, match="ACK timed out.*No automatic rollback"):
        apply_config(RECEIVER, config, write=True, backup=device.backup_path, timeout_ms=1)
    assert len(device.setters) == 1 and device.closed


def test_sleep_status_failure_stops_without_retry(device, monkeypatch) -> None:
    original = device.write

    def write(packet: bytes) -> int:
        count = original(packet)
        if packet[1:3] == b"\xa7\x0c":
            device.response = bytes.fromhex("a7 0c 01").ljust(32, b"\x00")
        return count

    monkeypatch.setattr(device, "write", write)
    with pytest.raises(RuntimeError, match="returned status 1"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "sleep": {"sleep": 30}}),
            write=True,
            backup=device.backup_path,
        )
    assert len(device.setters) == 1 and device.closed


@pytest.mark.parametrize("payload", [b"\xa7\x37", b"\xa7\x3d", b"\xa7\x0c", b"\x10", b"\x0f"])
def test_read_channel_still_rejects_new_setters_and_macro_reset(payload) -> None:
    with pytest.raises(ValueError, match="read-only allowlist"):
        request(object(), payload)


@pytest.mark.parametrize("payload", [b"\xa7\x36\x00", b"\xa7\x3c\x01", b"\xa7\x0b\x01"])
def test_new_read_commands_reject_extra_arguments(payload) -> None:
    with pytest.raises(ValueError, match="takes no arguments"):
        request(object(), payload)


def macro_config():
    return validate_config(
        {"schema_version": 1, "macros": [[{"type": "text", "text": "hello"}], []]}
    )


def test_macro_transaction_keeps_invalidation_marker_until_final_packet(
    device, monkeypatch
) -> None:
    original = device.write
    observations = []

    def write(packet: bytes) -> int:
        count = original(packet)
        if packet[1] == 0x0F:
            observations.append(device.macro_buffer[-1])
        return count

    monkeypatch.setattr(device, "write", write)
    assert apply_config(RECEIVER, macro_config(), write=True, backup=device.backup_path)["verified"]
    assert observations == [255, 255, 255, 0]
    # 28 + 27 data bytes; final byte is exclusively set by the finalization packet.
    assert [p[4] for p in device.setters if p[1] == 0x0F] == [1, 28, 27, 1]


@pytest.mark.parametrize("attempt", [1, 2, 3, 4, 5])
def test_macro_transfer_failure_never_retries_or_finalizes_a_partial_buffer(
    device, attempt
) -> None:
    device.fail_write_number = attempt
    with pytest.raises(RuntimeError, match=f"{attempt}/5 write attempts.*No automatic rollback"):
        apply_config(RECEIVER, macro_config(), write=True, backup=device.backup_path)
    assert len(device.setters) == attempt and device.backup_path.exists() and device.closed
    if 2 < attempt:
        assert device.macro_buffer[-1] == 255


def test_macro_mismatched_echo_aborts_before_finalization(device, monkeypatch) -> None:
    original = device.write

    def write(packet: bytes) -> int:
        count = original(packet)
        if len(device.setters) == 3:
            bad = bytearray(device.response)
            bad[4] ^= 1
            device.response = bytes(bad)
        return count

    monkeypatch.setattr(device, "write", write)
    with pytest.raises(RuntimeError, match="did not echo the exact chunk"):
        apply_config(RECEIVER, macro_config(), write=True, backup=device.backup_path)
    assert len(device.setters) == 3 and device.macro_buffer[-1] == 255 and device.closed


def test_macro_reset_timeout_aborts_before_invalidation(device, monkeypatch) -> None:
    original = device.read
    monkeypatch.setattr(
        device, "read", lambda size, timeout: b"" if device.setters else original(size, timeout)
    )
    with pytest.raises(RuntimeError, match="0x10 ACK timed out"):
        apply_config(RECEIVER, macro_config(), write=True, backup=device.backup_path, timeout_ms=1)
    assert len(device.setters) == 1 and device.closed


def test_raw_macro_final_byte_must_be_zero_before_any_setter(device) -> None:
    target = bytes(55) + b"\x01"
    with pytest.raises(ValueError, match="final macro-buffer byte must be zero"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "macro_buffer": target.hex()}),
            write=True,
            backup=device.backup_path,
        )
    assert not device.setters and not device.backup_path.exists()


def test_macro_readback_mismatch_is_not_success(device, monkeypatch) -> None:
    def drift(_: float) -> None:
        device.macro_buffer = b"X" + device.macro_buffer[1:]

    monkeypatch.setattr(apply_module.time, "sleep", drift)
    with pytest.raises(RuntimeError, match="read-back mismatch: macro_buffer"):
        apply_config(RECEIVER, macro_config(), write=True, backup=device.backup_path)
    assert len(device.setters) == 5 and device.backup_path.exists() and device.closed


def test_macro_noop_never_resets_store(device) -> None:
    config = validate_config({"schema_version": 1, "macros": [[], []]})
    assert apply_config(RECEIVER, config, write=True, backup=device.backup_path)["mode"] == "no-op"
    assert not device.setters and not device.backup_path.exists()


@pytest.mark.parametrize(
    "change",
    [
        Change("custom_dpi", 800, 0),
        Change("custom_dpi", 800, True),
        Change("custom_dpi", 800, 65536),
        Change("custom_dpi", 800, 900, layer=0),
        Change("dpi_stage_count", 5, 0),
        Change("dpi_stage_count", 5, 6),
        Change("dpi_stage_count", 5, 3, index=0),
        Change("sleep", {}, {"sleep": 30}),
        Change("sleep", {}, {"backlight": 0, "sleep": True, "magnet_scan": 0}),
        Change("sleep", {}, {"backlight": 0, "sleep": 65536, "magnet_scan": 0}),
    ],
)
def test_new_encoders_reject_unvalidated_values_or_addresses(change) -> None:
    with pytest.raises(ValueError):
        encode_change(change)


def test_sleep_zero_values_roundtrip_without_touching_unspecified_fields(device) -> None:
    original = dict(device.sleep_settings)
    config = validate_config({"schema_version": 1, "sleep": {"sleep": 0}})
    assert apply_config(RECEIVER, config, write=True, backup=device.backup_path)["verified"]
    assert device.sleep_settings == {**original, "sleep": 0}


def test_sleep_echo_like_zero_timers_are_unusable_as_in_launcher(device) -> None:
    device.sleep_settings.update({"backlight": 0, "sleep": 0})
    with pytest.raises(ValueError, match="sleep query returned no usable state"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "custom_dpi": 900}),
            write=True,
            backup=device.backup_path,
        )
    assert not device.setters and not device.backup_path.exists() and device.closed


def test_sleep_config_that_would_break_readback_is_rejected_before_writing(device) -> None:
    config = validate_config({"schema_version": 1, "sleep": {"backlight": 0, "sleep": 0}})
    with pytest.raises(ValueError, match="cannot both be zero"):
        apply_config(RECEIVER, config, write=True, backup=device.backup_path)
    assert not device.setters and not device.backup_path.exists() and device.closed


def test_unavailable_extended_getter_prevents_all_writes(device, monkeypatch) -> None:
    original = device.read

    def read(size: int, timeout: int) -> bytes:
        return b"" if device.requests[-1][:2] == b"\xa7\x36" else original(size, timeout)

    monkeypatch.setattr(device, "read", read)
    with pytest.raises(TimeoutError):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "custom_dpi": 900}),
            write=True,
            backup=device.backup_path,
            timeout_ms=1,
        )
    assert not device.setters and not device.backup_path.exists() and device.closed


def test_advanced_export_includes_all_new_settings(device, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_select_receiver", lambda _: RECEIVER)
    path = tmp_path / "advanced.json"
    assert cli._run(cli._parser().parse_args(["export", str(path), "--advanced"])) == 0
    data = json.loads(path.read_text())
    assert data["custom_dpi"] == 800 and data["dpi_stage_count"] == 5
    assert data["sleep"] == device.sleep_settings
