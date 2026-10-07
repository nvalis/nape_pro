import json
from types import SimpleNamespace

import pytest
from test_snapshot import RECEIVER, FakeNape

from nape_cli import apply as apply_module
from nape_cli import cli
from nape_cli.apply import apply_config as apply_pointer_config
from nape_cli.apply import encode_change
from nape_cli.config import Change, validate_config

USB = {**RECEIVER, "product_id": 0x0440}


class WritableNape(FakeNape):
    def __init__(self) -> None:
        super().__init__()
        self.orientation = 90
        self.dpi_index = 2
        self.dpi_values = [450, 800, 1600, 3200, 4000]
        self.rate_index = 3
        self.setters: list[bytes] = []
        self.reject_writes = False
        self.fail_write_number: int | None = None
        self.backup_path = None
        self.other_slot_connected = False
        self.change_keymap = False
        self.status_failure = None
        self.omit_ack = None

    @property
    def orientation(self):
        return self.layer_orientations[self.current_layer]

    @orientation.setter
    def orientation(self, value):
        self.layer_orientations[self.current_layer] = value

    def write(self, packet: bytes) -> int:
        if packet[1:3] in (
            b"\xa7\x22",
            b"\xa7\x23",
            b"\xa7\x34",
            b"\xa7\x0e",
            b"\xa7\x25",
            b"\xa7\x27",
            b"\xa7\x29",
            b"\xa7\x2d",
            b"\xa7\x2e",
            b"\xa7\x2f",
            b"\xa7\x32",
            b"\xa7\x39",
            b"\xa7\x37",
            b"\xa7\x3b",
            b"\xa7\x3d",
            b"\xa7\x0c",
        ) or packet[1] in (0x0F, 0x10):
            assert self.backup_path is not None and self.backup_path.is_file()
            backup = json.loads(self.backup_path.read_text())
            assert len(backup["layers"]) == 9
            assert len(backup["combos"]) == 30 and len(backup["tap_holds"]) == 63
            assert "macro_buffer" in backup and "scroll_dpi" in backup
            assert all("orientation" in layer for layer in backup["layers"])
            self.setters.append(packet)
            if len(self.setters) == self.fail_write_number:
                raise OSError("simulated USB failure")
            if not self.reject_writes:
                if packet[1] == 0x10:
                    self.macro_buffer = bytes(len(self.macro_buffer))
                elif packet[1] == 0x0F:
                    offset = int.from_bytes(packet[2:4], "big")
                    size = packet[4]
                    buffer = bytearray(self.macro_buffer)
                    buffer[offset : offset + size] = packet[5 : 5 + size]
                    self.macro_buffer = bytes(buffer)
                else:
                    sub = packet[2]
                    if sub == 0x37:
                        self.custom_dpi = max(400, min(4000, int.from_bytes(packet[3:5], "little")))
                    elif sub == 0x3B:
                        self.scroll_dpi = max(40, min(4000, int.from_bytes(packet[3:5], "little")))
                    elif sub == 0x3D:
                        self.dpi_stage_count = packet[3]
                    elif sub == 0x0C:
                        self.sleep_settings = {
                            name: int.from_bytes(packet[3 + i * 2 : 5 + i * 2], "little")
                            for i, name in enumerate(("backlight", "sleep", "magnet_scan"))
                        }
                    elif sub == 0x22:
                        self.dpi_index = packet[3]
                    elif sub == 0x23:
                        self.dpi_values[packet[3]] = int.from_bytes(packet[4:6], "little")
                    elif sub == 0x34:
                        self.orientation = packet[3] * 45
                    elif sub == 0x0E:
                        self.rate_index = packet[3]
                        self.secondary_rate_index = packet[4]
                    elif sub == 0x39:
                        self.layer_orientations[packet[3]] = packet[4] * 45
                    elif sub == 0x2D:
                        self.default_layer = self.current_layer = packet[3]
                    elif sub == 0x29:
                        self.gesture = {
                            name: int.from_bytes(packet[3 + i * 2 : 5 + i * 2], "little")
                            for i, name in enumerate(("up", "down", "left", "right"))
                        }
                    elif sub == 0x32:
                        self.force_gesture_scroll = {"gesture": packet[3], "scroll": packet[4]}
                    elif sub == 0x25:
                        layer, column = packet[3], packet[5]
                        self.tap_holds[(layer, column)] = {
                            "tap": int.from_bytes(packet[6:8], "little"),
                            "held": int.from_bytes(packet[8:10], "little"),
                        }
                    elif sub == 0x2F:
                        self.tap_holds.pop((packet[3], packet[5]), None)
                    elif sub == 0x27:
                        self.combos[packet[3]] = {
                            "timeout_ms": int.from_bytes(packet[4:6], "little"),
                            "layer": packet[6],
                            "columns": packet[7],
                            "tap": int.from_bytes(packet[8:10], "little"),
                            "held": int.from_bytes(packet[10:12], "little"),
                        }
                    elif sub == 0x2E:
                        index = packet[3]
                        self.combos = {
                            key if key < index else key - 1: value
                            for key, value in self.combos.items()
                            if key != index
                        }
            if packet[1] in (0x0F, 0x10):
                self.response = packet[1:]
            else:
                # A zero status is not proof of acceptance or successful persistence.
                ack = bytearray(packet[1:])
                ack[2] = 1 if packet[2] == self.status_failure else 0
                self.response = b"" if packet[2] == self.omit_ack else bytes(ack)
            return len(packet)
        count = super().write(packet)
        reply = bytearray(self.response)
        if packet[1] == 0xB2:
            reply[2:7] = bytes.fromhex("34 34 40 04 01")
            reply[11] = int(self.other_slot_connected)
        elif packet[1] == 0xA1:
            reply = bytearray(b"\xa1" + self.firmware.ljust(31, b"\x00"))
        elif packet[1] == 0xA7:
            sub = packet[2]
            if sub == 0x20:
                reply[2] = self.orientation // 45
            elif sub == 0x21:
                reply[2] = self.dpi_index
            elif sub == 0x24:
                reply[2:4] = self.dpi_values[packet[3]].to_bytes(2, "little")
            elif sub == 0x0D:
                reply[6] = self.rate_index
        elif packet[1] == 0x12 and self.change_keymap and self.setters:
            reply[4:6] = b"\x00\x04"
        self.response = bytes(reply)
        return count


