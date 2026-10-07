# Configuration

Use a separate partial JSON config, not an edited export.
Only Nape firmware `v1.3.0-ZK` is supported; other versions are rejected before configuration queries.
YAML, symbolic binding inputs, and profile selection are unsupported.
Use the [action catalog](action-catalog.md) to translate intent into numeric keycodes.
The [hardware matrix](hardware-tests.md) records passing read-only checks; configuration setters and reboot persistence still need hardware verification.

## Schema

`schema_version` must be integer 1, plus at least one setting:

| Field | Accepted input |
|---|---|
| `orientation` | `0..315` in 45-degree steps, for the effective layer |
| `active_layer` | Default-layer target `0..8`; existing config field name retained |
| `dpi_index` | Stage `0..4`, below the resulting enabled-stage count |
| `dpi_values` | Exactly five integers in `1..65535`, including disabled stored stages |
| `custom_dpi` | Integer `400..4000` |
| `scroll_dpi` | Integer `40..4000`; physical scroll-mode effect unverified |
| `dpi_stage_count` | Integer `1..5` |
| `sleep` | Nonempty partial map of `backlight`, `sleep`, `magnet_scan` to raw integers `0..65535` |
| `polling_rate` | One of `8000,4000,2000,1000,500,250,125`, also advertised by the connected device |
| `layers` | Nonempty list of partial keymap/orientation objects |
| `tap_holds` | Nonempty list of layer/button tap-hold records or deletions |
| `combos` | Nonempty list of indexed combo records or deletions |
| `gesture` | Partial map of `up`, `down`, `left`, `right` to four-digit hex keycodes |
| `force_gesture_scroll` | Partial map of `gesture` and/or `scroll` to integers `0..15` |
| `macros` | Complete slot list of typed steps; count and capacity checked online |
| `macro_buffer` | Hex string containing the complete raw macro buffer; mutually exclusive with `macros` |

Unspecified settings are preserved.
Unknown or duplicate fields, nulls, booleans, floats, and strings in place of integers are rejected.
Snapshots contain diagnostic fields and are not valid configs.
The firmware clamps custom/scroll DPI, so the CLI rejects out-of-range targets rather than silently applying different values.
Stage-DPI LE16 limits are encoding limits, not verified sensor limits.
Offline validation cannot check supported polling rates or current record occupancy.

```json
{
  "schema_version": 1,
  "orientation": 90,
  "dpi_index": 2
}
```

See [`examples/firmware-130-config.json`](../examples/firmware-130-config.json) for device settings and [`examples/nape-two-layer-config.json`](../examples/nape-two-layer-config.json) for a two-layer layout.
Examples are not recommended preferences or guaranteed factory defaults.

## DPI and sleep

Advanced reads include custom DPI, scroll-mode DPI, stage count, and sleep.
Targeted configs also read these fields; selecting a stage reads its enabled count before planning.
There are five stored stages even when fewer participate in cycling.

```json
{
  "schema_version": 1,
  "custom_dpi": 1200,
  "scroll_dpi": 80,
  "dpi_stage_count": 3,
  "dpi_index": 1,
  "sleep": {"sleep": 30}
}
```

See [`examples/firmware-130-config.json`](../examples/firmware-130-config.json).
Custom DPI does not automatically select a stage or assign a button action.
The scroll-mode DPI getter substitutes 400 when its underlying field is invalid, so a valid getter alone cannot establish stored validity.
Its physical effect is unverified.
Sleep fields remain raw unsigned 16-bit values; do not assume units or what zero does.
Zero timers are accepted, and omitted sleep fields are preserved.

When shrinking stage count, explicitly select an index below the new count if the existing selection would be disabled.
Apply selects the valid stage before shrinking; it enables stages before selecting a newly enabled one.
It checks current selection before a count setter and count state immediately afterward.
Rejected intermediate changes stop the sequence rather than selecting or disabling invalid stages.

## Keymaps and orientation

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

A layer object requires integer `layer` in `0..8` and at least one of `buttons`, `dial`, or `orientation`.
Each layer index can occur once.
Buttons accept `03`, `04`, `01`, `02`, `M1`, `M2`, and `Press`; `Press` is the dial push button.
Dial accepts only `ccw` and `cw`.
Bindings must be strings with exactly four hex digits, such as `0x0068`; prefixes and digits normalize to `0xNNNN`.
Integers, `KC_F13`, and shortcut strings such as `ctrl+c` are not accepted.
A valid encoding does not prove the firmware executes that action.

Per-layer angles are `0..315` in 45-degree steps.
Changing the effective layer's angle also changes the global orientation readout.
Conflicting global and effective-layer angle targets are rejected; matching targets produce one setter.
The firmware does not bounds-check per-layer orientation access, so the CLI restricts it to nine user layers.
Unspecified layers and bindings are preserved.

