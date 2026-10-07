"""Regressions for contracts inspected in the official Launcher v1.5.0 bundle."""

from types import SimpleNamespace

import pytest
from test_apply import WritableNape
from test_snapshot import RECEIVER, FakeNape

from nape_cli import apply as apply_module
from nape_cli import cli, snapshot
from nape_cli.apply import apply_config, encode_change
from nape_cli.config import Change, plan_changes, validate_config
from nape_cli.macros import MacroStep, decode_macros, encode_macros


@pytest.fixture
def fake(monkeypatch, tmp_path) -> WritableNape:
    device = WritableNape()
    device.backup_path = tmp_path / "before.json"

    def backend():
        return SimpleNamespace(device=lambda: device)

    monkeypatch.setattr(apply_module, "hid_backend", backend)
    monkeypatch.setattr(snapshot, "hid_backend", backend)
    monkeypatch.setattr(apply_module.time, "sleep", lambda _: None)
    return device


@pytest.mark.parametrize("layer", [0, 1, 8])
def test_active_layer_is_the_unmodified_launcher_wire_value(layer) -> None:
    device = FakeNape()
    original = device.write

    def write(packet: bytes) -> int:
        result = original(packet)
        if packet[1] == 0xA3:
            # Literal A3 response, independent of the fake's indexing convention.
            device.response = bytes((0xA3, layer)) + bytes(30)
        return result

    device.write = write
    assert snapshot.read_snapshot_from_device(device)["active_layer"] == layer
    assert encode_change(Change("active_layer", 0, layer))[:3] == bytes((0xA7, 0x2D, layer))


@pytest.mark.parametrize("layer", [0, 8])
def test_active_layer_write_and_readback_use_same_index(fake, layer) -> None:
    fake.current_layer = 1
    result = apply_config(
        RECEIVER,
        validate_config({"schema_version": 1, "active_layer": layer}),
        write=True,
        backup=fake.backup_path,
    )
    assert result["verified"] and fake.current_layer == layer


@pytest.mark.parametrize("index", [0, 3, 6, 255])
def test_polling_write_preserves_even_an_unadvertised_secondary_index(fake, index) -> None:
    fake.secondary_rate_index = index
    result = apply_config(
        RECEIVER,
        validate_config({"schema_version": 1, "polling_rate": 500}),
        write=True,
        backup=fake.backup_path,
    )
    assert result["verified"]
    assert fake.setters[0][1:5] == bytes((0xA7, 0x0E, 4, index))
    assert fake.secondary_rate_index == index


def test_snapshot_decodes_secondary_polling_capabilities(fake) -> None:
    fake.secondary_rate_bitmap = 0x58
    fake.secondary_rate_index = 4
    state = snapshot.read_snapshot(RECEIVER)
    assert state["polling_rate_for_fr_index"] == 4
    assert state["polling_rate_for_fr"] == 500
    assert state["supported_polling_rates_for_fr"] == [1000, 500, 125]


def test_snapshot_rejects_invalid_advertised_secondary_index(fake) -> None:
    fake.secondary_rate_bitmap = 0x58
    fake.secondary_rate_index = 7
    with pytest.raises(ValueError, match="secondary polling-rate index"):
        snapshot.read_snapshot(RECEIVER)
    assert fake.closed


def test_secondary_polling_drift_fails_readback_even_for_unrelated_write(fake, monkeypatch) -> None:
    fake.secondary_rate_index = 3
    monkeypatch.setattr(
        apply_module.time, "sleep", lambda _: setattr(fake, "secondary_rate_index", 4)
    )
    with pytest.raises(RuntimeError, match="read-back mismatch: polling_rate_for_fr_index"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=fake.backup_path,
        )
    assert fake.backup_path.exists() and fake.closed


def test_polling_encoder_and_planner_require_secondary_state(fake) -> None:
    with pytest.raises(ValueError, match="secondary polling-rate index"):
        encode_change(Change("polling_rate", 1000, 500))
    current = snapshot.read_snapshot(RECEIVER)
    del current["polling_rate_for_fr_index"]
    with pytest.raises(ValueError, match="secondary polling-rate state"):
        plan_changes(validate_config({"schema_version": 1, "polling_rate": 500}), current)


def test_orientation_ack_timeout_stops_before_next_setter(fake, monkeypatch) -> None:
    original = fake.read

    def read(size: int, timeout_ms: int) -> bytes:
        return b"" if fake.setters else original(size, timeout_ms)

    monkeypatch.setattr(fake, "read", read)
    with pytest.raises(RuntimeError, match="1/2 write attempts.*0x34 ACK timed out"):
        apply_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135, "polling_rate": 500}),
            write=True,
            backup=fake.backup_path,
            timeout_ms=1,
        )
    assert len(fake.setters) == 1 and fake.backup_path.exists() and fake.closed


def test_encoder_ack_ignores_wrong_direction() -> None:
    sent = bytes.fromhex("15 00 00 01 00 04").ljust(32, b"\x00")
    wrong = bytes.fromhex("15 00 00 00 00 04").ljust(32, b"\x00")
    replies = [wrong, sent]
    device = SimpleNamespace(read=lambda *_: replies.pop(0))
    apply_module._wait_keymap_ack(device, sent, 100)
    assert not replies


