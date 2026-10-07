# CLI and settings reference

Scope: `nape-cli` **0.3.0**, Link-KM `3434:D026` firmware `0.1.3` and Nape firmware `v1.1.6-ZK`. See the [current hardware matrix](hardware-tests.md) for storage/read-back coverage and blocked features. Physical actions, reboot persistence, combo deletion and empty-slot creation remain unverified. Use the [named-action catalog](action-catalog.md) for protocol-12 keycode lookup and request translation. `apply` is dry-run unless explicitly authorized with `--write --backup NEW_FILE`; see [configuration](configuration.md). Direct USB Nape access and Bluetooth are not implemented. Start with the [agent guide](agent-guide.md).

## Complete CLI command list

Prefix every command below with `uv run` from the repository. Global flags: `nape --help` (`-h`), `nape --version`. Every subcommand also supports `--help` (`-h`).

| Command | Purpose | Options / defaults |
|---|---|---|
| `nape devices` | List relevant Keychron HID collections | `--json`: JSON array; `--all`: all collections with VID `0x3434` |
| `nape receiver-info` | Read receiver protocol, firmware, paired slots | `--index N`: optional selection; `--timeout-ms 1500`; `--json`: include raw packets |
| `nape status` | Read Nape pointer settings and battery | `--advanced` also reads custom DPI, stage count, sleep, gestures, force-scroll, and macros; `--index N`; `--timeout-ms 1500`; `--json` |
| `nape export OUTPUT` | Read settings and nine keymap layers into a new JSON file | Required file path; `--advanced` reads custom DPI, stage count, sleep, gestures, force-scroll, and macros; `--layer-orientations` separately attempts `GET_LAYER_ORI`; `--index N`; `--timeout-ms 1500`; no overwrite/force flag |
| `nape validate CONFIG` | Validate pointer/keymap, layer, tap-hold, combo, gesture, force-scroll, and macro config offline | Required config path; `--json`: normalized config |
| `nape plan CONFIG` | Read current settings/bindings and preview changes, never write | Required config path; `--index N`; `--timeout-ms 1500`; `--json`: diff |
| `nape apply CONFIG` | Dry-run by default; optionally apply Launcher-defined settings and advanced actions | Required config path; `--write` or `--dry-run` (mutually exclusive); `--backup NEW_FILE` required only with `--write`; `--index N`; `--timeout-ms 1500`; `--json` |
| `nape protocol get-orientation` | Print a zero-padded `A7 20` payload; send nothing | No required options |
| `nape protocol get-dpi` | Print an `A7 21` payload; send nothing | No required options |
| `nape protocol set-orientation --angle DEGREES` | Print `A7 34 angle/45`; **does not set orientation** | `--angle` required, one of `0,45,90,135,180,225,270,315` |
| `nape probe --index N` | Experimental raw read query for a direct mouse collection | `--command orientation` or `dpi` (default `orientation`); `--report-id 0`; `--timeout-ms 1000` |

`protocol` accepts `--angle`, but only uses it for `set-orientation`. Its printed warning is conservative: direct-device framing remains unverified even though receiver reads have worked.

### Selection and errors

- `--index` is a non-negative, zero-based **collection** index from a fresh default `nape devices` listing. Enumeration order can change; do not reuse indices from `devices --all`.
- Multiple collections may share a path; interface numbers and indices are not interchangeable.
- Receiver commands auto-select exactly one `3434:D026`, `FF60:61` collection. They validate explicit selections too. Zero or multiple auto-selection candidates produce an error.
- `status`/`export` require a connected paired slot and exactly nine reported layers. Receiver diagnostics can work while the Nape is asleep.
- Timeouts are positive milliseconds **per request**, not a total command duration. Status makes 13 requests; standard export makes 40. Advanced export adds custom-DPI/count/sleep reads, gesture/scroll reads, and macro metadata/buffer reads (number depends on buffer size). On tested firmware the custom-DPI/count replies echo the query and are reported as unavailable; sleep reads successfully. Layer-orientation queries are separate and fail safely on tested firmware.
- `probe` requires a mouse usage page `FFC1` or `FF0A`, rejects Link-KM `D026`, and is not the normal receiver workflow. Report IDs accept decimal or `0x` notation, range `0..255`. It prints raw bytes and can return success with no response.
- Normal success exits `0`; handled argument/device/file errors exit `2` and write an error to stderr. An empty discovery list is still success. Help/version exit `0`.

