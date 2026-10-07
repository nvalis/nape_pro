from collections import deque

import pytest

from nape_cli import channel, receiver
from nape_cli.cli import _parser
from nape_cli.receiver import parse_receiver_replies, query
from nape_cli.transport import probe


def test_probe_argument_does_not_overwrite_subcommand() -> None:
    args = _parser().parse_args(["probe", "--index", "0", "--command", "dpi"])
    assert args.command == "probe"
    assert args.probe_command == "dpi"


def test_receiver_fixture() -> None:
    version = bytes.fromhex("b1 02 00 0b").ljust(32, b"\x00")
    state = bytes.fromhex("b2 02 34 34 40 04 00 00 00 00 00 00 34 34 4c d0 00").ljust(32, b"\x00")
    firmware = b"\xb30.1.3 Jan  5 2026 10:49:19".ljust(32, b"\x00")
    result = parse_receiver_replies(version, state, firmware)
    assert result["protocol_version"] == 2
    assert result["firmware"].startswith("0.1.3")
    assert result["slots"][2]["product_id"] == 0x4CD0
    assert not result["slots"][2]["connected"]


def test_query_skips_notifications() -> None:
    response = b"\xb1\x02".ljust(32, b"\x00")
    replies = deque([b"\xbc".ljust(32, b"\x00"), response])

    class Device:
        def write(self, data: bytes) -> int:
            assert data == b"\x00\xb1" + bytes(31)
            return len(data)

        def read(self, size: int, timeout: int) -> bytes:
            return replies.popleft()

    assert query(Device(), 0xB1, 100) == response


def test_query_times_out(monkeypatch) -> None:
    times = iter([0.0, 0.0, 0.0, 2.0])
    monkeypatch.setattr(channel.time, "monotonic", lambda: next(times))

    class Device:
        def write(self, data: bytes) -> int:
            return len(data)

        def read(self, size: int, timeout: int) -> bytes:
            return b""

    with pytest.raises(TimeoutError):
        query(Device(), 0xB2, 1000)


def test_receiver_is_not_treated_as_direct_mouse() -> None:
    with pytest.raises(ValueError, match="tunneling"):
        probe(
            {"product_id": 0xD026, "usage_page": 0xFFC1},
            "orientation",
            report_id=0,
            timeout_ms=100,
        )


def test_receiver_rejects_wrong_collection() -> None:
    with pytest.raises(ValueError, match="Raw HID"):
        receiver.receiver_info({"product_id": 0xD026, "usage_page": 0x8C})


def test_parser_rejects_short_reply() -> None:
    with pytest.raises(ValueError, match="invalid receiver response"):
        parse_receiver_replies(b"\xb1", bytes(32), bytes(32))