@pytest.fixture
def writable(monkeypatch, tmp_path) -> WritableNape:
    fake = WritableNape()
    fake.backup_path = tmp_path / "before.json"
    monkeypatch.setattr(apply_module, "hid_backend", lambda: SimpleNamespace(device=lambda: fake))
    monkeypatch.setattr(apply_module.time, "sleep", lambda _: None)
    return fake


def test_dry_run_never_sends_setters_or_creates_backup(writable) -> None:
    config = validate_config({"schema_version": 1, "orientation": 135})
    result = apply_pointer_config(RECEIVER, config)
    assert result["mode"] == "dry-run"
    assert result["changes"] == [{"setting": "orientation", "before": 90, "after": 135}]
    assert writable.setters == []
    assert not writable.backup_path.exists()
    assert writable.closed


def test_explicit_apply_saves_backup_then_verifies_all_pointer_fields(writable) -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "dpi_values": [450, 900, 1600, 3200, 4000],
            "dpi_index": 1,
            "orientation": 135,
            "polling_rate": 500,
        }
    )
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["mode"] == "applied" and result["verified"]
    assert [packet[:6] for packet in writable.setters] == [
        bytes.fromhex("00 a7 23 01 84 03"),
        bytes.fromhex("00 a7 22 01 00 00"),
        bytes.fromhex("00 a7 34 03 00 00"),
        bytes.fromhex("00 a7 0e 04 00 00"),
    ]
    assert all(len(packet) == 33 for packet in writable.setters)
    assert json.loads(writable.backup_path.read_text())["orientation"] == 90
    assert writable.closed


def test_usb_write_uses_usb_transport_and_verifies_readback(writable) -> None:
    config = validate_config({"schema_version": 1, "orientation": 135})
    result = apply_pointer_config(USB, config, write=True, backup=writable.backup_path)
    assert result["mode"] == "applied" and result["verified"]
    assert writable.setters[0][1:4] == bytes.fromhex("a7 34 03")
    assert json.loads(writable.backup_path.read_text())["transport"] == "usb-raw-hid"
    assert not any(request[:1] == b"\xb2" for request in writable.requests)
    assert writable.closed


