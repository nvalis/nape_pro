import pytest

from nape_cli.protocol import (
    KC_MISC_CMD_GROUP,
    REPORT_SIZE,
    NapeCommand,
    build_request,
    orientation_units,
)


def test_get_orientation_request_is_zero_padded() -> None:
    request = build_request(NapeCommand.GET_ORIENTATION)

    assert len(request) == REPORT_SIZE
    assert request[:2] == bytes((KC_MISC_CMD_GROUP, 0x20))
    assert request[2:] == bytes(REPORT_SIZE - 2)


def test_set_orientation_request_encodes_45_degree_units() -> None:
    request = build_request(NapeCommand.SET_ORIENTATION, orientation_units(90))

    assert request[:3] == bytes((KC_MISC_CMD_GROUP, 0x34, 2))


@pytest.mark.parametrize("angle", [-45, 1, 44, 360])
def test_invalid_orientation_is_rejected(angle: int) -> None:
    with pytest.raises(ValueError, match="orientation must be"):
        orientation_units(angle)


def test_request_rejects_non_byte_arguments() -> None:
    with pytest.raises(ValueError, match="must be bytes"):
        build_request(NapeCommand.SET_ORIENTATION, 256)
