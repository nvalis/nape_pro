import json
from types import SimpleNamespace

import pytest

from nape_cli import cli, snapshot
from nape_cli.channel import request

RECEIVER = {
    "vendor_id": 0x3434,
    "product_id": 0xD026,
    "usage_page": 0xFF60,
    "usage": 0x61,
    "path": b"test",
}


class FakeNape:
    def __init__(self) -> None:
        self.closed = False
        self.requests: list[bytes] = []
        self.response = b""
        self.layer_count = 9
        self.awake = True
        self.layer_orientations = [0] * 9
        self.macro_count = 2
        self.macro_buffer = bytes(56)
        self.gesture = {"up": 0x0001, "down": 0x0002, "left": 0x0003, "right": 0x0004}
        self.force_gesture_scroll = {"gesture": 0, "scroll": 0}
        self.tap_holds = {}
        self.combos = {0: {"timeout_ms": 200, "layer": 0, "columns": 3, "tap": 4, "held": 5}}
        self.current_layer = 0
        self.custom_dpi = 800
        self.dpi_stage_count = 5
        self.sleep_settings = {"backlight": 0x0123, "sleep": 0x0456, "magnet_scan": 0x0789}
        self.firmware = b"v1.1.6-ZK"
        self.secondary_rate_bitmap = 0
        self.secondary_rate_index = 0

    def open_path(self, path: bytes) -> None:
        assert path == b"test"

    def close(self) -> None:
        self.closed = True

    def write(self, packet: bytes) -> int:
        assert len(packet) == 33 and packet[0] == 0
        payload = packet[1:]
        self.requests.append(payload)
        command = payload[0]
        reply = bytearray(payload)
        if command == 0x01:
            reply[1:3] = (12).to_bytes(2, "big")
        elif command == 0xB2:
            reply[6] = int(self.awake)
        elif command == 0xA1:
            reply[1:] = self.firmware.ljust(31, b"\x00")
        elif command == 0x11:
            reply[1] = self.layer_count
        elif command == 0xA3:
            reply[1] = self.current_layer
        elif command == 0xA7:
            sub = payload[1]
            if sub in (0x20, 0x21):
                reply[2] = 2
            elif sub == 0x24:
                reply[2:4] = (450, 800, 1600, 3200, 4000)[payload[2]].to_bytes(2, "little")
            elif sub == 0x31:
                reply[2:4] = b"\x62\x00"
            elif sub == 0x0D:
                reply[5:7] = b"\x58\x03"
                reply[10] = self.secondary_rate_bitmap
                reply[11] = self.secondary_rate_index
            elif sub == 0x36:
                reply[2:4] = self.custom_dpi.to_bytes(2, "little")
            elif sub == 0x3C:
                reply[2] = self.dpi_stage_count
            elif sub == 0x0B:
                for i, name in enumerate(("backlight", "sleep", "magnet_scan")):
                    reply[3 + i * 2 : 5 + i * 2] = self.sleep_settings[name].to_bytes(2, "little")
            elif sub == 0x38:
                reply[2] = self.layer_orientations[payload[2]] // 45
            elif sub == 0x2A:
                for i, name in enumerate(("up", "down", "left", "right")):
                    reply[2 + i * 2 : 4 + i * 2] = self.gesture[name].to_bytes(2, "little")
            elif sub == 0x33:
                reply[2] = self.force_gesture_scroll["gesture"]
                reply[3] = self.force_gesture_scroll["scroll"]
            elif sub == 0x26:
                layer, column = payload[2], payload[4]
                values = self.tap_holds.get((layer, column), {"tap": 0, "held": 0})
                reply[2:5] = bytes((layer, payload[3], column))
                reply[5:7] = values["tap"].to_bytes(2, "little")
                reply[7:9] = values["held"].to_bytes(2, "little")
            elif sub == 0x28:
                index = payload[2]
                if index not in self.combos:
                    reply[6] = 0
                else:
                    values = self.combos[index]
                    reply[2] = index
                    reply[3:5] = values["timeout_ms"].to_bytes(2, "little")
                    reply[5] = values["layer"]
                    reply[6] = values["columns"]
                    reply[7:9] = values["tap"].to_bytes(2, "little")
                    reply[9:11] = values["held"].to_bytes(2, "little")
        elif command == 0x0C:
            reply[1] = self.macro_count
        elif command == 0x0D:
            reply[1:3] = len(self.macro_buffer).to_bytes(2, "big")
        elif command == 0x0E:
            offset = int.from_bytes(payload[1:3], "big")
            size = payload[3]
            reply[3] = size
            reply[4 : 4 + size] = self.macro_buffer[offset : offset + size]
        elif command == 0x12:
            reply[4:18] = bytes.fromhex("52 2a 00 00 00 d4 00 00 00 d1 00 d2 52 2b")
        elif command == 0x14:
            reply[4:6] = (0xAA if payload[3] == 0 else 0xA9).to_bytes(2, "big")
        else:
            raise AssertionError(f"unexpected command {command}")
        self.response = bytes(reply)
        return len(packet)

    def read(self, size: int, timeout_ms: int) -> bytes:
        return self.response


@pytest.fixture
def device(monkeypatch) -> FakeNape:
    fake = FakeNape()
    monkeypatch.setattr(snapshot, "hid_backend", lambda: SimpleNamespace(device=lambda: fake))
    return fake


