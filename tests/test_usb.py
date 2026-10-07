"""Direct USB uses FF60:61, never the keyboard, mouse, or bridge collections."""

import json
from types import SimpleNamespace

import pytest
from test_snapshot import RECEIVER, FakeNape

from nape_cli import apply, cli, devices, snapshot

USB = {
    "vendor_id": 0x3434,
    "product_id": 0x0440,
    "usage_page": 0xFF60,
    "usage": 0x61,
    "path": b"test",
}


@pytest.fixture
def usb(monkeypatch):
    fake = FakeNape()
    # A direct USB device has no receiver slot state and must not query it.
    fake.awake = False
    original_write = fake.write

    def write(packet):
        assert packet[1] not in (0xB1, 0xB2, 0xB3)
        return original_write(packet)

    fake.write = write
    backend = SimpleNamespace(device=lambda: fake, enumerate=lambda *_: [USB])
    monkeypatch.setattr(devices, "hid_backend", lambda: backend)
    monkeypatch.setattr(snapshot, "hid_backend", lambda: backend)
    monkeypatch.setattr(apply, "hid_backend", lambda: backend)
    return fake


def test_default_discovery_includes_usb_raw_hid(monkeypatch):
    keyboard = {**USB, "usage_page": 1, "usage": 6}
    bridge = {**USB, "usage_page": 0x8C, "usage": 1}
    interfaces = [keyboard, USB, bridge]
    monkeypatch.setattr(
        devices, "hid_backend", lambda: SimpleNamespace(enumerate=lambda *_: interfaces)
    )
    assert devices.enumerate_devices() == [USB, bridge]
    assert devices.enumerate_devices(all_collections=True) == interfaces


@pytest.mark.parametrize("target", [USB, RECEIVER])
def test_configuration_selection_supports_both_transports(monkeypatch, target):
    monkeypatch.setattr(cli, "enumerate_devices", lambda: [target])
    assert cli._select_configuration(None) == target
    assert cli._select_configuration(0) == target


def test_multiple_targets_require_explicit_selection(monkeypatch):
    monkeypatch.setattr(cli, "enumerate_devices", lambda: [USB, RECEIVER])
    with pytest.raises(ValueError, match="multiple.*--index"):
        cli._select_configuration(None)
    assert cli._select_configuration(0) == USB
    assert cli._select_configuration(1) == RECEIVER
    assert cli._select_receiver(None) == RECEIVER


@pytest.mark.parametrize("index", [-1, 2])
def test_selection_rejects_invalid_index(monkeypatch, index):
    monkeypatch.setattr(cli, "enumerate_devices", lambda: [USB, RECEIVER])
    with pytest.raises(ValueError, match="out of range"):
        cli._select_configuration(index)


def test_no_configuration_target_has_actionable_error(monkeypatch):
    monkeypatch.setattr(cli, "enumerate_devices", lambda: [])
    with pytest.raises(ValueError, match="no USB Nape or Link-KM.*devices --all"):
        cli._select_configuration(None)


def test_receiver_diagnostics_do_not_auto_select_usb(usb):
    with pytest.raises(ValueError, match="no Link-KM receiver"):
        cli._run(cli._parser().parse_args(["receiver-info"]))
    assert not usb.requests


@pytest.mark.parametrize(
    "overrides",
    [
        {"product_id": 0x1234},
        {"vendor_id": 0x1234},
        {"usage_page": 1, "usage": 2},
        {"usage_page": 0x8C, "usage": 1},
        {"usage": 0x62},
        {"usage_page": 0},
    ],
)
def test_invalid_usb_collection_rejected_before_open(monkeypatch, overrides):
    monkeypatch.setattr(snapshot, "hid_backend", lambda: pytest.fail("opened invalid target"))
    with pytest.raises(ValueError, match="Raw HID collection"):
        snapshot.read_snapshot({**USB, **overrides})


def test_usb_snapshot_skips_receiver_state_and_labels_transport(usb):
    result = snapshot.read_snapshot(USB, include_keymap=True, include_macro_buffer=True)
    assert result["transport"] == "usb-raw-hid"
    assert result["dpi"] == 1600
    assert len(result["layers"]) == 9
    assert result["macros"] == [[], []]
    assert "b2" not in result["raw"]
    assert usb.requests[0][0] == 0xA1
    assert usb.closed


def test_usb_targeted_advanced_records(usb):
    result = snapshot.read_snapshot(
        USB,
        include_device_settings=True,
        include_gesture=True,
        include_force_gesture_scroll=True,
        tap_hold_targets=((0, "M1"),),
        combo_targets=(0,),
    )
    assert result["tap_holds"]["0:M1"] is None
    assert len(result["tap_holds"]) == 63 and result["record_inventory"]
    assert result["combos"]["0"]["timeout_ms"] == 200
    assert result["sleep"] == usb.sleep_settings
    assert result["gesture"] == usb.gesture
    assert result["force_gesture_scroll"] == usb.force_gesture_scroll
    assert usb.closed


def test_usb_decode_error_closes_handle(usb):
    usb.layer_count = 4
    with pytest.raises(ValueError, match="9 layers"):
        snapshot.read_snapshot(USB)
    assert usb.closed


def test_usb_timeout_closes_handle(usb, monkeypatch):
    def timeout(*_):
        raise TimeoutError("USB read timed out")

    monkeypatch.setattr(snapshot, "request", timeout)
    with pytest.raises(TimeoutError, match="USB read"):
        snapshot.read_snapshot(USB)
    assert usb.closed


def test_invalid_timeout_rejected_before_usb_open(monkeypatch):
    monkeypatch.setattr(snapshot, "hid_backend", lambda: pytest.fail("opened with bad timeout"))
    with pytest.raises(ValueError, match="timeout"):
        snapshot.read_snapshot(USB, timeout_ms=0)


def test_usb_status_json(usb, capsys):
    assert cli._run(cli._parser().parse_args(["status", "--json"])) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["transport"] == "usb-raw-hid"
    assert result["orientation"] == 90
    assert usb.closed


def test_usb_advanced_export(usb, tmp_path):
    output = tmp_path / "usb.json"
    assert cli._run(cli._parser().parse_args(["export", str(output), "--advanced"])) == 0
    result = json.loads(output.read_text())
    assert result["transport"] == "usb-raw-hid"
    assert len(result["layers"]) == 9
    assert "sleep" in result
    assert "gesture" in result
    assert "force_gesture_scroll" in result
    assert "macro_buffer" in result
    assert usb.closed


@pytest.mark.parametrize("command", ["plan", "apply"])
def test_usb_planning_never_sends_setters(usb, tmp_path, capsys, command):
    config = tmp_path / "config.json"
    config.write_text('{"schema_version":1,"orientation":135}')
    assert cli._run(cli._parser().parse_args([command, str(config), "--json"])) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "mode": "dry-run",
        "changes": [{"setting": "orientation", "before": 90, "after": 135}],
    }
    assert usb.closed
