# Protocol command reference

This reference concerns Nape firmware `v1.3.0-ZK` only.
The CLI rejects every other version before configuration queries.
Packet evidence comes from the [published-image analysis](../research/nape-1.3.0.md) and [Launcher source review](launcher-verification.md).
Passing 1.3.0 device checks are read-only; setter behavior and persistence remain unverified on hardware.
See the [hardware matrix](hardware-tests.md), [CLI reference](cli-reference.md), and [configuration guide](configuration.md).
Do not use this document to bypass guarded apply with arbitrary packets.

## Transport

- Link-KM receiver `3434:D026` and USB Nape Pro `3434:0440` use collection `FF60:61`.
- Payloads contain 32 bytes, command first, zero-padded.
  Hidapi output adds a leading zero report-ID byte; received payloads contain 32 bytes.
- The numbered `008C:01` bridge collection is a separate channel.
  Do not use keyboard or normal mouse collections for configuration.
- USB skips receiver commands `B1`, `B2`, and `B3`.
  Discover paths and interfaces rather than hardcoding them.
- Requests run serially and match command, subcommand, and echoed target fields.
  Unrelated `BC` receiver notifications and asynchronous `A3` reports are skipped.
  There are no transaction IDs; timeouts abort rather than implying empty records.

Offsets below are zero-based within the payload, excluding the report-ID prefix.
The reader expects nine user layers, seven row-0 buttons per layer, and five stored DPI stages.

## Read layouts

| Prefix | Meaning | Response decoding |
|---|---|---|
| `A1` | Nape firmware | NUL-terminated ASCII at byte 1; exact token `v1.3.0-ZK` |
| `11` | User keymap layer count | Byte 1, expected 9 |
| `A3` | Effective layer | Byte 1; distinct from default layer during temporary layer actions |
| `A7 35` | Default layer | Byte 2 |
| `A7 20` | Effective orientation | Byte 2 × 45 degrees |
| `A7 21` | Selected DPI stage | Byte 2, `0..4`; low nibble of the persisted stage byte |
| `A7 24 stage` | Stored stage DPI | LE16 at bytes `2..3` |
| `A7 36` | Custom DPI | LE16 at bytes `2..3`, `400..4000` |
| `A7 3A` | Scroll-mode DPI candidate | LE16 at bytes `2..3`, `40..4000`; getter substitutes 400 for an invalid stored value |
| `A7 3C` | Enabled cycling count | Byte 2, `1..5`; high nibble of the persisted stage byte |
| `A7 0B` | Sleep fields | Backlight/sleep/magnet-scan LE16 at `3..4`, `5..6`, `7..8` |
| `A7 0D` | Polling rates | Primary bitmap/index `5/6`, secondary bitmap/index `10/11` |
| `A7 31` | Battery | Percentage byte 2, charging byte 3 |
| `A7 38 layer` | User-layer angle | Byte 2 × 45; CLI restricts layer to `0..8` |
| `12 offset_hi offset_lo 0E` | Seven row-0 bindings | Echo `1..3`, seven BE16 keycodes starting at byte 4 |
| `14 layer 00 direction` | Encoder 0 binding | Echo `1..3`, BE16 keycode at `4..5` |
| `A7 26 layer 00 column` | Tap-hold record | Echo target at `2..4`, tap LE16 `5..6`, held LE16 `7..8` |
| `A7 28 index` | Combo record | Index 2, timeout LE16 `3..4`, layer 5, columns 6, tap LE16 `7..8`, held LE16 `9..10` |
| `A7 2A` | Gesture actions | Four LE16 values at `2..9`, ordered up/down/left/right |
| `A7 33` | Force gesture/scroll | Gesture byte 2 and scroll byte 3, each `0..15` |
| `01` | VIA protocol | BE16 at `1..2`, observed 12 |
| `0C` | Macro slot count | Byte 1, observed 16 |
| `0D` | Macro capacity | BE16 at `1..2`, observed 2394 |
| `0E offset_hi offset_lo size` | Macro chunk | Echo `1..3`, data at byte 4, at most 28 bytes |
| `B1` | Receiver protocol/features | LE16 `1..2`, raw features `3..4` |
| `B2` | Receiver paired slots | Records at 2, 7, 12: VID BE16, PID BE16, status byte |
| `B3` | Receiver firmware | NUL-terminated ASCII at byte 1 |

Keymap offset is `layer * 14`.
Button columns are `03`, `04`, `01`, `02`, `M1`, `M2`, `Press` in order.
Encoder directions are 0 for CCW and 1 for CW.
Polling index/bitmap bits decode to `8000,4000,2000,1000,500,250,125` Hz.
This table does not establish support for every rate; use the advertised bitmap.
The CLI preserves the raw secondary index even when its capability bitmap is zero.

Absent tap-holds and out-of-count combos return unchanged requests.
`--records` reads 30 combo indices and all 63 accessible tap-hold targets.
Snapshots include `null` for confirmed absence, never for a timeout.
Each store has capacity for 30 records.

## Guarded setter layouts

These payloads are constructed only from validated changes through `apply`.
Every write needs explicit `--write`, a new fsynced complete configuration backup, and final read-back.
Receiver writes require only Nape `3434:4004` connected in slot 0.

