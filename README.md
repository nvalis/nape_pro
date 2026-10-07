# nape-cli

A small command-line companion for exploring the Keychron Nape Pro instead of relying exclusively on the web configurator.

## Current status

Implemented: HID discovery and read-only Link-KM receiver queries, tested against hardware `3434:D026`. The receiver's **FF60:61 Raw HID collection** accepts unnumbered 32-byte payloads for protocol (`0xB1`), paired-device state (`0xB2`), and firmware (`0xB3`) queries. Unsolicited `0xBC` notifications are skipped when waiting for replies.

Nape read support is also verified through this receiver on firmware **v1.1.6-ZK**: orientation, five DPI stages, battery, polling rate, nine keymap layers, and both encoder directions. `status` reads settings; `export` saves those settings and keycodes to JSON. All Raw HID requests go through a read-command allowlist.

It does **not** write settings yet. Direct USB transport is still unverified. `probe` is experimental, rejects the Link-KM receiver, and sends only read commands. `protocol set-orientation` only prints a packet.

Reference notes:

- [Mouse / Trackball Protocol](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/mouse-protocol.md)
- [Launcher Overview](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/overview.md)
- [Command Map](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/command-map.md)
- [Bridge / Dongle Protocol](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/bridge-dongle-protocol.md)
- [NapeBar protocol implementation](https://github.com/ky0209/NapeBar/blob/main/Sources/NapeBar/Protocol/NapeHID.swift) — Nape-specific layouts, independently checked using device read replies

These notes are not specifications. On the tested receiver, the numbered **008C:01** bridge collection is separate from the unnumbered **FF60:61** collection used by `receiver-info`.

## Install

Requires Python 3.11+ and `uv`:

```sh
uv sync --extra hardware
```

Linux uses the `hidraw` backend when available, avoiding the libusb backend's missing usage metadata and kernel-driver detachment. The user needs read/write access to the relevant `/dev/hidraw*` nodes; check permissions/udev rules if opening fails. Temporary permissions expire on USB reconnection.

In WSL, attach the receiver/device with `usbipd attach --wsl --busid <busid>` from Windows. Sharing alone is not attachment. While attached, the receiver is unavailable to Windows; restore it with `usbipd detach --busid <busid>`.

Receiver and wireless Nape **reads** are supported. Settings writes, direct USB Nape access, and Bluetooth are not yet implemented.

## Usage

List relevant Keychron HID collections (indices are collection indices; multiple collections can share a path):

```sh
uv run nape devices
uv run nape devices --json
```

Read the Link-KM receiver's firmware and paired-device state:

```sh
uv run nape receiver-info
uv run nape receiver-info --json
```

This auto-selects one receiver's Raw HID collection; use `--index` if multiple receivers exist. Slot status fields follow the reverse-engineered layout and are also retained in raw JSON for verification. If no slot reports connected, wake the Nape and check its 2.4 GHz mode before attempting wireless configuration.

Read Nape status or export its pointer settings and all nine keymap layers:

```sh
uv run nape status
uv run nape status --json
uv run nape export nape-snapshot.json
```

These commands require an awake Nape in 2.4 GHz mode. Export never overwrites an existing file. Layer and DPI-stage indices are zero-based. Button names are `03`, `04`, `01`, `02`, `M1`, `M2`, and `Press`; the dial has `ccw`/`cw` keycodes. Keycodes are hex values, not host keyboard shortcuts.

**An export is not a complete firmware backup**: it does not include macros, tap-holds, combos, gestures, or per-layer orientation. It cannot be applied/restored yet. JSON includes raw replies for auditing. Keep the device stationary while reading; the firmware does not offer an atomic snapshot.

Show candidate packets without sending them:

```sh
uv run nape protocol get-orientation
uv run nape protocol get-dpi
uv run nape protocol set-orientation --angle 90
```

Try an explicitly read-only raw HID probe against a listed interface:

```sh
uv run nape probe --index 0 --command orientation
```

The probe output is raw because the reply layout and correct HID report ID/transport still need confirmation on-device. It may time out even when the device is compatible. Do not treat the candidate packet printed by `protocol` as confirmed firmware behavior.

## Development

```sh
uv sync --extra dev --extra hardware
uv run pytest
uv run ruff check .
uv run ty check src
```
