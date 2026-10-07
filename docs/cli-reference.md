# CLI and settings reference

Only Nape firmware `v1.3.0-ZK` is supported, including its optional build timestamp.
The CLI checks the firmware token before configuration reads and refuses every other version.
Supported transports are Link-KM `3434:D026` and direct USB Nape `3434:0440`, using `FF60:61` Raw HID.
Bluetooth is not implemented.
See the [hardware matrix](hardware-tests.md) for completed device checks and the [1.3.0 guide](firmware-1.3.0.md) for packet-derived limits.
Configuration setters, most physical effects, and reboot persistence remain unverified on hardware.

## Commands

Prefix commands with `uv run` from the repository.
Global options are `nape --help`, `nape -h`, and `nape --version`.
Every subcommand also accepts `--help` and `-h`.

| Command | Purpose | Options |
|---|---|---|
| `nape devices` | List relevant Keychron HID collections | `--json`; `--all` for every collection with VID `3434` |
| `nape receiver-info` | Read receiver protocol, firmware, and paired slots | `--index N`; `--timeout-ms 1500`; `--json` |
| `nape status` | Read pointer settings, effective/default layers, and battery | `--advanced`; `--layer-orientations`; `--records`; `--index N`; `--timeout-ms 1500`; `--json` |
| `nape export OUTPUT` | Read settings and all nine keymaps into a new JSON file | Same read flags as status; no overwrite flag |
| `nape validate CONFIG` | Validate a partial config offline | `--json` for normalized config |
| `nape plan CONFIG` | Read state and preview changes; no writes | `--index N`; `--timeout-ms 1500`; `--json` |
| `nape apply CONFIG` | Dry-run by default; optionally apply approved changes | `--write` or `--dry-run`; `--backup NEW_FILE` required with write; `--index N`; `--timeout-ms 1500`; `--json` |
| `nape protocol get-orientation` | Print `A7 20`; send nothing | None required |
| `nape protocol get-dpi` | Print `A7 21`; send nothing | None required |
| `nape protocol get-default-layer` | Print `A7 35`; send nothing | None required |
| `nape protocol get-custom-dpi` | Print `A7 36`; send nothing | None required |
| `nape protocol get-scroll-dpi` | Print `A7 3A`; send nothing | None required |
| `nape protocol get-dpi-stage-count` | Print `A7 3C`; send nothing | None required |
| `nape protocol get-layer-orientation --layer N` | Print `A7 38 N`; send nothing | Layer required in `0..8` |
| `nape protocol set-orientation --angle DEGREES` | Print `A7 34 angle/45`; does not set orientation | Angle required, `0..315` in 45-degree steps |
| `nape probe --index N` | Experimental raw read for another direct mouse collection | `--command orientation` or `dpi`; `--report-id 0`; `--timeout-ms 1000` |

`protocol` never opens hardware.
Its previews show encoding, not completed device tests.
`probe` is not the normal USB Nape/receiver workflow.

## Read flags and selection

`--advanced` adds custom DPI, scroll-mode DPI, enabled-stage count, sleep, gestures, force-scroll, macro metadata, decoded slots, and all raw macro bytes.
`--layer-orientations` adds nine user-layer angles.
`--records` scans 30 combo indices and 63 row-0 layer/button tap-hold targets.
Use all three flags with export to capture every supported configuration family.

`--index` is a nonnegative collection index from a fresh default `nape devices` listing.
Enumeration order can change; do not reuse indices from `devices --all`.
Collections can share a path, and interface numbers are not indices.
One configuration candidate is selected automatically; multiple candidates require an explicit index.
`receiver-info` selects only a receiver.
USB skips receiver-state queries.
Receiver configuration reads require an awake paired Nape, while receiver diagnostics can work with it asleep.

Timeouts are positive milliseconds per request, not per command.
Standard receiver status makes 14 requests; standard export adds 27 keymap/encoder reads.
USB makes one fewer request by skipping `B2`.
Layer angles add nine requests, records add 93, and macro request counts depend on buffer size.
Keep the Nape stationary and awake, close Launcher, and run commands serially.

Normal success exits 0.
Handled argument, device, and file errors exit 2 and print to stderr.
An empty discovery list is still success.
`probe` prints raw data and can succeed with no response.
Its collection pages are `FFC1` or `FF0A`; it refuses Link-KM.

