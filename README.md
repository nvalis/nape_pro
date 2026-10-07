# nape-cli

A command-line companion for the Keychron Nape Pro.
It reads configuration, previews partial JSON changes, and applies approved changes with a saved backup and read-back checks.

## Documentation

- [Agent guide](docs/agent-guide.md): inspection workflow and connection troubleshooting.
- [CLI and settings reference](docs/cli-reference.md): commands, options, and JSON fields.
- [Configuration](docs/configuration.md): partial JSON configs, validation, planning, and recovery.
- [Firmware 1.3.0](docs/firmware-1.3.0.md): version-specific limits, record compaction, and backup coverage.
- [Protocol reference](docs/protocol-reference.md): packet layouts and known commands.
- [Named keycodes and actions](docs/action-catalog.md): protocol-12 bindings and physical acceptance checks.
- [Hardware verification status](docs/hardware-tests.md): what has actually been tested on a device.
- [Official Launcher verification](docs/launcher-verification.md): source evidence and safety differences.

## Current status

The CLI supports the Link-KM receiver `3434:D026` and direct USB Nape Pro `3434:0440` through their `FF60:61` Raw HID collections.
Payloads are unnumbered 32-byte reports, distinct from the numbered `008C:01` bridge channel.
Linux discovery uses hidraw when available.
Bluetooth is not implemented.

Only Nape firmware `v1.3.0-ZK` is supported.
The CLI rejects other versions before configuration queries or setters.
Supported settings include custom and scroll-mode DPI, five stored DPI stages, enabled-stage count, default-layer selection, user-layer orientation, keymaps, tap-holds, combos, sleep, gestures, force-scroll, and complete macro replacement.

Core and advanced reads, all user-layer angles, complete record export, and dry-run planning passed on the connected 1.3.0 device through the receiver.
Setter implementation uses published-firmware disassembly and packet tests.
1.3.0 hardware writes, physical effects, and reboot persistence remain unverified.
The [hardware matrix](docs/hardware-tests.md) keeps those claims separate.

`apply` defaults to dry-run.
Writes require `--write --backup NEW_FILE`, the exact `v1.3.0-ZK` firmware token, and a supported USB device or only Nape `3434:4004` awake in receiver slot 0.
On 1.3.0, every configuration write first backs up all accessible records, user-layer angles, keymaps, device settings, gestures, force-scroll, and macro bytes.
It verifies preserved state as well as requested changes afterward.
Failures can leave partial changes; there is no automatic rollback or whole-snapshot restore.
Macro replacement resets the complete store and is not atomic.
Bulk record deletion, profiles, flashing, pairing, and factory reset are not exposed.

## Install

Requires Python 3.11+ and `uv`:

```sh
uv sync --extra hardware
```

The user needs read/write access to the selected `/dev/hidraw*` node.
Discover its current path rather than hardcoding one.
For example, after checking the path, `sudo setfacl -m u:$(id -un):rw /dev/hidraw8` grants temporary access.
That access expires on reconnection.
The Linux hidraw backend avoids libusb's missing usage metadata and kernel-driver detachment.

In WSL, attach the device with `usbipd attach --wsl --busid <busid>` from Windows.
Sharing alone is not attachment, and Windows cannot use the device while attached.
Detach with `usbipd detach --busid <busid>`.
If force-bound, also run `usbipd unbind --busid <busid>` in Administrator PowerShell to restore Windows access.

## Usage

```sh
uv run nape devices
uv run nape devices --json
uv run nape receiver-info
uv run nape status
uv run nape status --advanced
uv run nape export nape-snapshot.json
```

Connect in USB mode or keep the Nape awake in 2.4 GHz mode.
The CLI auto-selects one supported collection.
With multiple candidates, use `--index N` from a fresh default `nape devices` listing.
Indices identify collections, not USB interface numbers or receiver slots.
`receiver-info` selects only a receiver and can work while the Nape is asleep.
Exports never overwrite existing files.

For 1.3.0:

```sh
uv run nape status --advanced --layer-orientations --records
uv run nape export nape-130.json --advanced --layer-orientations --records
```

`--records` reads all 30 combo indices and 63 user-layer/button tap-hold targets.
`--layer-orientations` reads nine user-layer angles.
Standard output separates the effective `active_layer` from the 1.3.0 `default_layer`.
Advanced output includes `scroll_dpi`, whose physical effect is not yet verified.
Snapshots are not flash backups or directly importable configs.
Keep the device stationary; reads are not atomic.

Preview a separate partial config:

```sh
uv run nape validate examples/firmware-130-config.json
uv run nape plan examples/firmware-130-config.json
uv run nape apply examples/firmware-130-config.json --dry-run
uv run nape validate examples/nape-two-layer-config.json
uv run nape plan examples/nape-two-layer-config.json
```

Only after approving the diff, run `nape apply CONFIG --write --backup NEW_FILE`.
The two-layer example sets explicit angles for layers 1 and 2 and creates combo 0 only when empty or already identical.
It refuses to overwrite a different combo and does not delete unrelated slots.
Layer and DPI-stage indices are zero-based.
Button names are `03`, `04`, `01`, `02`, `M1`, `M2`, and `Press`; dial directions are `ccw` and `cw`.
Bindings use four-digit hex keycodes, not symbolic names or host shortcuts.
The [action catalog](docs/action-catalog.md) maps named actions to numeric bindings.

Packet previews send nothing:

```sh
uv run nape protocol get-orientation
uv run nape protocol get-default-layer
uv run nape protocol get-scroll-dpi
uv run nape protocol get-layer-orientation --layer 2
uv run nape protocol set-orientation --angle 90
```

`probe --index N` remains an experimental raw read for other direct mouse collections, not the normal USB/receiver workflow.
A packet preview is not proof of device support.

## Sources

- [Published 1.3.0 analysis](research/nape-1.3.0.md), with reproducible Ghidra scripts.
- [Keychron Launcher](https://launcher.keychron.com/), whose v1.5.0 bundle supplies packet evidence.
- [NapeBar protocol implementation](https://github.com/ky0209/NapeBar/blob/main/Sources/NapeBar/Protocol/NapeHID.swift).
- [Mouse/trackball notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/mouse-protocol.md).
- [Launcher overview](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/overview.md).
- [Command map](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/command-map.md).
- [Bridge/dongle notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/bridge-dongle-protocol.md).

These are reverse-engineering sources, not authoritative firmware specifications.

## Development

```sh
uv sync --extra dev --extra hardware
uv run pytest
uv run ruff check .
uv run ty check src
```
