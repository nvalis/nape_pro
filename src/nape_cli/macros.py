"""VIA macro-buffer codecs matching the Keychron Launcher implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TERMINATE = 0
TAP = 1
DOWN = 2
UP = 3
DELAY = 4
CHARACTER_STREAM = 5
DELAY_TERMINATE = 124


@dataclass(frozen=True)
class MacroStep:
    kind: str
    keycode: int | None = None
    milliseconds: int | None = None
    text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.kind in ("tap", "down", "up"):
            assert self.keycode is not None
            return {"type": self.kind, "keycode": f"0x{self.keycode:04X}"}
        if self.kind == "delay":
            return {"type": self.kind, "ms": self.milliseconds}
        return {"type": "text", "text": self.text}


def _step_bytes(step: MacroStep, protocol_version: int) -> bytes:
    if step.kind in ("tap", "down", "up"):
        assert step.keycode is not None
        action = {"tap": TAP, "down": DOWN, "up": UP}[step.kind]
        return (
            bytes((1, action, step.keycode))
            if protocol_version >= 11
            else bytes((action, step.keycode))
        )
    if step.kind == "delay":
        if protocol_version < 11:
            raise ValueError("this VIA protocol version does not support macro delays")
        assert step.milliseconds is not None
        digits = str(step.milliseconds).encode("ascii")
        return bytes((1, DELAY)) + digits + bytes((DELAY_TERMINATE,))
    assert step.text is not None
    try:
        text = step.text.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError("macro text may contain only characters with code points 0..255") from exc
    reserved = {TERMINATE, 1} if protocol_version >= 11 else {TERMINATE, TAP, DOWN, UP, DELAY}
    if any(value in reserved for value in text):
        raise ValueError("macro text contains a reserved opcode for this VIA protocol version")
    return text


def encode_macros(
    macros: tuple[tuple[MacroStep, ...], ...], *, count: int, size: int, protocol_version: int
) -> bytes:
    """Encode the Launcher macro step model into a full-size VIA buffer."""
    if len(macros) != count:
        raise ValueError(f"macros must contain exactly the device's {count} macro slots")
    if not 0 <= size <= 65535:
        raise ValueError("macro buffer size is outside the VIA 16-bit range")
    encoded = bytearray()
    for macro in macros:
        for step in macro:
            encoded.extend(_step_bytes(step, protocol_version))
        encoded.append(TERMINATE)
    if len(encoded) > size:
        raise ValueError(f"encoded macros need {len(encoded)} bytes; device buffer has {size}")
    return bytes(encoded).ljust(size, b"\x00")


def _decode_delay(data: bytes, offset: int) -> tuple[int, int]:
    end = data.find(bytes((DELAY_TERMINATE,)), offset)
    if end == -1:
        raise ValueError("unterminated macro delay")
    digits = data[offset:end]
    if not digits or any(not 48 <= value <= 57 for value in digits):
        raise ValueError("invalid macro delay encoding")
    return int(digits.decode("ascii")), end + 1


def decode_macros(data: bytes, *, count: int, protocol_version: int) -> list[list[dict[str, Any]]]:
    """Decode macro actions using Launcher v9/v11 buffer rules."""
    macros: list[list[dict[str, Any]]] = []
    offset = 0
    for _ in range(count):
        steps: list[dict[str, Any]] = []
        text = bytearray()

        def flush_text() -> None:
            if text:
                steps.append({"type": "text", "text": text.decode("latin-1")})
                text.clear()

        while offset < len(data):
            opcode = data[offset]
            offset += 1
            if opcode == TERMINATE:
                break
            if protocol_version >= 11 and opcode == 1:
                if offset >= len(data):
                    raise ValueError("truncated macro action")
                action = data[offset]
                offset += 1
                if action in (TAP, DOWN, UP):
                    if offset >= len(data):
                        raise ValueError("truncated macro key action")
                    flush_text()
                    kind = {TAP: "tap", DOWN: "down", UP: "up"}[action]
                    steps.append({"type": kind, "keycode": f"0x{data[offset]:04X}"})
                    offset += 1
                    continue
                if action == DELAY:
                    milliseconds, offset = _decode_delay(data, offset)
                    flush_text()
                    steps.append({"type": "delay", "ms": milliseconds})
                    continue
                # Launcher consumes unknown marker/type pairs without emitting text.
                continue
            if protocol_version < 11 and opcode in (TAP, DOWN, UP):
                if offset >= len(data):
                    raise ValueError("truncated legacy macro key action")
                flush_text()
                kind = {TAP: "tap", DOWN: "down", UP: "up"}[opcode]
                steps.append({"type": kind, "keycode": f"0x{data[offset]:04X}"})
                offset += 1
                continue
            if protocol_version < 11 and opcode == DELAY:
                milliseconds, offset = _decode_delay(data, offset)
                flush_text()
                steps.append({"type": "delay", "ms": milliseconds})
                continue
            text.append(opcode)
        else:
            raise ValueError("incomplete macro buffer: missing slot terminator")
        flush_text()
        macros.append(steps)
    return macros