def test_usb_write_rejects_unverified_firmware_before_backup_or_setter(writable) -> None:
    writable.firmware = b"v9.0.0-ZK"
    config = validate_config({"schema_version": 1, "orientation": 135})
    with pytest.raises(ValueError, match="unsupported Nape firmware"):
        apply_pointer_config(USB, config, write=True, backup=writable.backup_path)
    assert writable.setters == [] and not writable.backup_path.exists()
    assert writable.closed


def test_apply_per_layer_orientation_is_backed_up_and_verified(writable) -> None:
    config = validate_config({"schema_version": 1, "layers": [{"layer": 3, "orientation": 135}]})
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["verified"] and writable.layer_orientations[3] == 135
    assert writable.setters[0][1:5] == bytes.fromhex("a7 39 03 03")
    assert writable.closed


def test_layer_switch_and_orientation_must_be_applied_separately(writable) -> None:
    writable.current_layer = 1
    config = validate_config({"schema_version": 1, "active_layer": 2, "orientation": 135})
    with pytest.raises(ValueError, match="in separate applies"):
        apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert not writable.setters and not writable.backup_path.exists()


def test_apply_active_layer_requires_status_and_verifies_new_angle(writable) -> None:
    config = validate_config({"schema_version": 1, "active_layer": 2})
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["verified"]
    assert writable.default_layer == writable.current_layer == 2 and writable.orientation == 0
    assert writable.setters[0][1:4] == bytes.fromhex("a7 2d 02")


def test_apply_gesture_and_force_scroll_match_launcher_packets(writable) -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "gesture": {"up": "0x0009"},
            "force_gesture_scroll": {"gesture": 1, "scroll": 0},
        }
    )
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["verified"]
    assert writable.gesture == {"up": 9, "down": 2, "left": 3, "right": 4}
    assert writable.force_gesture_scroll == {"gesture": 1, "scroll": 0}
    assert [packet[1:12] for packet in writable.setters] == [
        bytes.fromhex("a7 29 09 00 02 00 03 00 04 00 00"),
        bytes.fromhex("a7 32 01 00 00 00 00 00 00 00 00"),
    ]


def test_apply_tap_hold_matches_launcher_little_endian_layout(writable) -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "tap_holds": [
                {"layer": 0, "button": "M1", "tap": "0x0004", "held": "0x00E1", "create": True}
            ],
        }
    )
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["verified"]
    assert writable.tap_holds[(0, 4)] == {"tap": 4, "held": 0xE1}
    assert writable.setters[0][1:10] == bytes.fromhex("a7 25 00 00 04 04 00 e1 00")


def test_apply_tap_hold_delete_requires_status_and_verifies_readback(writable) -> None:
    writable.tap_holds[(0, 4)] = {"tap": 4, "held": 0xE1}
    config = validate_config(
        {"schema_version": 1, "tap_holds": [{"layer": 0, "button": "M1", "delete": True}]}
    )
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["verified"]
    assert writable.tap_holds == {}
    assert writable.setters[0][1:6] == bytes.fromhex("a7 2f 00 00 04")


def test_zero_status_tap_hold_delete_must_still_remove_the_record(writable) -> None:
    writable.tap_holds[(0, 4)] = {"tap": 4, "held": 0xE1}
    writable.reject_writes = True
    config = validate_config(
        {"schema_version": 1, "tap_holds": [{"layer": 0, "button": "M1", "delete": True}]}
    )
    with pytest.raises(RuntimeError, match="read-back mismatch: tap_holds"):
        apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert len(writable.setters) == 1 and writable.backup_path.exists()


def test_apply_combo_update_matches_launcher_layout(writable) -> None:
    config = validate_config(
        {
            "schema_version": 1,
            "combos": [
                {
                    "index": 0,
                    "layer": 0,
                    "columns": 3,
                    "tap": "0x0006",
                    "held": "0x0005",
                    "timeout_ms": 200,
                }
            ],
        }
    )
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["verified"]
    assert writable.combos[0]["tap"] == 6
    assert writable.setters[0][1:12] == bytes.fromhex("a7 27 00 c8 00 00 03 06 00 05 00")