@pytest.mark.parametrize("with_keymap", [False, True])
def test_known_layer_orientation_failure_is_blocked_before_any_angle_query(
    fake, with_keymap
) -> None:
    with pytest.raises(ValueError, match="per-layer orientation is unreadable"):
        snapshot.read_snapshot(
            RECEIVER, include_keymap=with_keymap, include_layer_orientations=True
        )
    assert not any(p[:2] == b"\xa7\x38" for p in fake.requests)
    assert fake.closed


@pytest.mark.parametrize("kind", ["tap_hold", "combo"])
def test_creation_timeout_is_not_treated_as_an_empty_record(fake, monkeypatch, kind) -> None:
    original = fake.read
    query = b"\xa7\x26" if kind == "tap_hold" else b"\xa7\x28"

    def read(size: int, timeout_ms: int) -> bytes:
        if fake.requests[-1][:2] == query:
            return b""
        return original(size, timeout_ms)

    monkeypatch.setattr(fake, "read", read)
    record = {"create": True, "tap": "0x0004", "held": "0x0005"}
    field = "tap_holds" if kind == "tap_hold" else "combos"
    address = (
        {"layer": 0, "button": "M1"}
        if kind == "tap_hold"
        else {"index": 3, "layer": 0, "columns": 3}
    )
    config = validate_config({"schema_version": 1, "dpi_index": 1, field: [{**record, **address}]})
    with pytest.raises(TimeoutError):
        apply_config(RECEIVER, config, write=True, backup=fake.backup_path, timeout_ms=1)
    assert not fake.setters and not fake.backup_path.exists() and fake.closed


def test_positive_empty_combo_response_allows_creation(fake) -> None:
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
    result = apply_config(RECEIVER, config, write=True, backup=fake.backup_path)
    assert result["verified"] and fake.combos[3]["tap"] == 4


@pytest.mark.parametrize("version,byte", [(12, 0), (12, 1), (9, 0), (9, 1), (9, 2), (9, 3), (9, 4)])
def test_macro_text_rejects_protocol_reserved_bytes(version, byte) -> None:
    with pytest.raises(ValueError, match="reserved opcode"):
        encode_macros(
            ((MacroStep("text", text=chr(byte)),),), count=1, size=16, protocol_version=version
        )


def test_shared_reserved_macro_text_is_rejected_offline() -> None:
    with pytest.raises(ValueError, match="reserved macro opcode"):
        validate_config(
            {"schema_version": 1, "macros": [[{"type": "text", "text": "\x01\x01A"}], []]}
        )


def test_legacy_reserved_macro_text_fails_planning_with_device_protocol(fake, monkeypatch) -> None:
    config = validate_config(
        {"schema_version": 1, "macros": [[{"type": "text", "text": "\x02"}], []]}
    )
    original = fake.write

    def write(packet: bytes) -> int:
        count = original(packet)
        if packet[1] == 0x01:
            fake.response = bytes.fromhex("01 00 09").ljust(32, b"\x00")
        return count

    monkeypatch.setattr(fake, "write", write)
    with pytest.raises(ValueError, match="reserved opcode"):
        apply_config(RECEIVER, config)
    assert not fake.setters and fake.closed


def test_v11_unknown_macro_action_is_ignored_like_launcher() -> None:
    assert decode_macros(bytes.fromhex("01 05 41 00"), count=1, protocol_version=12) == [
        [{"type": "text", "text": "A"}]
    ]


@pytest.mark.parametrize("data,count", [(b"", 1), (b"A", 1), (b"\x00", 2), (b"A\x00B", 2)])
def test_incomplete_macro_slots_are_rejected(data, count) -> None:
    with pytest.raises(ValueError, match="missing slot terminator"):
        decode_macros(data, count=count, protocol_version=12)


@pytest.mark.parametrize("data", ["01", "01 01", "01 04 31", "01 04 7c 00", "01 04 2d 31 7c 00"])
def test_truncated_and_invalid_macro_actions_are_rejected(data) -> None:
    with pytest.raises(ValueError):
        decode_macros(bytes.fromhex(data), count=1, protocol_version=12)


def test_launcher_legacy_delay_is_decoded() -> None:
    assert decode_macros(bytes.fromhex("04 31 35 30 7c 00"), count=1, protocol_version=9) == [
        [{"type": "delay", "ms": 150}]
    ]


def test_incomplete_macro_export_fails_instead_of_fabricating_slots(fake) -> None:
    fake.macro_buffer = b"A" * 56
    with pytest.raises(ValueError, match="missing slot terminator"):
        snapshot.read_snapshot(RECEIVER, include_macro_buffer=True)
    assert fake.closed


def test_raw_macro_plan_rejects_unterminated_target(fake) -> None:
    config = validate_config({"schema_version": 1, "macro_buffer": (b"A" * 55 + b"\x00").hex()})
    with pytest.raises(ValueError, match="missing slot terminator"):
        apply_config(RECEIVER, config)
    assert not fake.setters and fake.closed


def test_cli_macro_replacement_warns_about_destructive_reset(
    fake, monkeypatch, tmp_path, capsys
) -> None:
    config = tmp_path / "macros.json"
    config.write_text('{"schema_version":1,"macros":[[{"type":"text","text":"hello"}],[]]}')
    monkeypatch.setattr(cli, "_select_receiver", lambda _: RECEIVER)
    args = cli._parser().parse_args(
        ["apply", str(config), "--write", "--backup", str(fake.backup_path)]
    )
    assert cli._run(args) == 0
    assert "resets the entire macro store" in capsys.readouterr().out
    assert fake.setters[0][1] == 0x10