| Prefix | Meaning |
|---|---|
| `A7 23 stage dpi_lo dpi_hi` | Store LE16 stage DPI; stages `0..4`; handler does not clamp the value |
| `A7 22 stage` | Select stage `0..4`, below the resulting enabled count |
| `A7 37 dpi_lo dpi_hi` | Custom DPI, clamped by firmware to `400..4000`; CLI rejects targets outside the range |
| `A7 3B dpi_lo dpi_hi` | Scroll-mode DPI candidate, clamp `40..4000`; CLI rejects out-of-range targets |
| `A7 3D count` | Enable `1..5` cycling stages |
| `A7 0C backlight_lo backlight_hi sleep_lo sleep_hi magnet_lo magnet_hi` | Store merged sleep fields; units and zero semantics unverified |
| `A7 34 angle_units` | Store effective orientation, degrees divided by 45 |
| `A7 39 layer angle_units` | Store user-layer orientation; CLI bounds-checks layer and angle |
| `A7 2D layer` | Set default layer, config target `0..8` |
| `A7 25 layer 00 column tap_lo tap_hi held_lo held_hi` | Store one tap-hold pair |
| `A7 2F layer 00 column` | Delete one tap-hold |
| `A7 27 index timeout_lo timeout_hi layer columns tap_lo tap_hi held_lo held_hi` | Store combo index `0..29` |
| `A7 2E index` | Delete one combo and compact the table |
| `A7 29 up_lo up_hi down_lo down_hi left_lo left_hi right_lo right_hi` | Store all four gesture actions |
| `A7 32 gesture scroll` | Store two nibble-valued force modes |
| `A7 0E primary_index secondary_index` | Set primary polling while preserving secondary index |
| `05 layer 00 column keycode_hi keycode_lo` | Store row-0 button binding, BE16 |
| `15 layer 00 direction keycode_hi keycode_lo` | Store encoder 0 binding, BE16 |

Implemented Nape-specific setters require a matching subcommand ACK with payload byte 2 equal to zero.
Sleep also requires zero status.
Polling uses send/read-back verification without a required ACK.
Keymap/encoder writes wait for matching command ACKs; encoder ACKs also match layer and direction.
Macro ACK behavior is described below.

Some firmware handlers ignore settings-backend failures.
Zero status can mean the runtime change succeeded while saving failed.
Immediate read-back checks reported state, not power-cycle persistence.
Failures stop without retry or automatic rollback.

Count growth precedes selecting a newly enabled stage; valid selection precedes count shrinkage.
The CLI rechecks selection before count writes and count state afterward.
Despite release-note wording about additional DPI settings, these handlers still accept five stages and counts `1..5`.

Global and per-layer orientation refer to the same effective-layer storage when targeting that layer.
The firmware does not bounds-check per-layer access, so the CLI limits it to nine user layers.
Switch layers and set global orientation in separate applies.

Combo config indices refer to the original snapshot.
Updates run before descending-index deletions; final read-back checks every shifted and preserved slot.
Tap-hold identifiers are layer/button tuples and remain stable despite internal compaction.
Their deletions run before creations to free capacity.
Bulk-delete sentinels are not exposed.

## Macro transaction

A top-level `0D` is macro capacity; `A7 0D` is polling information.
Macro GET/SET packets use BE16 offsets at `1..2`, size at byte 3, and data at byte 4.
The maximum chunk is 28 bytes.

Protocol-12 encoding uses `00` to end a slot and `01,type,keycode` for tap/down/up types 1/2/3.
Delay is `01 04`, ASCII decimal milliseconds, then `7C`.
Other bytes are text; reserved-opcode text and truncated actions are rejected.
The CLI requires terminators for every reported slot.

Changed complete replacements first save all existing macro bytes in the configuration backup.
The writer resets with `10`, invalidates the final byte with `FF`, transfers all other bytes using `0F`, then finalizes with `00`.
Reset requires a command ACK; every data chunk and marker requires an exact echoed packet.
The writer reads and compares the entire resulting buffer.
There are no automatic retries, blind finalization, or standalone macro-reset commands.
A failure after reset can leave macros empty or invalid.
A no-op sends no reset.

## No-op and unexposed commands

`A7 2B`, `A7 2C`, and host request `A7 30` are no-ops in the analyzed dispatcher.
The firmware separately generates `A7 30` notifications.
Profiles and battery-report configuration are therefore not exposed as settings.
Factory reset, bootloader, flashing, pairing, and delete-all sentinels are outside CLI configuration scope.
No lighting, haptics, motion-sync, debounce, or lift-off-distance support is established for this Nape.

## Sources

- [Published image and reproducible Ghidra analysis](../research/nape-1.3.0.md).
- [Deployed Launcher v1.5.0 bundle](https://launcher.keychron.com/main.be11320b2a72b61b.js).
- [NapeBar protocol implementation](https://github.com/ky0209/NapeBar/blob/main/Sources/NapeBar/Protocol/NapeHID.swift).
- [Launcher command map](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/command-map.md).
- [Mouse/trackball notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/mouse-protocol.md).
- [Bridge/dongle notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/bridge-dongle-protocol.md).
- Local [`firmware.py`](../src/nape_cli/firmware.py), [`channel.py`](../src/nape_cli/channel.py), [`snapshot.py`](../src/nape_cli/snapshot.py), [`protocol.py`](../src/nape_cli/protocol.py), [`apply.py`](../src/nape_cli/apply.py), and [`config.py`](../src/nape_cli/config.py).

These are reverse-engineering sources, not authoritative specifications.
Persistent record layouts, sizes, and RAM addresses remain in the research notes, not editable configuration fields.
