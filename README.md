# nape-cli

A small command-line companion for exploring the Keychron Nape Pro instead of relying exclusively on the web configurator.

## Documentation

- [Agent guide](docs/agent-guide.md): safe inspection workflow, configuration limitations, and connection troubleshooting.
- [CLI and settings reference](docs/cli-reference.md): every CLI command/option, JSON field, and feature's support status.
- [Configuration](docs/configuration.md): partial pointer/keymap JSON, validation/planning, and guarded apply with snapshot and verification.
- [Protocol reference](docs/protocol-reference.md): verified read layouts and the full known NAPE command list, including unimplemented settings.
- [Named keycodes and actions](docs/action-catalog.md): protocol-12 lookup tables, natural-language recipes, and physical acceptance checks.
- [Hardware verification status](docs/hardware-tests.md): current coverage and remaining verification gaps.
- [Official Launcher verification](docs/launcher-verification.md): current source evidence and safety differences.

## Current status

Implemented: HID discovery and read-only Link-KM receiver queries, tested against hardware `3434:D026`. The receiver's **FF60:61 Raw HID collection** accepts unnumbered 32-byte payloads for protocol (`0xB1`), paired-device state (`0xB2`), and firmware (`0xB3`) queries. Unsolicited `0xBC` notifications are skipped when waiting for replies.

Nape read support is also verified through this receiver on firmware **v1.1.6-ZK**: orientation, five DPI stages, battery, polling rate, nine keymap layers, both encoder directions, and the VIA macro buffer. `status` reads core settings; `status --advanced` and `export --advanced` also read optional settings, gestures, force-scroll, and macros. On tested firmware the custom-DPI and DPI-stage-count queries echo their request, so the CLI reports these fields as `null` and refuses configs that target them; sleep and the other advanced reads succeed. `export --layer-orientations` is separate because the tested firmware echoes the requested layer instead of returning a usable angle, and the command fails safely. DPI values/selection, orientation, active layer, polling, button/encoder bindings, tap-hold records, existing combo updates, sleep, gestures/force-scroll, and full macro replacement have passed hardware storage/read-back tests. Custom DPI, stage count, and per-layer orientation remain unavailable on this firmware. Physical action execution and reboot persistence are not established. Macro replacement uses the Launcher reset/invalidate/transfer/finalize sequence and can leave macros empty or invalid if interrupted. Active-layer reads use the unchanged wire index, and polling writes preserve the secondary polling field. Read requests go through a read-command allowlist; experimental setters use a separate, restricted write path.

`validate` checks partial pointer/keymap, custom-DPI, stage-count, sleep, active-layer, tap-hold, combo, gesture, macro, and orientation configs offline; `plan` compares supported entries with the device without writing. See [Configuration](docs/configuration.md).

`apply` defaults to dry-run. Guarded writes require **`--write --backup NEW_FILE`** and are restricted to firmware `v1.1.6-ZK`, with only Nape `3434:4004` awake in receiver slot 0. The [hardware matrix](docs/hardware-tests.md) covers the available configuration families, including full macro replacement and exact restoration; successful storage read-back does not prove runtime behavior. Combo deletion/empty-slot creation remain untested. Structured/raw macro replacements reset the entire macro store only after a full-buffer backup has been saved; every chunk is ACKed without automatic retry. See the [verification status](docs/hardware-tests.md). Read-back verifies all pointer fields and the complete expected keymap, including omitted entries, plus requested active-layer, targeted advanced records, gesture/scroll state, requested device settings/macros, and the preserved secondary polling index. For an active-layer-only switch, the context-dependent orientation readout is not compared with the previous layer. Failures may leave partial changes and are not automatically rolled back.

Direct USB transport is still unverified. `probe` rejects the Link-KM receiver and sends only read commands. `protocol set-orientation` only prints a packet.

Reference notes:

- [Mouse / Trackball Protocol](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/mouse-protocol.md)
- [Launcher Overview](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/overview.md)
- [Command Map](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/command-map.md)
- [Bridge / Dongle Protocol](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/bridge-dongle-protocol.md)
- [NapeBar protocol implementation](https://github.com/ky0209/NapeBar/blob/main/Sources/NapeBar/Protocol/NapeHID.swift) — Nape-specific layouts, independently checked using device read replies
- [Keychron Launcher](https://launcher.keychron.com/) — advanced packet layouts were checked against the deployed Launcher v1.5.0 JavaScript bundle; not a firmware specification

These notes are not specifications. On the tested receiver, the numbered **008C:01** bridge collection is separate from the unnumbered **FF60:61** collection used by `receiver-info`.

## Install

Requires Python 3.11+ and `uv`:

```sh
uv sync --extra hardware
```

Linux uses the `hidraw` backend when available, avoiding the libusb backend's missing usage metadata and kernel-driver detachment. The user needs read/write access to the relevant `/dev/hidraw*` nodes; check permissions/udev rules if opening fails. Temporary permissions expire on USB reconnection.

In WSL, attach the receiver/device with `usbipd attach --wsl --busid <busid>` from Windows. Sharing alone is not attachment. While attached, the receiver is unavailable to Windows. Detach with `usbipd detach --busid <busid>`; **if force-bound**, Windows access also requires `usbipd unbind --busid <busid>` in Administrator PowerShell. Detaching alone does not undo force-binding.

Receiver and wireless Nape reads are supported, with guarded pointer/keymap writes and Launcher-derived experimental active-layer, tap-hold, combo, gesture, force-scroll, and per-layer-orientation operations, plus custom-DPI, DPI-stage-count, sleep, and complete macro replacement. See the [hardware matrix](docs/hardware-tests.md) for tested setters and limitations. On the tested firmware custom-DPI and stage-count reads are unavailable, while the per-layer orientation read is unusable and guarded planning stops before those setters. Direct USB Nape access and Bluetooth remain unimplemented. Profile selection has no usable operation in the official Nape code and remains unsupported.

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
uv run nape status --advanced
uv run nape export nape-advanced.json --advanced
# This will fail safely on tested firmware until GET_LAYER_ORI is understood:
uv run nape export nape-layers.json --layer-orientations
```

These commands require an awake Nape in 2.4 GHz mode. Export never overwrites an existing file. Layer and DPI-stage indices are zero-based. Button names are `03`, `04`, `01`, `02`, `M1`, `M2`, and `Press`; the dial has `ccw`/`cw` keycodes. Keycodes are hex values, not host keyboard shortcuts. The [action catalog](docs/action-catalog.md) translates named actions such as mouse Back and vertical scrolling to numeric bindings; symbolic names are reference labels, not accepted JSON inputs.

A standard export is not a complete firmware backup. `export --advanced` includes gestures, force-scroll settings, decoded macro slots, and the raw VIA macro buffer. Tap-holds and combos are queried only for explicit targets in a config, not bulk-exported. Per-layer orientation export is a separate, currently failing query on the tested firmware. Profiles are not exposed by the current Launcher. Snapshots cannot be applied wholesale. JSON includes raw replies for auditing. Keep the device stationary while reading; the firmware does not offer an atomic snapshot.

Validate and preview a partial configuration:

```sh
uv run nape validate examples/pointer-config.json
uv run nape plan examples/pointer-config.json
uv run nape apply examples/pointer-config.json --dry-run
uv run nape validate examples/keymap-config.json
uv run nape plan examples/keymap-config.json
```

After reviewing the diff and explicitly choosing to write, use `nape apply CONFIG --write --backup NEW_FILE`. See [Configuration](docs/configuration.md) for limitations and recovery guidance. Exported snapshots are not accepted as configs.

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