def test_apply_combo_delete_matches_launcher_layout(writable) -> None:
    config = validate_config({"schema_version": 1, "combos": [{"index": 0, "delete": True}]})
    result = apply_pointer_config(
        RECEIVER, config, write=True, backup=writable.backup_path, timeout_ms=25
    )
    assert result["verified"]
    assert writable.combos == {}
    assert writable.setters[0][1:4] == bytes.fromhex("a7 2e 00")


@pytest.mark.parametrize("field", ["macros", "macro_buffer"])
def test_complete_macro_replacement_is_backed_up_and_verified(writable, field) -> None:
    target = bytes.fromhex("01 01 04 00") + bytes(52)
    value = [[{"type": "tap", "keycode": "0x0004"}], []] if field == "macros" else target.hex()
    config = validate_config({"schema_version": 1, field: value})
    result = apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert result["verified"] and writable.macro_buffer == target
    assert writable.setters[0][1] == 0x10
    assert writable.setters[1][1:6] == bytes.fromhex("0f 00 37 01 ff")
    assert writable.setters[-1][1:6] == bytes.fromhex("0f 00 37 01 00")
    assert json.loads(writable.backup_path.read_text())["macro_buffer"] == bytes(56).hex()


def test_structured_macro_dry_run_remains_available(writable) -> None:
    config = validate_config(
        {"schema_version": 1, "macros": [[{"type": "tap", "keycode": "0x0004"}], []]}
    )
    result = apply_pointer_config(RECEIVER, config)
    assert result["mode"] == "dry-run"
    assert result["changes"][0]["setting"] == "macro_buffer"
    assert not writable.setters and not writable.backup_path.exists()


def test_missing_backup_is_rejected_before_opening_hardware(monkeypatch) -> None:
    monkeypatch.setattr(apply_module, "hid_backend", lambda: pytest.fail("hardware opened"))
    with pytest.raises(ValueError, match="requires --backup"):
        apply_pointer_config(
            RECEIVER, validate_config({"schema_version": 1, "orientation": 135}), write=True
        )


def test_existing_backup_never_overwritten(writable) -> None:
    writable.backup_path.write_text("original")
    with pytest.raises(FileExistsError):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )
    assert writable.backup_path.read_text() == "original"
    assert writable.requests == [] and writable.setters == []


def test_unsupported_rate_prevents_all_writes(writable) -> None:
    with pytest.raises(ValueError, match="support"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "polling_rate": 8000}),
            write=True,
            backup=writable.backup_path,
        )
    assert writable.setters == [] and not writable.backup_path.exists()
    assert writable.closed


def test_backup_failure_prevents_all_writes(writable, monkeypatch) -> None:
    def fail_sync(fd: int) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(apply_module.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="disk failure"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )
    assert writable.setters == [] and writable.closed


def test_firmware_rejection_is_not_reported_as_success(writable) -> None:
    writable.reject_writes = True
    with pytest.raises(RuntimeError, match="read-back mismatch.*No automatic rollback"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )
    assert len(writable.setters) == 1 and writable.backup_path.exists()
    assert writable.closed


def test_partial_usb_failure_stops_without_retry_or_rollback(writable) -> None:
    writable.fail_write_number = 2
    config = validate_config({"schema_version": 1, "dpi_index": 1, "orientation": 135})
    with pytest.raises(RuntimeError, match="2/2 write attempts.*No automatic rollback"):
        apply_pointer_config(RECEIVER, config, write=True, backup=writable.backup_path)
    assert len(writable.setters) == 2 and writable.dpi_index == 1
    assert writable.orientation == 90 and writable.closed


def test_keymap_changes_fail_verification(writable) -> None:
    writable.change_keymap = True
    with pytest.raises(RuntimeError, match="layers"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )


def test_noop_sends_no_setters_and_creates_no_backup(writable) -> None:
    result = apply_pointer_config(
        RECEIVER,
        validate_config({"schema_version": 1, "orientation": 90}),
        write=True,
        backup=writable.backup_path,
    )
    assert result["mode"] == "no-op" and result["backup"] is None
    assert writable.setters == [] and not writable.backup_path.exists()


