"""1.3.0 packet contracts from the binary, with independent status/compaction fakes."""

import json
from types import SimpleNamespace

import pytest
from test_apply import USB, WritableNape
from test_snapshot import RECEIVER, FakeNape

from nape_cli import apply as apply_module
from nape_cli import cli, snapshot
from nape_cli.apply import apply_config, encode_change
from nape_cli.channel import request
from nape_cli.config import Change, plan_changes, validate_config
from nape_cli.firmware import capabilities
from nape_cli.snapshot import BUTTON_ORDER


class Nape130(WritableNape):
    def __init__(self):
        super().__init__()
        self.firmware = b"v1.3.0-ZK"
        self.default_layer = self.current_layer = 1
        self.layer_orientations[1] = 90
        self.custom_dpi = 400
        self.scroll_dpi = 400
        self.dpi_stage_count = 3
        self.combos = {}
        self.status_failure = None
        self.omit_ack = None


@pytest.fixture
def nape(monkeypatch, tmp_path):
    device = Nape130()
    device.backup_path = tmp_path / "before.json"

    def backend():
        return SimpleNamespace(device=lambda: device)

    monkeypatch.setattr(apply_module, "hid_backend", backend)
    monkeypatch.setattr(snapshot, "hid_backend", backend)
    monkeypatch.setattr(apply_module.time, "sleep", lambda _: None)
    return device


def record(tap=4):
    return {"layer": 0, "columns": 3, "tap": tap, "held": 5, "timeout_ms": 200}


def combo(index, tap=4, **kwargs):
    return {
        "index": index,
        "layer": 0,
        "columns": 3,
        "tap": f"0x{tap:04X}",
        "held": "0x0005",
        "timeout_ms": 200,
        **kwargs,
    }


def apply(device, data, transport=RECEIVER):
    return apply_config(
        transport,
        validate_config({"schema_version": 1, **data}),
        write=True,
        backup=device.backup_path,
        timeout_ms=5,
    )


def test_firmware_support_is_exact_and_fail_closed():
    assert capabilities("v1.3.0-ZK Aug 20 2026 08:35:53").supported
    for version in ("v1.1.6-ZK", "v1.3.1-ZK", "v1.3.0", "v1.30.0-ZK", "v9.0.0-ZK"):
        assert not capabilities(version).supported


def test_new_getters_and_layer_angles_decode_and_preserve_raw(nape):
    nape.current_layer = 2
    nape.layer_orientations[2] = 135
    nape.scroll_dpi = 80
    state = snapshot.read_snapshot(
        RECEIVER, include_device_settings=True, include_layer_orientations=True
    )
    assert state["active_layer"] == 2 and state["default_layer"] == 1
    assert state["custom_dpi"] == 400 and state["scroll_dpi"] == 80
    assert state["layer_orientations"][2]["orientation"] == 135
    assert state["capabilities"]["combo_capacity"] == 30
    assert state["raw"]["a7 35"][:8] == "a7 35 01"
    assert state["raw"]["a7 3a"][:11] == "a7 3a 50 00"
    assert not nape.setters


@pytest.mark.parametrize("version", [b"v0.9.0-ZK", b"v1.3.1-ZK", b"v1.3.0"])
def test_unsupported_firmware_stops_before_configuration_queries(nape, version):
    nape.firmware = version
    with pytest.raises(ValueError, match="only v1.3.0-ZK is supported"):
        snapshot.read_snapshot(RECEIVER, include_device_settings=True)
    assert [packet[0] for packet in nape.requests] == [0xB2, 0xA1]
    assert nape.closed and not nape.setters


def test_complete_inventory_covers_both_stores_and_accepts_echoed_absence(nape):
    nape.combos = {0: record()}
    nape.tap_holds[(2, 4)] = {"tap": 4, "held": 5}
    state = snapshot.read_snapshot(RECEIVER, include_records=True)
    assert state["record_inventory"]
    assert len(state["combos"]) == 30 and len(state["tap_holds"]) == 63
    assert state["combos"]["0"] == record() and state["combos"]["1"] is None
    assert state["tap_holds"]["2:M1"] == {"tap": 4, "held": 5}
    assert state["tap_holds"]["8:Press"] is None
    assert len([p for p in nape.requests if p[:2] == b"\xa7\x28"]) == 30
    assert len([p for p in nape.requests if p[:2] == b"\xa7\x26"]) == 63


