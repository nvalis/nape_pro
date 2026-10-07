"""Verify the pinned firmware and extract review files from the Ghidra export."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

SHA256 = "e54dd28fc8ec9bd5e4562d3fb3077ea9b40c16772453efe091c790ae2cf06a76"
URL = (
    "https://launcher.keychron.com/static/device/875824192/bin/"
    "01a05725-997a-74ac-befb-4673b15ba939.bin"
)
BASE = 0x0402D000
COPIES = (
    (0x00100C00, 0x0406F814, 0x19D0),
    (0x001025D0, 0x040711E4, 0x327C),
    (0x00119C00, 0x0402D8E8, 0x11D90),
    (0x0012B990, 0x0403F678, 0x8E8),
    (0x0012C278, 0x0403FF60, 0xBB8),
)
FOCUS = {
    "0011a92c",  # combo runtime rebuild
    "0011ab20",  # combo deletion runtime update
    "0011d738",  # effective layer
    "0011d95c",  # default layer
    "0011ffd4",  # pointer/scroll mode DPI consumers
    "04048d20",  # misc dispatcher
    "04048f0c",  # raw HID dispatcher
    "0404bcac",  # save all Nape records
    "0404bddc",  # tap-hold deletion
    "0404c2ac",  # tap-hold runtime rebuild
    "0404c3d0",  # gesture runtime rebuild
    "0404c598",  # effective pointer DPI
    "0404c62c",  # scroll mode DPI candidate
    "0404c7fc",  # effective orientation
    "0404c80c",  # orientation setter
    "0404c898",  # Nape subcommand dispatcher
    "0404d050",  # event dispatch
    "0404d4c4",  # persistent default layer update
    "04050b00",  # settings backend save
}


def export(directory: Path) -> None:
    image = (directory / "nape-pro-1.3.0.bin").read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if digest != SHA256:
        raise ValueError(f"Firmware SHA-256 mismatch: {digest}")
    if len(image) != 292812:
        raise ValueError("Unexpected firmware length")
    if struct.unpack_from("<I", image, 0x1C8)[0] != BASE:
        raise ValueError("Unexpected image base")
    if struct.unpack_from("<I", image, 0x604)[0] != 0x0402D859:
        raise ValueError("Unexpected reset vector")
    output = directory / "export"
    c = (output / "decompiled.c").read_text()
    sections = re.split(r"(?=\n/\* [0-9a-f]{8} )", c)
    selected = []
    found = set()
    for section in sections:
        match = re.search(r"/\* ([0-9a-f]{8}) (\w+) \*/", section)
        if match and match[1] in FOCUS:
            selected.append(section)
            found.add(match[1])
    if missing := FOCUS - found:
        raise ValueError(f"Missing Ghidra functions: {sorted(missing)}")
    (output / "protocol-focus.c").write_text(
        "/* Ghidra-generated pseudocode, not original source or compilable C.\n"
        " * Review the assembly when loops or types look wrong.\n"
        f" * Image SHA-256: {SHA256}\n */\n" + "".join(selected)
    )
    targets = {}
    for command in range(0x20, 0x3E):
        offset = 0x1F8AC + (command - 0x20) * 2
        halfword = struct.unpack_from("<H", image, offset)[0]
        targets[f"{command:02x}"] = f"{0x0404C8AC + halfword * 2:08x}"
    (output / "nape-jump-table.tsv").write_text(
        "subcommand\ttarget\n"
        + "".join(f"{command}\t{target}\n" for command, target in targets.items())
    )
    (output / "strings.tsv").write_text(
        "file_offset\tflash_address\ttext\n"
        + "".join(
            f"{match.start():08x}\t{BASE + match.start():08x}\t{match[0][:-1].decode('ascii')}\n"
            for match in re.finditer(rb"[\x20-\x7e]{5,}\x00", image)
        )
    )
    manifest = {
        "url": URL,
        "sha256": digest,
        "bytes": len(image),
        "language": "ARM:LE:32:v8-m",
        "flash_base": f"{BASE:08x}",
        "ram_copies": [
            {"destination": f"{dest:08x}", "source": f"{src:08x}", "bytes": size}
            for dest, src, size in COPIES
        ],
        "nape_subcommand_targets": targets,
        "hardware_validation": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Verified 1.3.0 and extracted {len(selected)} protocol functions into {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    export(parser.parse_args().directory)