@pytest.mark.parametrize("guard", ["firmware", "multiple_slots"])
def test_unverified_or_ambiguous_target_prevents_writes(writable, guard: str) -> None:
    if guard == "firmware":
        writable.firmware = b"v9.0.0-ZK"
    else:
        writable.other_slot_connected = True
    with pytest.raises(ValueError, match="unsupported Nape firmware|writes"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )
    assert writable.setters == [] and not writable.backup_path.exists()
    assert writable.closed


@pytest.mark.parametrize(
    "change",
    [
        Change("battery_percent", 98, 99),
        Change("orientation", 90, 91),
        Change("dpi_index", 2, 5),
        Change("dpi_values", 100, 0, 1),
        Change("dpi_values", 100, 800, 5),
        Change("polling_rate", 1000, 300),
        Change("orientation", 90, True),
    ],
)
def test_encoder_rejects_invalid_or_unimplemented_setters(change: Change) -> None:
    with pytest.raises(ValueError):
        encode_change(change)


def test_cli_write_requires_backup_before_hardware(monkeypatch, tmp_path) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"schema_version": 1, "orientation": 135}')
    monkeypatch.setattr(cli, "_select_configuration", lambda _: pytest.fail("hardware queried"))
    with pytest.raises(ValueError, match="requires --backup"):
        cli._run(cli._parser().parse_args(["apply", str(config), "--write"]))


def test_cli_apply_is_dry_run_by_default(writable, monkeypatch, tmp_path, capsys) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"schema_version": 1, "orientation": 135}')
    monkeypatch.setattr(cli, "_select_configuration", lambda _: RECEIVER)
    assert cli._run(cli._parser().parse_args(["apply", str(config), "--json"])) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["mode"] == "dry-run"
    assert "no settings written" in captured.err
    assert writable.setters == []


def test_short_write_is_reported_as_possible_partial_change(writable, monkeypatch) -> None:
    original = writable.write

    def short_write(packet: bytes) -> int:
        count = original(packet)
        return count - 1 if packet[1:3] == b"\xa7\x34" else count

    monkeypatch.setattr(writable, "write", short_write)
    with pytest.raises(RuntimeError, match="incomplete HID setter write.*partially changed"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )
    assert writable.backup_path.exists() and writable.closed


def test_readback_timeout_is_not_success(writable, monkeypatch) -> None:
    original = writable.read

    def read(size: int, timeout_ms: int) -> bytes:
        if writable.setters:
            raise TimeoutError("simulated read-back timeout")
        return original(size, timeout_ms)

    monkeypatch.setattr(writable, "read", read)
    with pytest.raises(RuntimeError, match="read-back timeout.*No automatic rollback"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )
    assert len(writable.setters) == 1 and writable.closed


def test_interrupt_reports_that_a_write_was_attempted(writable, monkeypatch) -> None:
    def interrupt(_: float) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(apply_module.time, "sleep", interrupt)
    with pytest.raises(RuntimeError, match="1/1 write attempts.*backup"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )
    assert len(writable.setters) == 1 and writable.closed


def test_verification_checks_unspecified_pointer_fields(writable, monkeypatch) -> None:
    def drift(_: float) -> None:
        writable.dpi_values[0] = 700

    monkeypatch.setattr(apply_module.time, "sleep", drift)
    with pytest.raises(RuntimeError, match="read-back mismatch: dpi_values"):
        apply_pointer_config(
            RECEIVER,
            validate_config({"schema_version": 1, "orientation": 135}),
            write=True,
            backup=writable.backup_path,
        )


def test_plan_is_shown_before_any_setter(writable) -> None:
    shown = []

    def on_plan(changes) -> None:
        assert not writable.setters and not writable.backup_path.exists()
        shown.extend(changes)

    apply_pointer_config(
        RECEIVER,
        validate_config({"schema_version": 1, "orientation": 135}),
        write=True,
        backup=writable.backup_path,
        on_plan=on_plan,
    )
    assert len(shown) == 1
