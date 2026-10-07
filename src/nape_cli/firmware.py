"""The single supported Nape firmware contract."""

from __future__ import annotations

from dataclasses import dataclass

FIRMWARE_TOKEN = "v1.3.0-ZK"
DPI_STAGE_LIMIT = 5
RECORD_LIMIT = 30
CUSTOM_DPI_RANGE = (400, 4000)
SCROLL_DPI_RANGE = (40, 4000)


@dataclass(frozen=True)
class FirmwareCapabilities:
    version: str
    supported: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration_writes": self.supported,
            "layer_orientations": self.supported,
            "default_layer": self.supported,
            "scroll_dpi": self.supported,
            "record_inventory": self.supported,
            "dpi_stages": DPI_STAGE_LIMIT,
            "combo_capacity": RECORD_LIMIT,
            "tap_hold_capacity": RECORD_LIMIT,
        }


def capabilities(firmware: str) -> FirmwareCapabilities:
    version = firmware.split(" ", 1)[0]
    return FirmwareCapabilities(version, supported=version == FIRMWARE_TOKEN)


def require_firmware(firmware: str) -> FirmwareCapabilities:
    support = capabilities(firmware)
    if not support.supported:
        raise ValueError(
            f"unsupported Nape firmware {support.version!r}; only {FIRMWARE_TOKEN} is supported"
        )
    return support
