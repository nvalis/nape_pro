# Nape Pro 1.3.0 disassembly notes

This is static analysis of Keychron's published 1.3.0 image, not hardware testing of 1.3.0.
The connected device was not flashed, reset, or queried during this analysis.
The static analysis did not change device configuration.
Subsequent read-only CLI checks are recorded separately in `docs/hardware-tests.md`.

## Image and artifacts

- Download URL: https://launcher.keychron.com/static/device/875824192/bin/01a05725-997a-74ac-befb-4673b15ba939.bin
- Metadata API: https://launcher.keychron.com/vapi/v2/firmware/875824192
- Size: 292,812 bytes.
- SHA-256: `e54dd28fc8ec9bd5e4562d3fb3077ea9b40c16772453efe091c790ae2cf06a76`.
- Embedded version: `v1.3.0-ZK`.
- Embedded build date and time: `Aug 20 2026 08:35:53`.
- Zephyr build string: `c723bd0fd29d`.
- Analysis tool: Ghidra 12.1.2 DEV, language `ARM:LE:32:v8-m`.

The local image, Ghidra project, and generated exports live under `snapshots/firmware/1.3.0/`.
That directory is already excluded from Git by the project's `snapshots/` rule.

Start with these exports:

| File under `snapshots/firmware/1.3.0/export/` | Contents |
|---|---|
| `protocol-focus.c` | Nape protocol and related runtime functions, extracted from the decompiler output |
| `disassembly.txt` | Discovered functions and their ARM instructions |
| `decompiled.c` | Full generated pseudocode |
| `functions.tsv` | Function addresses and names |
| `references.tsv` | Instruction references and calls |
| `memory.tsv` | Imported memory blocks |
| `nape-jump-table.tsv` | The binary's `20..3D` subcommand destinations |
| `strings.tsv` | NUL-terminated ASCII strings with file offsets and flash addresses |
| `manifest.json` | Pinned image identity and reconstructed mappings |

The pseudocode is not original source and is not compilable C.
Some decompiled loops are wrong, notably the compacting loops in combo and tap-hold deletion.
Use the assembly to check those paths.
The full export also contains startup and library decoding warnings, and includes some flash copies of functions that execute in RAM.
Do not interpret its function count as a count of unique source functions.

## Load addresses

The image base is `0402D000`, recorded at file offset `1C8`.
The vector table begins at file offset `600`, address `0402D600`.
The reset vector is `0402D859`, whose Thumb instructions start at file offset `858`.
Startup writes the flash vector-table address into VTOR.

Startup at `0402D898` and `04067940` copies these initialized sections:

| Destination | Source in flash | Length | Interpretation |
|---|---|---|---|
| `00100C00` | `0406F814` | `19D0` | Initialized data |
| `001025D0` | `040711E4` | `327C` | Initialized data |
| `00119C00` | `0402D8E8` | `11D90` | RAM-executed code |
| `0012B990` | `0403F678` | `8E8` | Additional initialized RAM section |
| `0012C278` | `0403FF60` | `BB8` | Additional initialized RAM section |

These copies matter.
For example, an interrupt vector into `0011BE90` points to code loaded from file offset `2B78`, not to a missing part of the update image.
Importing only a flat flash block leaves calls into RAM unresolved.
The scripts map uninitialized RAM as uninitialized memory, not as fabricated zero-filled device state.
The exact MCU model has not been identified.

## Command dispatch

| Address | Name assigned during analysis | Role |
|---|---|---|
| `04048F0C` | `launcher_raw_hid_dispatch` | Top-level VIA/Keychron packet dispatcher |
| `04048D20` | `launcher_misc_dispatch` | Generic `A7` miscellaneous commands and Nape fallback |
| `0404C898` | `nape_subcommand_dispatch` | Nape cases `20..3D` |
| `0404BCAC` | `nape_save_all_records_candidate` | Saves the four Nape settings records |
| `04050B00` | `settings_save_one_candidate` | Calls the settings backend's save operation under a lock |

The top-level `A7` case passes `packet + 1` to the misc dispatcher.
Consequently, `param_1[0]` in the Nape pseudocode is the subcommand, and `param_1[1]` is byte 2 of the full HID payload.
All offsets below refer to the full HID payload, including `A7` at byte 0.

The raw dispatcher sends the mutated packet after processing it.
Most successful Nape setters overwrite payload byte 2 with zero.
Several invalid-input paths write one there, but others return the unchanged request.
A zero status byte does not prove persistence: callers generally ignore the settings backend's return value.

## Findings useful for configuration

### DPI and per-layer orientation

| Packet prefix | 1.3.0 implementation | Case address |
|---|---|---|
| `A7 20` | Returns the orientation byte for the effective layer at payload byte 2 | `0404CCDC` |
| `A7 21` | Returns the selected DPI stage from the low nibble of settings byte 10 | `0404CCD0` |
| `A7 22 stage` | Accepts stages `0..4`, updates the low nibble, emits a runtime event, and saves settings | `0404CCE8` |
| `A7 23 stage dpi_lo dpi_hi` | Stores a LE16 value for stages `0..4`; this handler does not clamp the DPI value | `0404CCB2` |
| `A7 24 stage` | Returns that stage's LE16 DPI at payload bytes 2 and 3; invalid stage returns zero | `0404CC98` |
| `A7 35` | Returns the byte read by the default-layer getter candidate | `0404C9E4` |
| `A7 36` | Returns custom DPI as LE16 at payload bytes 2 and 3 | `0404C9D6` |
| `A7 37 dpi_lo dpi_hi` | Clamps custom DPI to `400..4000`, stores it, and saves settings | `0404C9AA` |
| `A7 38 layer` | Replaces payload byte 2 with the requested layer's orientation byte | `0404C9A0` |
| `A7 39 layer angle` | Stores the angle byte for the layer; angle above 7 becomes zero | `0404C984` |
| `A7 3A` | Returns the LE16 field at settings offset 25; invalid stored range returns 400 | `0404C962` |
| `A7 3B value_lo value_hi` | Clamps that field to `40..4000`, stores it, and saves settings | `0404C93A` |
| `A7 3C` | Returns the enabled DPI-stage count from the high nibble of settings byte 10 | `0404C92E` |
| `A7 3D count` | Accepts only `1..5`, updates the high nibble, and saves settings | `0404C90E` |