The [configuration guide](configuration.md) describes the separate partial-config schema, write guardrails, result JSON, and recovery. Config files are not exported snapshots. Offline validation does not check the connected device's rate support. Apply preview never creates a backup; a write-mode no-op also creates none.

## Available settings and observations

`status --json` and standard `export` contain the same core fields, except that only export includes `layers`. Advanced export adds `custom_dpi`, `dpi_stage_count`, `sleep`, `gesture`, `force_gesture_scroll`, macro metadata, decoded `macros`, and the raw `macro_buffer`. **`orientation`, `active_layer`, `dpi_index`, `dpi_values`, `polling_rate`, partial `layers`, `tap_holds`, `combos`, `gesture`, and `force_gesture_scroll`** are accepted config inputs for guarded apply. `custom_dpi`, `dpi_stage_count`, partial `sleep`, and full `macros` or `macro_buffer` replacements are also supported by guarded apply. Sleep and complete macro storage replacement/restoration are hardware-tested; custom DPI and stage count remain unavailable on tested firmware. Macro writes reset the complete store after backing it up; interrupted transfers may leave it empty or invalid. Profile selection is not supported. See [Launcher source verification](launcher-verification.md).

| JSON field | Meaning / domain | Notes |
|---|---|---|
| `schema_version` | Snapshot schema, currently integer `1` | Metadata, not a firmware setting |
| `transport` | `"link-km-raw-hid"` | Metadata |
| `firmware` | Nape firmware/build string | Not the receiver firmware |
| `layer_count` | Integer `9` on tested firmware | Current reader rejects other counts |
| `active_layer` | Layer index `0..8` | Unchanged wire index, matching Launcher `A3`/`A7 2D`; set/restore hardware-tested. The tested firmware omits the `A7 2D` ACK, so apply verifies by read-back; switching layers also changes the `A7 20` angle readout |
| `orientation` | Reported angle, degrees `0..315` in steps of `45` | Set/restore hardware-tested. The readout changed with active layer on tested firmware (`90°` on layer 1, `0°` on layer 2); this does not establish per-layer orientation support |
| `dpi_index` | Active DPI-stage index `0..4` | Different from a mouse profile or keymap layer |
| `dpi_values` | Five integer DPI values ordered by stage | Read as unsigned 16-bit LE values; valid write range/step not established |
| `dpi` | `dpi_values[dpi_index]` | Derived value |
| `custom_dpi` | Separate custom-DPI value (LE16), or `null` when unavailable | Advanced/targeted reads; write range `1..65535` is an encoding limit, not a sensor specification. The tested firmware echoes the zero-padded query, so this is `null` and cannot be planned/written |
| `dpi_stage_count` | Enabled cycling count `1..5`, or `null` when unavailable | Advanced/targeted reads; five stored values are retained; a selected stage must remain enabled. The tested firmware echoes the zero-padded query, so this is `null` and cannot be planned/written |
| `sleep` | Raw `backlight`, `sleep`, `magnet_scan` unsigned 16-bit fields | Advanced/targeted reads; partial config merges/preserves other fields; units/zero semantics unverified |
| `battery_percent` | Integer `0..100` | Device status, not configurable |
| `charging` | Boolean | Device status |
| `polling_rate` | Current rate in Hz | Decode table: `8000,4000,2000,1000,500,250,125`; this does not imply support for every rate |
| `supported_polling_rates` | List of rates reported by the device | Use this list, not the full decode table, when proposing a rate |
| `polling_rate_for_fr_index` | Raw secondary polling index (byte `11`) | Preserved by primary polling writes and checked on every apply read-back; not a config input |
| `polling_rate_for_fr`, `supported_polling_rates_for_fr` | Secondary rate in Hz (or null when bitmap is zero), and supported rates | Launcher-derived decoding of bytes `11/10`; physical semantics remain unverified |
| `layers` | Nine keymap objects; export only | `--layer-orientations` attempts to add per-layer `orientation`; tested firmware echoes the layer index so this fails safely |
| `gesture`, `force_gesture_scroll` | Four 16-bit directional actions and two raw mode bytes | Advanced export; set/restore storage read-back hardware-tested; physical behavior remains unverified |
| `via_protocol_version`, `macro_count`, `macro_buffer_size`, `macro_buffer`, `macros` | VIA version, slot count, capacity, raw hex, and decoded Launcher-style steps | Advanced export; structured `macros` or raw `macro_buffer` may be applied as full replacements (mutually exclusive); last byte must be zero; incomplete buffers fail decoding |
| `tap_holds`, `combos` | Targeted action records | Not bulk-exported; requested target entries are read during plan/apply |
| `raw` | Request hex → full reply hex | Diagnostic evidence, not configuration to apply |

