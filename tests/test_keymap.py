import copy
import json
from types import SimpleNamespace

import pytest
from test_apply import WritableNape
from test_snapshot import RECEIVER

from nape_cli import apply as apply_module
from nape_cli import cli
from nape_cli.apply import apply_config, encode_change
from nape_cli.config import Change, load_config, plan_changes, validate_config
from nape_cli.snapshot import read_snapshot_from_device


class KeymapNape(WritableNape):
    def __init__(self) -> None:
        super().__init__()
        self.buttons = [[0x522A, 0, 0x00D4, 0, 0x00D1, 0x00D2, 0x522B] for _ in range(9)]
        self.encoders = [[0x00AA, 0x00A9] for _ in range(9)]
        self.keymap_setters: list[bytes] = []
        self.disturb_unrequested = False

    def write(self, packet: bytes) -> int:
        command = packet[1]
        if command in (0x05, 0x15):
            assert self.backup_path.is_file()
            assert len(packet) == 33 and packet[0] == 0 and packet[3] == 0
            self.keymap_setters.append(packet)
            if not self.reject_writes:
                layer, column = packet[2], packet[4]
                code = int.from_bytes(packet[5:7], "big")
                target = self.buttons if command == 0x05 else self.encoders
                target[layer][column] = code
            if self.disturb_unrequested:
                self.buttons[8][0] = 0x0004
            self.response = packet[1:]
            return len(packet)
        count = super().write(packet)
        reply = bytearray(self.response)
        if command == 0x12:
            layer = int.from_bytes(packet[2:4], "big") // 14
            reply[4:18] = b"".join(code.to_bytes(2, "big") for code in self.buttons[layer])
        elif command == 0x14:
            reply[4:6] = self.encoders[packet[2]][packet[4]].to_bytes(2, "big")
        self.response = bytes(reply)
        return count


@pytest.fixture
def mapped(monkeypatch, tmp_path) -> KeymapNape:
    fake = KeymapNape()
    fake.backup_path = tmp_path / "before.json"
    monkeypatch.setattr(apply_module, "hid_backend", lambda: SimpleNamespace(device=lambda: fake))
    monkeypatch.setattr(apply_module.time, "sleep", lambda _: None)
    return fake


@pytest.mark.parametrize(
    "layers",
    [
        [],
        {},
        [None],
        [{"layer": -1, "buttons": {"M1": "0x0068"}}],
        [{"layer": 9, "buttons": {"M1": "0x0068"}}],
        [{"layer": True, "buttons": {"M1": "0x0068"}}],
        [{"buttons": {"M1": "0x0068"}}],
        [{"layer": 0}],
        [{"layer": 0, "buttons": {}}],
        [{"layer": 0, "buttons": {"b1": "0x0068"}}],
        [{"layer": 0, "buttons": {"M1": "KC_F13"}}],
        [{"layer": 0, "buttons": {"M1": 104}}],
        [{"layer": 0, "buttons": {"M1": "0x68"}}],
        [{"layer": 0, "buttons": {"M1": "0x10000"}}],
        [{"layer": 0, "buttons": {"M1": "ctrl+c"}}],
        [{"layer": 0, "dial": {"press": "0x0068"}}],
        [{"layer": 0, "dial": {"cw": None}}],
        [{"layer": 0, "gesture": {"up": "0x0068"}}],
        [{"layer": 0, "buttons": {"M1": "0x0068"}}, {"layer": 0, "dial": {"cw": "0x0069"}}],
    ],
)
def test_invalid_layer_config_is_rejected(layers: object) -> None:
    with pytest.raises(ValueError):
        validate_config({"schema_version": 1, "layers": layers})


def test_hex_normalization_and_duplicate_nested_fields(tmp_path) -> None:
    config = validate_config(
        {"schema_version": 1, "layers": [{"layer": 0, "dial": {"cw": "0X00aa"}}]}
    )
    assert config.to_dict()["layers"] == [{"layer": 0, "dial": {"cw": "0x00AA"}}]
    path = tmp_path / "config.json"
    path.write_text(
        '{"schema_version":1,"layers":[{"layer":0,"buttons":{"M1":"0x0068","M1":"0x0069"}}]}'
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_config(path)


def test_partial_layer_merge_does_not_modify_snapshot(mapped) -> None:
    current = read_snapshot_from_device(mapped, include_keymap=True)
    original = copy.deepcopy(current)
    config = validate_config(
        {"schema_version": 1, "layers": [{"layer": 0, "buttons": {"M1": "0x0068"}}]}
    )
    changes = plan_changes(config, current)
    assert [change.to_dict() for change in changes] == [
        {"setting": "layers[0].buttons.M1", "before": "0x00D1", "after": "0x0068"}
    ]
    assert current == original


def test_keymap_dry_run_reads_layers_but_sends_no_setters(mapped) -> None:
    config = validate_config(
        {"schema_version": 1, "layers": [{"layer": 8, "dial": {"cw": "0x0068"}}]}
    )
    result = apply_config(RECEIVER, config)
    assert result["mode"] == "dry-run"
    assert result["changes"][0]["setting"] == "layers[8].dial.cw"
    assert mapped.keymap_setters == [] and mapped.setters == []
    assert not mapped.backup_path.exists() and mapped.closed


def test_apply_combined_pointer_button_and_encoder_changes(mapped) -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "dpi_index": 1,
            "layers": [
                {"layer": 0, "buttons": {"M1": "0x0068"}, "dial": {"ccw": "0x0069"}},
                {"layer": 8, "buttons": {"Press": "0x006A"}, "dial": {"cw": "0x006B"}},
            ],
        }
    )
    before = copy.deepcopy(mapped.buttons)
    result = apply_config(RECEIVER, config, write=True, backup=mapped.backup_path)
    assert result["mode"] == "applied" and result["verified"]
    assert [packet[:7] for packet in mapped.keymap_setters] == [
        bytes.fromhex("00 05 00 00 04 00 68"),
        bytes.fromhex("00 15 00 00 00 00 69"),
        bytes.fromhex("00 05 08 00 06 00 6a"),
        bytes.fromhex("00 15 08 00 01 00 6b"),
    ]
    assert mapped.buttons[0][4] == 0x68 and mapped.buttons[8][6] == 0x6A
    assert mapped.encoders[0][0] == 0x69 and mapped.encoders[8][1] == 0x6B
    assert mapped.buttons[1:8] == before[1:8]
    assert json.loads(mapped.backup_path.read_text())["layers"][0]["buttons"]["M1"] == "0x00D1"
    assert mapped.orientation == 90 and mapped.dpi_index == 1 and mapped.closed