`A7 35`, `A7 3A`, and `A7 3B` are additional handlers found in the binary.
The `35` helper at `0011D95C` reads a global default-layer byte, whereas `20` and top-level `A3` use the effective-layer helper at `0011D738`.
These layers can differ when temporary layers are active.

The `3A/3B` field looks like scroll-mode DPI.
Its getter at `0404C62C` supplies the same sensor-configuration routine as the normal DPI getter, but on the force-scroll branch of the RAM function at `0011FFD4`.
That is a static-analysis interpretation, not a verified UI name or physical behavior.

Despite the 1.3.0 release note about increasing DPI settings, these packet handlers still accept five stages and a count no greater than five.
Do not expand the CLI's accepted count based on the release note alone.
The per-layer getter and setter do not bounds-check the layer byte in this function.
Client-side validation is essential; do not experiment with out-of-range layers on hardware.

### Storage layout

The handler saves `nape/settings` from RAM address `001077D0`, length 27 bytes.

| Record offset | Size | Interpretation |
|---|---|---|
| `0..9` | 10 | Orientation bytes indexed by layer; exact user-visible layer correspondence remains unverified |
| `10` | 1 | Low nibble: selected DPI stage; high nibble: enabled stage count |
| `11..20` | 10 | Five LE16 stage DPI values |
| `21` | 1 | Low nibble: force-gesture value; high nibble: force-scroll value |
| `22` | 1 | Layer byte stored by `A7 2D` |
| `23..24` | 2 | Custom DPI, LE16 |
| `25..26` | 2 | Scroll-mode DPI candidate, LE16 |

Other persistent records are:

| Name | RAM address | Saved bytes | Layout |
|---|---|---|---|
| `nape/combos` | `00109928` | 241 | One count byte plus up to 30 eight-byte records |
| `nape/gesture` | `00109920` | 8 | Four LE16 keycodes |
| `nape/tapholds` | `0010984C` | 211 | One count byte plus up to 30 seven-byte records |

A combo record contains LE16 timeout, layer byte, columns byte, LE16 tap action, and LE16 hold action.
A tap-hold record contains layer, row, column, LE16 tap action, and LE16 hold action.
The combo setter raises the count to `index + 1` when needed; the tap-hold setter searches the layer/row/column tuple before appending.

### Empty reads, deletion, and profiles

- `A7 26` returns the unchanged request when no matching tap-hold record exists.
- `A7 28` returns the unchanged request when the requested index is outside the stored combo count.
- Combo deletion compacts the records and decrements the count, rather than keeping stable empty slots.
- The combo deletion handler has an all-records sentinel of `FF`.
- Tap-hold deletion has an all-records sentinel with layer, row, and column all `FF`.
- Profile commands `2B` and `2C`, and command `30`, reach the no-op return in this dispatcher.
  The firmware separately generates `A7 30` notifications, so the empty request handler does not imply that notifications are absent.

Those delete-all sentinels are documented as binary evidence, not as CLI features or instructions to try them.
No deletion or other setter was sent to the device.

### Compaction assembly review

LLVM's Cortex-M55 instruction decoder confirms the low-overhead loop instructions that Ghidra renders incorrectly.
This decoder choice does not identify the device's MCU.
For combo deletion, `0404CA70` starts the loop with `DLS lr, lr`.
The `LE` instruction at `0404CA92`, bytes `0F F0 11 C8`, branches to `0404CA74`, not Ghidra's displayed `0404CA76`.
The body copies both four-byte halves of the next eight-byte record over the current record.
After shifting through the old final record, the handler clears that final slot and decrements the count.
Tap-hold deletion at `0404BDDC` similarly copies each seven-byte record as four bytes, two bytes, and one byte, then clears the final slot and decrements the count.
These are compaction loops, not stable-slot deletion or the broken infinite loops shown by generated pseudocode.

## Reproduce the analysis

Install Ghidra and its supported JDK, then run from the project root:

```bash
GHIDRA_HOME=/opt/ghidra bash research/disassemble_nape130.sh
```

The script downloads the pinned image if absent, verifies its hash, imports it, reconstructs the RAM copies, seeds the protocol functions, and exports the results.
It overwrites only the generated `Nape130v8m` analysis program and exports.
It does not access HID devices.

The preparation, annotation, and export scripts are in `research/ghidra/`.
`research/export_nape130.py` verifies the image identity and extracts the protocol review files from the full export.

## Next checks

The CLI now supports only `v1.3.0-ZK`, with packet tests and separate read-only device checks.
Experimental configuration writes require an explicit request, a complete backup, setter-status checks, and preserved-state read-back.
Hardware setter acceptance, restoration, physical effects, and reboot persistence remain pending tests.
Binary evidence and reported getter state must not be presented as completed write or persistence verification.