Observed example, **not a prescribed configuration or guaranteed factory default**: orientation `90`, stage `2`, DPI stages `[450,800,1600,3200,4000]`, active DPI `1600`, polling rate `1000`, reported supported rates `[1000,500,125]`.

### Keymap objects

Each `layers` entry contains:

| Field | Shape |
|---|---|
| `layer` | Integer index `0..8` |
| `buttons` | Map of `03`, `04`, `01`, `02`, `M1`, `M2`, `Press` → `"0xNNNN"` keycodes |
| `dial` | Map of `ccw`, `cw` → `"0xNNNN"` keycodes |

The seven button names correspond to wire columns `0..6` in that order, row `0`. `Press` is the dial's push-button entry; rotations are read separately from encoder `0`, direction `0` = `ccw`, `1` = `cw`.

Keycodes are unsigned 16-bit firmware codes formatted as hex strings. They may encode mouse actions, keyboard actions, layers, or custom behaviors; the CLI does not accept symbolic binding inputs or validate which codes this firmware executes. The [action catalog](action-catalog.md) supplies named reference mappings to numeric codes. Do not treat an arbitrary 16-bit integer as a valid binding or assume a shortcut such as `ctrl+c` is accepted as input.

Example shape (one layer only, abbreviated; **not an importable config**):

```json
{
  "layer": 0,
  "buttons": {
    "03": "0x522A", "04": "0x0000", "01": "0x00D4", "02": "0x0000",
    "M1": "0x00D1", "M2": "0x00D2", "Press": "0x522B"
  },
  "dial": {"ccw": "0x00AA", "cw": "0x00A9"}
}
```

Exports are not atomic or complete backups and cannot be applied wholesale. `export --advanced` includes gesture/force-scroll and macro state; tap-holds and combos are read only for explicit targets. Per-layer orientation export is separate and currently fails on tested firmware.

## Other JSON outputs

### `devices --json`

An array of records, including when empty (`[]`):

| Fields | Meaning |
|---|---|
| `index` | Current collection index for selection |
| `vendor_id`, `product_id` | Integer USB IDs |
| `product_string`, `manufacturer_string` | Device-reported labels; may be empty/unavailable |
| `usage_page`, `usage` | Integer collection identifiers; may be unknown (`0`) with some backends |
| `interface_number` | USB interface number |
| `path` | Host/backend-specific path string |

### `receiver-info --json`

| Field | Meaning |
|---|---|
| `protocol_version` | Integer receiver protocol version; observed `2` |
| `feature_bytes` | Raw hex feature bytes; observed `"0b 00"`, not decoded |
| `firmware` | Receiver firmware/build string |
| `slots` | Three objects with `slot`, `vendor_id`, `product_id`, `status`, `connected` |
| `raw` | Named hex replies: `version`, `state`, `firmware` |

Slots use indices `0..2`; `connected` means status byte equals `1`. Empty slots typically have zero IDs/status. Do not confuse slots with Nape layers or DPI stages. The CLI does not expose receiver pairing/unpairing or target-slot selection.

## Known features not exposed by this CLI

These are protocol/source findings, **not guarantees that this firmware supports them**. Profile selection remains unimplemented because the deployed Launcher bundle contains command IDs but no profile operation or payload usage. Command IDs are in the [protocol reference](protocol-reference.md).

| Feature | Meaning |
|---|---|
| Mouse profiles | Profile selection; distinct from DPI stages and keymap layers. Launcher has no `GET/SET_PROFILE` operation |
| Battery-report configuration | Reporting behavior; not battery percentage itself |
| Factory reset / firmware / pairing | Not exposed; deliberately outside CLI scope |

The official trackball code also exposes custom DPI (`A7 36/37`), DPI gear count (`A7 3C/3D`), and sleep (`A7 0B/0C`) operations. The CLI implements these for advanced/targeted reads and guarded apply; sleep reads work on tested hardware, while custom-DPI and gear-count queries echo their requests and their setters remain unverified. Debounce, lift-off distance, motion sync, lighting, haptics, and other generic Keychron mouse settings have **not** been established as Nape Pro features here. Do not advertise them based on a different mouse's protocol. Firmware flashing, factory reset, and bootloader commands are also outside this CLI's scope.
