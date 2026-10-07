# CLI and settings reference

Scope: `nape-cli` **0.1.0**. All device operations are reads; `export` only writes a local file. Verified on Link-KM `3434:D026` firmware `0.1.3` and Nape firmware `v1.1.6-ZK`. Direct USB Nape access and Bluetooth are not implemented. Start with the [agent guide](agent-guide.md).

## Complete CLI command list

Prefix every command below with `uv run` from the repository. Global flags: `nape --help` (`-h`), `nape --version`. Every subcommand also supports `--help` (`-h`).

| Command | Purpose | Options / defaults |
|---|---|---|
| `nape devices` | List relevant Keychron HID collections | `--json`: JSON array; `--all`: all collections with VID `0x3434` |
| `nape receiver-info` | Read receiver protocol, firmware, paired slots | `--index N`: optional selection; `--timeout-ms 1500`; `--json`: include raw packets |
| `nape status` | Read Nape pointer settings and battery | `--index N`: optional selection; `--timeout-ms 1500`; `--json`: all fields and raw packets |
| `nape export OUTPUT` | Read settings and nine keymap layers into a new JSON file | Required file path; `--index N`; `--timeout-ms 1500`; no overwrite/force flag |
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
- Timeouts are positive milliseconds **per request**, not a total command duration. Status makes 13 requests; export makes 40.
- `probe` requires a mouse usage page `FFC1` or `FF0A`, rejects Link-KM `D026`, and is not the normal receiver workflow. Report IDs accept decimal or `0x` notation, range `0..255`. It prints raw bytes and can return success with no response.
- Normal success exits `0`; handled argument/device/file errors exit `2` and write an error to stderr. An empty discovery list is still success. Help/version exit `0`.

## Available settings and observations

Every field below is **read-only through this CLI**. `status --json` and `export` contain the same top-level fields, except that only export includes `layers`.

| JSON field | Meaning / domain | Notes |
|---|---|---|
| `schema_version` | Snapshot schema, currently integer `1` | Metadata, not a firmware setting |
| `transport` | `"link-km-raw-hid"` | Metadata |
| `firmware` | Nape firmware/build string | Not the receiver firmware |
| `layer_count` | Integer `9` on tested firmware | Current reader rejects other counts |
| `active_layer` | Layer index `0..8` | Normalized from firmware's `1..9`; no layer switching command |
| `orientation` | Global/default angle, degrees `0..315` in steps of `45` | Not a per-layer orientation map |
| `dpi_index` | Active DPI-stage index `0..4` | Different from a mouse profile or keymap layer |
| `dpi_values` | Five integer DPI values ordered by stage | Read as unsigned 16-bit LE values; valid write range/step not established |
| `dpi` | `dpi_values[dpi_index]` | Derived value |
| `battery_percent` | Integer `0..100` | Device status, not configurable |
| `charging` | Boolean | Device status |
| `polling_rate` | Current rate in Hz | Decode table: `8000,4000,2000,1000,500,250,125`; this does not imply support for every rate |
| `supported_polling_rates` | List of rates reported by the device | Use this list, not the full decode table, when proposing a rate |
| `layers` | Nine keymap objects; export only | Shape described below |
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

Keycodes are unsigned 16-bit firmware codes formatted as hex strings. They may encode mouse actions, keyboard actions, layers, or custom behaviors; the CLI does not translate names or validate which codes this firmware accepts. Do not treat an arbitrary 16-bit integer as a valid binding or assume a shortcut such as `ctrl+c` is accepted as input.

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

Exports are not atomic, not complete backups, and currently cannot be restored. They exclude the advanced features below.

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

These are protocol/source findings, **not guarantees that this firmware supports them**. No reads/exports/writes for them are implemented unless stated above. Command IDs are in the [protocol reference](protocol-reference.md).

| Feature | Meaning |
|---|---|
| DPI/angle/polling-rate setters | Writing the pointer settings currently readable through `status` |
| Button/encoder setters | Editing a layer's button bindings or dial rotations |
| Active-layer switching | Selecting a layer on the device |
| Per-layer orientation | Different trackball angle per layer |
| Mouse profiles | Profile selection; distinct from DPI stages and keymap layers; count/layout unverified |
| Tap-holds | Separate actions for tapping versus holding a button |
| Combos | Actions for simultaneous button combinations |
| Gestures | Trackball movement mapped to actions |
| Force gesture scroll | Gesture-based scroll mode |
| Battery-report configuration | Reporting behavior; not battery percentage itself |
| Macros | Stored action sequences; not included in keymap export even if a binding references one |

Sleep, debounce, lift-off distance, motion sync, lighting, haptics, and other generic Keychron mouse settings have **not** been established as Nape Pro features here. Do not advertise them based on a different mouse's protocol. Firmware flashing, factory reset, and bootloader commands are also outside this CLI's scope.
