# Configuration

Use a separate, partial **JSON config**, not an edited export. Snapshots contain diagnostic fields and are rejected as configs. YAML, symbolic binding inputs and profile selection are unsupported. Translate natural-language requests with the [named keycode/action catalog](action-catalog.md), then use numeric keycodes in JSON.

See the [current hardware matrix](hardware-tests.md) for storage/read-back coverage. Physical action execution and reboot persistence remain unverified. Custom-DPI and stage-count getters echo requests, yielding `null`; targeted writes are refused. Per-layer orientation is blocked because its getter echoes the layer rather than an angle. Macro replacement resets the entire store and is not atomic. Source evidence is in [Launcher verification](launcher-verification.md).

## Schema

`schema_version` must be integer `1`, plus at least one of:

| Field | Accepted input |
|---|---|
| `orientation` | Integer `0..315` in 45-degree steps; the tested firmware's reported angle changes with active layer |
| `active_layer` | Integer layer index `0..8`; switch/restore hardware-tested |
| `dpi_index` | Integer stage index `0..4` |
| `dpi_values` | Exactly five integers, each `1..65535` (stored slots, including disabled cycling stages) |
| `custom_dpi` | Integer `1..65535`, the separate Launcher custom-DPI value. Config targets are refused if the getter is unavailable |
| `dpi_stage_count` | Integer `1..5`, number of enabled DPI cycling stages. Config targets are refused if the getter is unavailable |
| `sleep` | Non-empty partial map of `backlight`, `sleep`, `magnet_scan` to raw integers `0..65535`; units/zero semantics unverified |
| `polling_rate` | Integer from `8000,4000,2000,1000,500,250,125`; must also be reported supported by the connected device |
| `layers` | Non-empty list of partial keymap/per-layer orientation objects, described below |
| `tap_holds` | Non-empty list of targeted layer/button tap-vs-hold actions or deletions |
| `combos` | Non-empty list of targeted combo slots to set/delete; `columns` is the Launcher wire byte |
| `gesture` | Partial map of `up`, `down`, `left`, `right` to 16-bit keycodes |
| `force_gesture_scroll` | Partial raw-byte map with `gesture` and/or `scroll` fields |
| `macros` | Complete macro slot list using Launcher-style typed steps; count and capacity checked online |
| `macro_buffer` | Hex string containing the complete device macro buffer; requires an advanced snapshot and must match its byte size exactly; mutually exclusive with `macros` |

Unspecified settings are preserved. Unknown/duplicate fields, nulls, booleans, strings, and floats in place of integers are rejected. DPI limits are wire-encoding limits, **not verified sensor limits**; firmware may reject or quantize values. Use known-good values; storage tests cover stage 0 at 450 and 800 DPI, not the full sensor range. Offline validation cannot check the connected device's supported polling rates.

Example partial config:

```json
{
  "schema_version": 1,
  "orientation": 90,
  "dpi_index": 2
}
```

[`examples/pointer-config.json`](../examples/pointer-config.json) includes all four settings using values previously read from our device. It is an example, not a recommended preference or guaranteed factory default.

## Custom DPI, stage count, and sleep

These fields are read by `status --advanced` / `export --advanced`, or when explicitly targeted by a config. Ordinary status/export avoid these optional getters. On the tested firmware, custom-DPI and stage-count queries echo their zero-padded requests; snapshots retain those raw replies and report the values as `null`. A config targeting either unavailable value is refused before planning/writing. Sleep is still read and can be planned independently; there is no fallback to guessed defaults.

```json
{
  "schema_version": 1,
  "custom_dpi": 1200,
  "dpi_stage_count": 3,
  "dpi_index": 1,
  "sleep": {"sleep": 30}
}
```

See [`examples/device-settings-config.json`](../examples/device-settings-config.json). These are illustrative wire values, not recommended preferences or factory defaults. Sleep values retain the Launcher's raw unsigned 16-bit fields; do not assume seconds/minutes or that zero disables a timer. Omitted sleep fields are read, preserved, and verified. As in Launcher, a sleep reply with both backlight/sleep values zero is considered unusable; configs that would produce that state are refused before writing. Custom DPI is a separate value, not automatic selection of a DPI stage or assignment of its button action.