def test_record_inventory_is_automatic_for_targeted_130_plans(nape):
    state = snapshot.read_snapshot(RECEIVER, combo_targets=(0,))
    assert state["record_inventory"] and len(state["combos"]) == 30
    config = validate_config({"schema_version": 1, "combos": [combo(0)]})
    with pytest.raises(ValueError, match="use create explicitly"):
        plan_changes(config, state)


@pytest.mark.parametrize("index", [30, 255])
def test_unsafe_combo_indices_rejected_before_any_record_query(nape, index):
    with pytest.raises(ValueError, match="0..29"):
        snapshot.read_snapshot(RECEIVER, combo_targets=(index,))
    assert not any(p[:2] == b"\xa7\x28" for p in nape.requests)
    with pytest.raises(ValueError):
        validate_config({"schema_version": 1, "combos": [{"index": index, "delete": True}]})
    with pytest.raises(ValueError, match="bulk deletion is not exposed"):
        encode_change(Change("combo", record(), None, index=index))


@pytest.mark.parametrize("transport", [RECEIVER, USB])
def test_new_dpi_writes_wait_for_status_and_backup_complete_configuration(nape, transport):
    result = apply(nape, {"custom_dpi": 1000, "scroll_dpi": 80, "dpi_stage_count": 4}, transport)
    assert result["verified"]
    assert [p[1:5] for p in nape.setters] == [
        bytes.fromhex("a7 3d 04 00"),
        bytes.fromhex("a7 37 e8 03"),
        bytes.fromhex("a7 3b 50 00"),
    ]
    backup = json.loads(nape.backup_path.read_text())
    assert backup["default_layer"] == 1 and backup["scroll_dpi"] == 400
    assert len(backup["combos"]) == 30 and len(backup["tap_holds"]) == 63
    assert backup["layers"][1]["orientation"] == 90 and "macro_buffer" in backup


@pytest.mark.parametrize("value", [1, 399, 4001, 65535])
def test_custom_dpi_clamping_is_rejected_not_silently_applied(nape, value):
    with pytest.raises(ValueError, match="400..4000"):
        apply(nape, {"custom_dpi": value})
    with pytest.raises(ValueError):
        encode_change(Change("custom_dpi", 400, value))
    assert not nape.setters and not nape.backup_path.exists()


@pytest.mark.parametrize("value", [0, 39, 4001, True])
def test_scroll_dpi_range_is_validated_offline(value):
    with pytest.raises(ValueError):
        validate_config({"schema_version": 1, "scroll_dpi": value})
    with pytest.raises(ValueError):
        encode_change(Change("scroll_dpi", 400, value))


def test_existing_count_limits_are_used_for_selection_only_config(nape):
    with pytest.raises(ValueError, match="select a dpi_index"):
        apply(nape, {"dpi_index": 4})
    assert not nape.setters


def test_per_layer_orientation_updates_effective_readback_without_extra_setter(nape):
    assert apply(nape, {"layers": [{"layer": 1, "orientation": 135}]})["verified"]
    assert [p[1:5] for p in nape.setters] == [bytes.fromhex("a7 39 01 03")]


def test_matching_global_and_layer_angle_send_only_one_setter(nape):
    assert apply(nape, {"orientation": 135, "layers": [{"layer": 1, "orientation": 135}]})[
        "verified"
    ]
    assert len(nape.setters) == 1 and nape.setters[0][2] == 0x34


def test_global_orientation_preserves_other_layer_angles(nape):
    nape.layer_orientations[3] = 180
    assert apply(nape, {"orientation": 135})["verified"]
    assert nape.layer_orientations[1] == 135 and nape.layer_orientations[3] == 180


def test_conflicting_global_and_layer_angles_are_rejected(nape):
    with pytest.raises(ValueError, match="conflicts"):
        apply(nape, {"orientation": 135, "layers": [{"layer": 1, "orientation": 180}]})
    assert not nape.setters


def test_layer_switch_preserves_and_verifies_angles(nape):
    nape.layer_orientations[2] = 180
    assert apply(nape, {"active_layer": 2})["verified"]
    assert nape.default_layer == 2 and nape.current_layer == 2


