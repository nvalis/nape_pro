import pytest

from nape_cli.macros import MacroStep, decode_macros, encode_macros


def test_v11_codec_matches_launcher_action_layout() -> None:
    macros = (
        (
            MacroStep("tap", keycode=0x04),
            MacroStep("down", keycode=0xE1),
            MacroStep("delay", milliseconds=150),
            MacroStep("text", text="A"),
        ),
    )
    encoded = encode_macros(macros, count=1, size=20, protocol_version=12)
    assert encoded[:14] == bytes.fromhex("01 01 04 01 02 e1 01 04 31 35 30 7c 41 00")
    assert encoded[14:] == bytes(6)
    assert decode_macros(encoded, count=1, protocol_version=12) == [
        [
            {"type": "tap", "keycode": "0x0004"},
            {"type": "down", "keycode": "0x00E1"},
            {"type": "delay", "ms": 150},
            {"type": "text", "text": "A"},
        ]
    ]


def test_v9_codec_matches_launcher_legacy_layout() -> None:
    macros = ((MacroStep("tap", keycode=0x04), MacroStep("text", text="x")),)
    encoded = encode_macros(macros, count=1, size=5, protocol_version=9)
    assert encoded == bytes.fromhex("01 04 78 00 00")
    assert decode_macros(encoded, count=1, protocol_version=9) == [
        [{"type": "tap", "keycode": "0x0004"}, {"type": "text", "text": "x"}]
    ]


def test_macro_encoder_rejects_capacity_and_unsupported_delay() -> None:
    macro = ((MacroStep("text", text="too long"),),)
    with pytest.raises(ValueError, match="device buffer"):
        encode_macros(macro, count=1, size=2, protocol_version=12)
    with pytest.raises(ValueError, match="does not support"):
        encode_macros(
            ((MacroStep("delay", milliseconds=10),),), count=1, size=30, protocol_version=9
        )


def test_macro_encoder_requires_reported_macro_count() -> None:
    with pytest.raises(ValueError, match="exactly the device's 2 macro slots"):
        encode_macros(((),), count=2, size=8, protocol_version=12)