Five stored DPI values remain in the config/export regardless of cycling count. When reducing the count, explicitly select an index below the new count if the current index would be disabled. Apply selects the valid stage before shrinking; when growing, it enables stages before selecting a newly enabled one. It re-queries the current selection before a count setter and checks the count immediately afterward, so rejected intermediate writes stop the sequence rather than disabling/selecting invalid stages. Read-back compares all three device-setting fields, including those not changed by the config; unavailable custom-DPI or count values are not treated as valid state and targeting them is refused.

## Partial keymaps

A config may include pointer settings, layer bindings, or advanced settings in any combination. Example:

```json
{
  "schema_version": 1,
  "layers": [
    {
      "layer": 0,
      "buttons": {"M1": "0x0068", "M2": "0x0069"},
      "dial": {"ccw": "0x006A", "cw": "0x006B"},
      "orientation": 90
    }
  ]
}
```

- `layer`: integer `0..8`; each layer index may occur only once. This edits bindings/orientation, **not** the active layer selection.
- `buttons`: optional non-empty map of names `03`, `04`, `01`, `02`, `M1`, `M2`, `Press` to keycodes. `Press` is the dial push button.
- `dial`: optional non-empty map of `ccw`/`cw` to keycodes. Do not put `press` here.
- `orientation`: optional integer `0..315` in 45-degree steps. This is the layer-specific angle, not the global/default orientation. The tested firmware currently returns an invalid echo for `GET_LAYER_ORI`, so plan/apply stop before writing it.
- Each layer must contain at least one of these fields. Unspecified layers/bindings are preserved; unknown names and nested fields are rejected.
- Keycodes must be strings with **exactly four hex digits**, such as `"0x0068"`. Lowercase digits and `0X` prefixes are accepted and normalized to `0xNNNN`. Integers, `KC_F13`, and `ctrl+c` strings are not accepted.
- Encoding validation is not semantic validation: choose firmware-specific action codes from the [protocol-12 catalog](action-catalog.md) or a confirmed existing binding. Do not invent arbitrary keycodes or map destructive firmware actions without understanding them. Read-back confirms storage, not what a physical press does.

## Other advanced settings (Launcher-derived)

```json
{
  "schema_version": 1,
  "active_layer": 2,
  "tap_holds": [
    {"layer": 0, "button": "M1", "tap": "0x0004", "held": "0x00E1", "create": true},
    {"layer": 0, "button": "M2", "delete": true}
  ],
  "combos": [
    {"index": 0, "layer": 0, "columns": 3, "tap": "0x0004", "held": "0x00E1", "timeout_ms": 200, "create": true}
  ],
  "gesture": {"up": "0x00E9", "down": "0x00E7"},
  "force_gesture_scroll": {"gesture": 1, "scroll": 0}
}
```