def test_existing_default_layer_does_not_write_over_a_temporary_layer(nape):
    nape.current_layer = 2
    assert apply(nape, {"active_layer": 1})["mode"] == "no-op"
    assert not nape.setters and not nape.backup_path.exists()


def test_combo_delete_compacts_and_verifies_preserved_records(nape):
    nape.combos = {0: record(4), 1: record(5), 2: record(6)}
    assert apply(nape, {"combos": [{"index": 0, "delete": True}]})["verified"]
    assert nape.combos == {0: record(5), 1: record(6)}
    backup = json.loads(nape.backup_path.read_text())
    assert backup["combos"]["0"] == record(4) and backup["combos"]["2"] == record(6)


def test_combo_edits_precede_descending_deletes_using_original_indices(nape):
    nape.combos = {i: record(i + 4) for i in range(4)}
    config = {"combos": [{"index": 1, "delete": True}, combo(2, 9), {"index": 3, "delete": True}]}
    assert apply(nape, config)["verified"]
    assert [p[2:4] for p in nape.setters] == [bytes((0x27, 2)), bytes((0x2E, 3)), bytes((0x2E, 1))]
    assert nape.combos == {0: record(4), 1: record(9)}


@pytest.mark.parametrize("family", ["combos", "tap_holds"])
def test_create_matching_existing_record_is_idempotent_without_overwriting(nape, family):
    if family == "combos":
        nape.combos = {0: record()}
        entries = [combo(0, create=True)]
    else:
        nape.tap_holds[(0, 4)] = {"tap": 4, "held": 5}
        entries = [{"layer": 0, "button": "M1", "tap": "0x0004", "held": "0x0005", "create": True}]
    assert apply(nape, {family: entries})["mode"] == "no-op"
    assert not nape.setters and not nape.backup_path.exists()


def test_empty_combo_delete_is_a_noop_not_a_compaction(nape):
    assert apply(nape, {"combos": [{"index": 2, "delete": True}]})["mode"] == "no-op"
    assert not nape.setters


def test_tap_hold_capacity_checks_complete_inventory(nape):
    targets = [(layer, column) for layer in range(9) for column in range(7)]
    nape.tap_holds = {target: {"tap": 4, "held": 5} for target in targets[:30]}
    layer, column = targets[30]
    create = {
        "layer": layer,
        "button": BUTTON_ORDER[column],
        "tap": "0x0004",
        "held": "0x0005",
        "create": True,
    }
    with pytest.raises(ValueError, match="capacity is 30"):
        apply(nape, {"tap_holds": [create]})
    assert not nape.setters


def test_tap_hold_deletes_free_capacity_before_creation(nape):
    nape.tap_holds[(0, 0)] = {"tap": 4, "held": 5}
    entries = [
        {"layer": 1, "button": "M1", "tap": "0x0004", "held": "0x0005", "create": True},
        {"layer": 0, "button": "03", "delete": True},
    ]
    assert apply(nape, {"tap_holds": entries})["verified"]
    assert [p[2] for p in nape.setters] == [0x2F, 0x25]


@pytest.mark.parametrize("field", ["custom_dpi", "scroll_dpi", "dpi_stage_count"])
def test_status_failure_stops_before_any_further_write(nape, field):
    values = {"custom_dpi": 900, "scroll_dpi": 80, "dpi_stage_count": 4}
    nape.status_failure = {"custom_dpi": 0x37, "scroll_dpi": 0x3B, "dpi_stage_count": 0x3D}[field]
    with pytest.raises(RuntimeError, match="returned status 1"):
        apply(nape, {field: values[field], "sleep": {"sleep": 100}})
    assert len(nape.setters) == 1 and nape.backup_path.is_file()


def test_missing_130_layer_ack_stops_without_retry(nape):
    nape.omit_ack = 0x2D
    with pytest.raises(RuntimeError, match="ACK timed out"):
        apply(nape, {"active_layer": 2})
    assert len(nape.setters) == 1