def test_snapshot_decodes_pointer_settings(device) -> None:
    result = snapshot.read_snapshot(RECEIVER)
    assert result["dpi"] == 1600
    assert result["dpi_values"] == [450, 800, 1600, 3200, 4000]
    assert result["orientation"] == 90
    assert result["battery_percent"] == 98
    assert result["active_layer"] == 0
    assert result["polling_rate"] == 1000
    assert result["supported_polling_rates"] == [1000, 500, 125]
    assert "layers" not in result
    assert device.closed


def test_snapshot_reads_all_keymap_layers(device) -> None:
    result = snapshot.read_snapshot(RECEIVER, include_keymap=True)
    assert len(result["layers"]) == 9
    assert result["layers"][0]["buttons"]["03"] == "0x522A"
    assert result["layers"][0]["dial"] == {"ccw": "0x00AA", "cw": "0x00A9"}
    key_reads = [p for p in device.requests if p[0] == 0x12]
    assert [int.from_bytes(p[1:3], "big") for p in key_reads] == list(range(0, 126, 14))
    assert device.closed


def test_launcher_advanced_queries_decode_as_expected(device) -> None:
    result = snapshot.read_snapshot(
        RECEIVER,
        include_macro_buffer=True,
        include_gesture=True,
        include_force_gesture_scroll=True,
        tap_hold_targets=((0, "M1"),),
        combo_targets=(0,),
    )
    assert result["via_protocol_version"] == 12
    assert result["macros"] == [[], []]
    assert result["gesture"] == {"up": 1, "down": 2, "left": 3, "right": 4}
    assert result["force_gesture_scroll"] == {"gesture": 0, "scroll": 0}
    assert result["tap_holds"] == {"0:M1": None}
    assert result["combos"]["0"] == {
        "timeout_ms": 200,
        "layer": 0,
        "columns": 3,
        "tap": 4,
        "held": 5,
    }
    assert any(payload.startswith(bytes.fromhex("a7 26 00 00 04")) for payload in device.requests)
    assert any(payload.startswith(bytes.fromhex("a7 28 00")) for payload in device.requests)


def test_advanced_snapshot_reads_layer_orientations_and_macro_buffer(device) -> None:
    device.firmware = b"v1.2.0"
    result = snapshot.read_snapshot(
        RECEIVER,
        include_keymap=True,
        include_layer_orientations=True,
        include_macro_buffer=True,
    )
    assert [layer["orientation"] for layer in result["layers"]] == [0] * 9
    assert result["macro_count"] == 2
    assert result["macro_buffer_size"] == 56
    assert result["macro_buffer"] == bytes(56).hex()
    assert len([payload for payload in device.requests if payload[0] == 0x0E]) == 2
    assert device.closed


def test_sleeping_device_stops_queries_and_closes(device) -> None:
    device.awake = False
    with pytest.raises(RuntimeError, match="awake"):
        snapshot.read_snapshot(RECEIVER)
    assert len(device.requests) == 1
    assert device.closed


def test_unexpected_layer_count_is_rejected(device) -> None:
    device.layer_count = 4
    with pytest.raises(ValueError, match="9 layers"):
        snapshot.read_snapshot(RECEIVER)
    assert device.closed


@pytest.mark.parametrize(
    "payload",
    [
        b"\x05",
        b"\xa7\x25",
        b"\xa7\x27",
        b"\xa7\x29",
        b"\xa7\x2d",
        b"\xa7\x2e",
        b"\xa7\x2f",
        b"\xa7\x32",
        b"\xa7\x34",
        b"\xa7\x39",
        b"\x10",
        b"\x0f",
    ],
)
def test_channel_rejects_write_commands(payload: bytes) -> None:
    with pytest.raises(ValueError, match="read-only allowlist"):
        request(object(), payload)


@pytest.mark.parametrize(
    "payload",
    [b"\xa7\x38", b"\xa7\x38\x09", b"\x0c\x01", b"\x0e\x00\x00\x00", b"\x0e\x00\x00\x1d"],
)
def test_advanced_read_requests_validate_arguments(payload: bytes) -> None:
    with pytest.raises(ValueError):
        request(object(), payload)


def test_export_does_not_overwrite_existing_file(tmp_path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text("keep this", encoding="utf-8")
    args = cli._parser().parse_args(["export", str(path)])
    with pytest.raises(FileExistsError):
        cli._run(args)
    assert path.read_text() == "keep this"


def test_export_writes_json_snapshot(device, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_select_receiver", lambda index: RECEIVER)
    path = tmp_path / "snapshot.json"
    args = cli._parser().parse_args(["export", str(path)])
    assert cli._run(args) == 0
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert len(data["layers"]) == 9
    assert "macro_buffer" not in data


def test_advanced_export_includes_experimental_state(device, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_select_receiver", lambda index: RECEIVER)
    path = tmp_path / "advanced.json"
    args = cli._parser().parse_args(["export", str(path), "--advanced"])
    assert cli._run(args) == 0
    data = json.loads(path.read_text())
    assert data["gesture"] == {
        "up": 1,
        "down": 2,
        "left": 3,
        "right": 4,
    }
    assert data["force_gesture_scroll"] == {"gesture": 0, "scroll": 0}
    assert data["macro_buffer"] == bytes(56).hex()
    assert data["macro_count"] == 2
    assert len(data["macros"]) == 2


def test_layer_orientation_export_uses_explicit_flag(device, monkeypatch, tmp_path) -> None:
    device.firmware = b"v1.2.0"
    monkeypatch.setattr(cli, "_select_receiver", lambda index: RECEIVER)
    path = tmp_path / "orientations.json"
    args = cli._parser().parse_args(["export", str(path), "--layer-orientations"])
    assert cli._run(args) == 0
    data = json.loads(path.read_text())
    assert [layer["orientation"] for layer in data["layers"]] == [0] * 9