- `active_layer` is the unchanged Launcher wire index `0..8`, used consistently for reads and writes. It is not the Launcher UI's potentially shifted display label; resolve the user's intended layer explicitly using the [catalog's layer guidance](action-catalog.md#physical-controls-and-layers). On tested firmware, `A7 2D` changes the layer but sends no matching ACK, so apply verifies it through `A3` read-back. The `A7 20` angle readout changed from `90°` on layer 1 to `0°` on layer 2 and back on restoration. Apply therefore does not compare orientation when an active-layer-only change is requested; a config that changes layer and sets orientation together is rejected, so apply them separately.
- Tap-holds target one row-0 button per layer. `tap` and `held` are four-digit hex keycodes; use `delete: true` to remove an entry. The Launcher protocol encodes both keycodes little-endian. `create: true` requires a positively returned empty record. Read timeouts always abort. Creation and deletion storage tests passed; deletion on tested firmware sends no matching ACK, so apply relies on targeted read-back. These operations edit the tap-hold record only; they do not automatically assign the Launcher's `CUSTOM(41)` tap-hold button binding (`0x7E29` on protocol 12). Assign that binding separately on the same layer/button; storage verification alone does not prove activation. See the [tap-hold recipe](action-catalog.md#single-button-tap-versus-hold).
- Combo `index` is a byte. `columns` is the opaque byte passed through by Launcher (the CLI does not invent bit assignments). Set entries require layer, columns, tap, and held; timeout defaults to 200 ms. The source exposes no slot-count query. Use only a confirmed index; add `"create": true` only when you have independently confirmed that slot is empty. A positively returned empty record is required for creation/deletion; a read timeout always aborts planning, even with `create: true`. Some firmware returns no record for an empty slot; creation through the CLI is unavailable in that case.
- Gesture directions are 16-bit keycodes, little-endian on wire. Unspecified directions are read and preserved before a full gesture setter is sent.
- `force_gesture_scroll` values are raw bytes copied to/from Launcher fields; their semantics are not decoded.

Tap-hold/combo planning reads only the target entries. The pre-write backup includes those entries, not a complete dump of every advanced slot. A timeout or unexpected response always stops planning/writing; it is never evidence of absence. These setters use the explicit `--write --backup` guard and immediate read-back. Tap-hold create/delete and existing-combo updates passed hardware storage tests; combo deletion and empty-slot creation remain untested.

## Macros

Structured macros follow the Launcher v11+ encoding (`macros` must contain exactly the device-reported slot count). The example below illustrates two slots; [`examples/macro-config.json`](../examples/macro-config.json) contains 16 slots, as reported by the tested target. Both replace all slots rather than preserving omitted macros; check your device's reported count and retain existing steps when preparing a replacement:

```json
{
  "schema_version": 1,
  "macros": [
    [
      {"type": "tap", "keycode": "0x0004"},
      {"type": "delay", "ms": 150},
      {"type": "text", "text": "hello"}
    ],
    []
  ]
}
```

Steps support `tap`, `down`, `up`, `delay`, and `text`. Macro keycodes are single-byte QMK keycodes written as four-digit hex values `0x0000..0x00FF`; text is Latin-1 (`0..255`) excluding reserved opcodes, and delay encoding requires protocol version 11 or newer. Planning rejects text bytes `00/01` for v11+ and `00..04` for legacy protocols. Macro exports reject truncated actions or missing slot terminators instead of fabricating slots. Planning compiles the entire slot list to a full-capacity buffer and shows its byte count/SHA-256. `macros` and `macro_buffer` are mutually exclusive.

Alternatively, `macro_buffer` replaces the **entire** VIA macro storage area with raw bytes. Use an advanced snapshot as a base and preserve exact length. The final byte must be `00`, reserved for Launcher finalization; all reported slots must decode successfully. Structured macros also reserve this final zero byte.

With `--write --backup NEW_FILE`, changed macro data is applied as a complete transaction:

1. Read and fsync a backup containing the old full macro buffer and metadata, plus all keymaps/core settings.
2. Send VIA macro reset (`10`) and wait for its ACK.
3. Write `FF` to the last byte as an invalidation marker.
4. Transfer all other buffer bytes in chunks of at most 28, keeping the marker intact.
5. Write `00` to the last byte to finalize, then read back and compare the entire buffer.

Every buffer-write packet must be echoed exactly, including marker packets. Unlike Launcher, the CLI **does not retry** mismatched ACKs or timeouts. Complete structured-text replacement and exact raw-buffer restoration passed hardware tests, including reset and every chunk/marker ACK; intermittent timeouts still occurred, so this is not a reliability guarantee. A failure after reset can leave macros empty or invalid; the CLI retains the backup/error and never automatically finalizes or rolls back a partial transfer. No standalone macro-reset command is exposed. A macro no-op sends no reset and creates no backup. Runtime execution and persistence still require separately approved hardware tests.

[`examples/keymap-config.json`](../examples/keymap-config.json) contains the keymap example. Review the plan before any write. See the [hardware matrix](hardware-tests.md) for tested storage operations and remaining gaps; physical actions and reboot persistence were not tested.

## Validate and plan

```sh
uv run nape validate examples/pointer-config.json
uv run nape validate examples/pointer-config.json --json
uv run nape plan examples/pointer-config.json
uv run nape plan examples/pointer-config.json --json
```

Validation is offline. Planning reads the current device and shows only changed values; it never writes settings. `plan` supports `--index N` and `--timeout-ms 1500`, like `status`. JSON plans contain `mode: "dry-run"` and `changes`, whose entries have `setting`, `before`, and `after`. DPI changes identify individual stages as `dpi_values[0]` etc. Keymap diffs use paths such as `layers[0].buttons.M1` and hex `before`/`after` strings. Plans containing layers read the full keymap; pointer-only plans do not.

## Experimental apply

```sh
# Both commands only read/preview; neither saves a backup or changes settings:
uv run nape apply examples/pointer-config.json
uv run nape apply examples/pointer-config.json --dry-run --json

# Only after reviewing the diff and explicitly approving the configuration:
uv run nape apply my-config.json --write --backup nape-before-write.json
```

`--write` is explicit authorization, not a prompt. `--write` and `--dry-run` are mutually exclusive. `--backup` is mandatory with `--write` and rejected without it. The path must be new, its parent directory must exist, and no existing snapshot is overwritten. A write-mode no-op sends no setters and creates no backup.

Apply supports `--index`, `--timeout-ms` (per read request), and `--json`. JSON stdout contains `mode` (`dry-run`, `no-op`, or `applied`) and `changes`; write results also contain `backup`, and successful changed writes contain `verified: true`. The visible pre-write diff goes to stderr with `--json`, otherwise stdout.

### Guardrails and limitations

- Storage/read-back hardware tests passed for DPI selection/values, orientation/layer, polling, button/dial, tap-hold create/delete, existing-combo update, sleep, gestures/force-scroll, and full macro replacement. Custom DPI, stage count, and per-layer orientation remain unavailable on tested firmware; combo deletion and empty-slot creation remain untested. The per-layer read currently fails on tested firmware, so its guarded apply path stops before sending a setter. See the [hardware matrix](hardware-tests.md).
- Write mode accepts only the observed firmware token **`v1.1.6-ZK`**, with **only `3434:4004` connected in receiver slot 0**. Other firmware/slot combinations are refused, with no override flag.
- Before a setter, apply reads the supported full snapshot (including nine keymap layers), shows the diff, then saves and flushes/fsyncs the snapshot file. Backup failure prevents all setters.
- Only changed settings are sent: pointer fields, active layer, requested layer bindings/orientations, targeted tap-holds/combos, full gesture/force-scroll values, custom DPI, stage count, merged sleep fields, and complete macro replacements. Profiles have no write path because the current Launcher bundle exposes no profile operation.
- One receiver handle is used for the read/write/read-back sequence. DPI/polling/stage-count/active-layer setters and tap-hold deletion are fire-and-forget; stage count, active layer, and deleted records are verified by explicit reads. Global orientation, dynamic-keymap, and other advanced setters wait for their observed ACK shapes. Encoder ACKs also match direction. Neither USB transmission nor an ACK proves acceptance.
- After writes, apply checks **all four pointer fields and the complete expected keymap**, including preserved entries and the secondary polling-rate index. An active-layer-only change is an exception: the tested firmware's `A7 20` orientation readout changes with the layer, so apply verifies the requested layer and does not compare the old layer's angle. Combining a layer switch with an orientation target is refused. A primary polling write copies the device's current secondary index rather than implicitly setting it to zero. Apply also checks targeted advanced records, gesture/force-scroll values, all requested device-setting state (including preserved fields), and the complete macro buffer. Firmware rejection is a verification error, not success.
- Read-back checks immediate state, **not persistence across reboot**. Profile settings remain unimplemented; the per-layer orientation reader fails safely on tested firmware.
- Apply is not atomic and offers **no automatic rollback**. A write error, timeout, mismatch, or interrupt after setters start may leave partial changes; the error identifies the snapshot and attempt count. Do not blindly retry.
- No device-wide locking or atomic snapshot is available. Keep the Nape awake/stationary, close other configurators, and do not run concurrent CLI/configuration commands.

### Recovery after a partial failure

Inspect `nape status --json` and export the current keymap first. Preserve the saved pre-write snapshot and error output. There is no full snapshot restore command. To propose recovery, create a new partial config with `schema_version: 1` and the affected pointer fields, layer bindings, or advanced target entries from that snapshot. For interrupted macro updates, preserve the backup/error and inspect the device before any further write; a macro export may fail decoding the incomplete store. Use the official Launcher for recovery if the CLI cannot read a valid pre-write buffer. Never bypass the guards or blindly finalize a partial transfer. Validate and plan it, then obtain explicit approval before another `--write` using a **different** backup path. Do not submit the whole snapshot as config, overwrite unaffected settings unnecessarily, or claim it restores unexported tap-holds/combos/gestures/profiles.

If a requested setter remains unverified or the target fails the guards, consider Keychron Launcher rather than sending ad-hoc packets.