@pytest.mark.parametrize("family", ["combos", "tap_holds", "macro_buffer", "default_layer"])
def test_unrequested_configuration_drift_fails_readback(nape, monkeypatch, family):
    def drift(_):
        if not nape.setters:
            return
        if family == "combos":
            nape.combos[4] = record(9)
        elif family == "tap_holds":
            nape.tap_holds[(8, 6)] = {"tap": 4, "held": 5}
        elif family == "macro_buffer":
            nape.macro_buffer = b"X" + nape.macro_buffer[1:]
        else:
            nape.default_layer = 2

    monkeypatch.setattr(apply_module.time, "sleep", drift)
    with pytest.raises(RuntimeError, match=f"read-back mismatch:.*{family}"):
        apply(nape, {"custom_dpi": 900})


def test_force_scroll_rejects_nibble_truncation(nape):
    with pytest.raises(ValueError, match="0..15"):
        apply(nape, {"force_gesture_scroll": {"scroll": 16}})
    assert not nape.setters


def test_zero_sleep_timers_are_valid_on_known_130(nape):
    nape.sleep_settings = {"backlight": 0, "sleep": 0, "magnet_scan": 0}
    assert (
        snapshot.read_snapshot(RECEIVER, include_device_settings=True)["sleep"]
        == nape.sleep_settings
    )
    assert apply(nape, {"sleep": {"sleep": 100}})["verified"]


@pytest.mark.parametrize("payload", [b"\xa7\x35\x00", b"\xa7\x3a\x00", b"\xa7\x3b"])
def test_new_channel_operations_keep_read_only_guards(payload):
    with pytest.raises(ValueError):
        request(object(), payload)


def test_unknown_layer_orientation_is_rejected_not_treated_as_130(nape):
    nape.firmware = b"v1.2.0"
    with pytest.raises(ValueError, match="unsupported Nape firmware"):
        snapshot.read_snapshot(RECEIVER, include_layer_orientations=True)


def test_cli_new_fields_records_and_angles_are_visible(nape, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_select_configuration", lambda _: RECEIVER)
    args = cli._parser().parse_args(["status", "--advanced", "--records", "--layer-orientations"])
    assert cli._run(args) == 0
    text = capsys.readouterr().out
    assert "Default layer: 1" in text and "scroll_dpi: 400" in text
    assert "Layer orientations:" in text and "tap_holds: {}" in text


def test_cli_packet_previews_do_not_open_hardware(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_select_configuration", lambda _: pytest.fail("hardware opened"))
    for operation, prefix in [("get-default-layer", "a7 35"), ("get-scroll-dpi", "a7 3a")]:
        assert cli._run(cli._parser().parse_args(["protocol", operation])) == 0
        assert prefix in capsys.readouterr().out


def test_malformed_empty_combo_is_not_inferred_as_absence(nape, monkeypatch):
    original = nape.write

    def write(packet):
        result = original(packet)
        if packet[1:3] == b"\xa7\x28" and packet[3] == 0:
            reply = bytearray(nape.response)
            reply[3] = 1
            nape.response = bytes(reply)
        return result

    monkeypatch.setattr(nape, "write", write)
    with pytest.raises(ValueError, match="malformed empty combo"):
        snapshot.read_snapshot(RECEIVER, include_records=True)


def test_malformed_empty_tap_hold_is_not_inferred_as_absence(nape, monkeypatch):
    original = nape.write

    def write(packet):
        result = original(packet)
        if packet[1:3] == b"\xa7\x26" and packet[3:6] == b"\x00\x00\x00":
            reply = bytearray(nape.response)
            reply[9] = 1
            nape.response = bytes(reply)
        return result

    monkeypatch.setattr(nape, "write", write)
    with pytest.raises(ValueError, match="malformed empty tap-hold"):
        snapshot.read_snapshot(RECEIVER, include_records=True)


def test_corrupt_tap_hold_inventory_prevents_any_write(nape):
    targets = [(layer, column) for layer in range(9) for column in range(7)]
    nape.tap_holds = {target: {"tap": 4, "held": 5} for target in targets[:31]}
    with pytest.raises(ValueError, match="invalid tap-hold inventory"):
        apply(nape, {"custom_dpi": 900})
    assert not nape.setters and not nape.backup_path.exists()


def test_supported_capabilities_describe_130_contract():
    state = snapshot.read_snapshot_from_device(FakeNape())
    assert state["capabilities"]["configuration_writes"]
    assert state["capabilities"]["layer_orientations"]
    assert state["default_layer"] == 0
