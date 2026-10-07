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
        if command == 0xB2:
            reply[6] = int(self.awake)
        elif command == 0xA1:
            reply[1:11] = b"v1.1.6-ZK\x00"
        elif command == 0x11:
            reply[1] = self.layer_count
        elif command == 0xA3:
            reply[1] = 1
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


@pytest.mark.parametrize("payload", [b"\x05", b"\xa7\x34", b"\x10"])
def test_channel_rejects_write_commands(payload: bytes) -> None:
    with pytest.raises(ValueError, match="read-only allowlist"):
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