## Snapshot fields

Snapshots are not configs or flash backups and cannot be applied wholesale.
They include raw replies for auditing.
Reads are not atomic, and no whole-snapshot restore command exists.

| Field | Meaning |
|---|---|
| `schema_version` | Snapshot schema 1 |
| `transport` | `link-km-raw-hid` or `usb-raw-hid` |
| `firmware` | Nape version/build string, not receiver firmware |
| `capabilities` | Implemented operations and firmware limits, not completed hardware tests |
| `layer_count` | Nine user keymap layers |
| `active_layer` | Effective wire layer from `A3`; user layers `0..8`, firmware internal layers may differ |
| `default_layer` | Default layer from `A7 35`; can differ during a held layer action; not a config field |
| `orientation` | Effective angle in degrees, `0..315` in 45-degree steps |
| `dpi_index` | Selected stored stage, `0..4` |
| `dpi_values` | Five unsigned LE16 stored DPI values |
| `dpi` | Derived `dpi_values[dpi_index]` |
| `custom_dpi` | Separate custom DPI, `400..4000`; advanced/targeted reads |
| `scroll_dpi` | Scroll-mode DPI candidate, `40..4000`; physical effect unverified |
| `dpi_stage_count` | Enabled cycling count, `1..5`; selection configs also read it |
| `sleep` | Raw unsigned 16-bit `backlight`, `sleep`, and `magnet_scan` fields; units and zero semantics unverified |
| `battery_percent`, `charging` | Battery percentage and charging boolean; not configurable |
| `polling_rate`, `supported_polling_rates` | Current Hz and device-advertised supported rates |
| `polling_rate_for_fr_index` | Raw secondary polling index; preserved and verified by apply, not a config input |
| `polling_rate_for_fr`, `supported_polling_rates_for_fr` | Secondary rate and capabilities; physical meaning unverified |
| `layers` | Nine keymap objects, optionally including angles |
| `layer_orientations` | Angle list when status reads angles without keymaps |
| `gesture` | Four 16-bit directional actions |
| `force_gesture_scroll` | Raw gesture/scroll mode values, each `0..15` |
| `via_protocol_version`, `macro_count`, `macro_buffer_size` | Macro protocol, slot count, and capacity |
| `macro_buffer`, `macros` | Complete raw hex macro bytes and decoded steps |
| `tap_holds`, `combos` | Target-keyed records, with `null` for absence |
| `record_inventory` | `true` when all accessible record targets were queried |
| `raw` | Request hex mapped to full response hex |

Each keymap layer has `layer`, `buttons`, and `dial` fields.
Buttons map `03`, `04`, `01`, `02`, `M1`, `M2`, and `Press` to four-digit hex keycodes.
These names correspond to wire columns `0..6`, row 0.
`Press` is the dial push button; dial rotations use `ccw` and `cw`.
Encoder 0 directions are 0 for CCW and 1 for CW.

Keycodes are firmware action codes, not host shortcuts or arbitrary valid actions.
Use the [action catalog](action-catalog.md) to translate intent into numeric bindings.
The [configuration guide](configuration.md) lists accepted partial inputs, write guards, and recovery.

## Other JSON outputs

`devices --json` is an array, including when empty.
Entries include `index`, integer `vendor_id`/`product_id`, reported labels, integer `usage_page`/`usage`, `interface_number`, and backend-specific `path`.
Usage metadata can be unknown on some backends.

`receiver-info --json` includes receiver `protocol_version`, raw `feature_bytes`, receiver `firmware`, three paired `slots`, and `raw` replies.
Each slot has `slot`, `vendor_id`, `product_id`, `status`, and `connected`.
Connected means status equals 1; slot indices are `0..2` and are not Nape layers or DPI stages.
The CLI does not expose pairing, unpairing, or target-slot selection.

## Deliberately unexposed

Profile requests and host battery-report configuration are no-ops in the analyzed image.
Bulk record deletion, firmware flashing, bootloader, pairing, and factory reset are outside configuration scope.
No debounce, lift-off distance, motion sync, lighting, or haptics support is established for this Nape.
Do not infer support from another Keychron mouse or an enum name.