@pytest.mark.parametrize("failure", ["rejected", "unrequested"])
def test_keymap_verification_rejects_wrong_or_unrequested_changes(mapped, failure) -> None:
    mapped.reject_writes = failure == "rejected"
    mapped.disturb_unrequested = failure == "unrequested"
    config = validate_config(
        {"schema_version": 1, "layers": [{"layer": 0, "buttons": {"M1": "0x0068"}}]}
    )
    with pytest.raises(RuntimeError, match="read-back mismatch: layers"):
        apply_config(RECEIVER, config, write=True, backup=mapped.backup_path)
    assert len(mapped.keymap_setters) == 1 and mapped.closed


def test_keymap_noop_creates_no_backup_or_writes(mapped) -> None:
    config = validate_config(
        {"schema_version": 1, "layers": [{"layer": 0, "buttons": {"M1": "0x00D1"}}]}
    )
    assert apply_config(RECEIVER, config, write=True, backup=mapped.backup_path)["mode"] == "no-op"
    assert mapped.keymap_setters == [] and not mapped.backup_path.exists()


@pytest.mark.parametrize(
    "change",
    [
        Change("buttons", 0, 0x68, layer=9, binding="M1"),
        Change("buttons", 0, 0x68, layer=True, binding="M1"),
        Change("buttons", 0, 65536, layer=0, binding="M1"),
        Change("buttons", 0, 0x68, layer=0, binding="b1"),
        Change("dial", 0, 0x68, layer=0, binding="press"),
        Change("dial", 0, 0x68, index=1, layer=0, binding="cw"),
        Change("orientation", 90, 135, layer=0, binding="M1"),
    ],
)
def test_keymap_encoder_rejects_invalid_address_or_code(change: Change) -> None:
    with pytest.raises(ValueError):
        encode_change(change)


def test_cli_plan_requests_keymap_for_layer_config(mapped, monkeypatch, tmp_path, capsys) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version":1,"layers":[{"layer":0,"buttons":{"M1":"0x0068"}}]}')
    monkeypatch.setattr(cli, "_select_configuration", lambda _: RECEIVER)

    def read(
        info,
        *,
        include_keymap,
        include_device_settings=False,
        include_layer_orientations=False,
        include_macro_buffer=False,
        include_gesture=False,
        include_force_gesture_scroll=False,
        tap_hold_targets=(),
        combo_targets=(),
        timeout_ms,
    ):
        assert include_keymap
        assert (
            not include_device_settings
            and not include_layer_orientations
            and not include_macro_buffer
        )
        assert not include_gesture and not include_force_gesture_scroll
        assert not tap_hold_targets and not combo_targets
        return read_snapshot_from_device(mapped, include_keymap=True)

    monkeypatch.setattr(cli, "read_snapshot", read)
    assert cli._run(cli._parser().parse_args(["plan", str(path)])) == 0
    assert "layers[0].buttons.M1: 0x00D1 -> 0x0068" in capsys.readouterr().out


def test_keymap_ack_timeout_stops_before_next_setter(mapped, monkeypatch) -> None:
    original = mapped.read

    def read(size: int, timeout_ms: int) -> bytes:
        if mapped.keymap_setters:
            raise TimeoutError("simulated keymap ACK timeout")
        return original(size, timeout_ms)

    monkeypatch.setattr(mapped, "read", read)
    config = validate_config(
        {"schema_version": 1, "layers": [{"layer": 0, "buttons": {"M1": "0x0068", "M2": "0x0069"}}]}
    )
    with pytest.raises(
        RuntimeError, match="1/2 write attempts.*ACK timeout.*No automatic rollback"
    ):
        apply_config(RECEIVER, config, write=True, backup=mapped.backup_path)
    assert len(mapped.keymap_setters) == 1 and mapped.closed