`active_layer` config values set the default layer through `A7 2D`.
Snapshots distinguish default layer `A7 35` from effective layer `A3`, which can differ during a held layer action.
A target equal to the existing default layer is a no-op, even if a temporary layer is active.
`default_layer` itself is read-only output, not a second config field.
Use the [catalog's layer guidance](action-catalog.md#physical-controls-and-layers) rather than shifted Launcher labels.
Switch layers and set global orientation in separate applies.
Layer selection verifies the new effective angle against the saved user-layer angles.

## Action records

```json
{
  "schema_version": 1,
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

Tap-holds target one row-0 button per layer and have a 30-record capacity across 63 accessible targets.
Tap/held actions are four-digit hex keycodes.
Use `create: true` for a new record; updates require an existing record.
Creation of an already identical record is a no-op, so the retained layout example can be reapplied without overwriting a different binding.
Use `delete: true` to remove a record, without tap/held fields.
Tap-hold deletions run before creations to free capacity.
These records do not automatically assign the activation binding `0x7E29`; see the [tap-hold recipe](action-catalog.md#single-button-tap-versus-hold).

Combos use indices `0..29`; bulk deletion is not exposed.
`columns` is the opaque Launcher wire byte, not a bit layout invented by the CLI.
Set entries require layer, columns, tap, and held; timeout defaults to 200 ms.
Combo deletion compacts the table.
Config indices refer to the original snapshot: updates run first, deletions run in descending order, and final verification checks the shifted table.
Deleting an already absent target is a no-op.

Record configs automatically read all 30 combo indices and 63 tap-hold targets.
The firmware returns unchanged requests for absent tap-holds and out-of-count combos.
Only an actual reply establishes absence; a timeout always aborts.
Gesture updates preserve unspecified directions before sending all four values.
Force gesture/scroll fields occupy nibbles, so values above 15 are rejected rather than truncated.
Their physical semantics remain unverified.

## Macros

`macros` replaces every reported slot, not just listed nonempty slots.
It must contain exactly the device-reported count.
This snippet illustrates two slots, but the connected target reports 16.
A real config must include all reported slots and preserve existing steps where intended.

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

Steps are `tap`, `down`, `up`, `delay`, and `text`.
Macro keycodes are single-byte QMK values written as `0x0000..0x00FF`.
Text is Latin-1 excluding protocol-reserved opcodes.
Planning compiles the complete slot list into a full-capacity buffer and shows its byte count and SHA-256.
Exports reject truncated actions or missing slot terminators rather than inventing empty slots.

Alternatively, `macro_buffer` replaces the complete store with raw hex bytes.
Its size must match the reported capacity and every slot must decode.
The final byte must be zero, reserved for finalization.
Do not combine `macros` and `macro_buffer`.

Changed macro data uses this transaction after saving a complete configuration backup:

1. Reset the macro store with `10` and wait for its ACK.
2. Write `FF` to the last byte as an invalidation marker.
3. Transfer all other bytes in chunks of at most 28.
4. Write `00` to the last byte to finalize.
5. Read and compare the complete buffer.

Every chunk and marker requires an exact echoed-packet ACK.
Timeouts and mismatches stop without retry, automatic finalization, or rollback.
A failure after reset can leave macros empty or invalid.
There is no standalone macro-reset command.
A macro no-op sends no reset and creates no backup.
Hardware transaction behavior, execution, and persistence remain unverified.

## Validate, plan, and apply

```sh
uv run nape validate examples/firmware-130-config.json
uv run nape validate examples/firmware-130-config.json --json
uv run nape plan examples/firmware-130-config.json
uv run nape apply examples/firmware-130-config.json --dry-run --json
# Only after reviewing and approving the diff:
uv run nape apply my-config.json --write --backup nape-before-write.json
```

Validation is offline.
Plan and default apply only read and preview; neither writes settings nor creates a backup.
Plans read complete keymaps when targeting layers and complete records when targeting action records.
Write mode reads all supported configuration families even for a pointer-only change.
`--write` is explicit authorization, not a prompt, and is mutually exclusive with `--dry-run`.
`--backup` is mandatory only with write; its path must be new and its parent must exist.
A write-mode no-op sends no setters and creates no backup.

Plan/apply accept `--index`, positive per-request `--timeout-ms`, and `--json`.
JSON results include `mode` and `changes`; changed write success adds `backup` and `verified: true`.
Diff paths identify individual DPI stages, layer bindings, and advanced records.
With JSON output, the visible pre-write diff goes to stderr.

## Write guards and recovery

Both supported transports require the exact `v1.3.0-ZK` token.
Receiver writes additionally require only Nape `3434:4004` connected in slot 0; USB skips receiver-state queries.
No override flag exists.

Before any setter, apply reads all supported settings, displays the diff, and fsyncs a new backup.
The backup includes nine keymaps and angles, all accessible records, device settings, gestures, force-scroll, and macro bytes.
Read or backup failure prevents setters.
Only requested changed settings are written.
Apply holds one channel open throughout, waits for setter ACKs, and verifies preserved state after writing.
Polling uses send/read-back verification rather than a required status ACK.
Primary polling writes copy the existing secondary index.

Read-back verifies reported immediate state, not reboot persistence.
Several firmware handlers ignore settings-backend failures, so zero status does not prove saving succeeded.
Writes are not atomic; failures can leave partial changes.
There is no automatic retry, rollback, device-wide lock, or whole-snapshot restore.
Keep the Nape awake and stationary, close other configurators, and do not run concurrent commands.

After a partial failure, retain the backup and error and inspect current state before proposing recovery.
Create a new partial config for the affected settings, validate and plan it, then obtain explicit approval before another write with a different backup path.
Do not apply the whole snapshot, blindly finalize a partial macro transfer, or overwrite unrelated settings.
If an interrupted macro store cannot be decoded, use Launcher for recovery rather than bypassing CLI guards.
See the [1.3.0 guide](firmware-1.3.0.md) and [hardware matrix](hardware-tests.md) for evidence and remaining tests.
