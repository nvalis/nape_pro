# Pointer and keymap configuration

Use a separate, partial **JSON config** rather than editing an exported snapshot. Snapshots contain diagnostic fields and are deliberately rejected as configs. YAML, symbolic keycode names, tap-holds, combos, gestures, profiles, and active-layer switching are not implemented. Per-layer orientation and raw VIA macro-buffer replacement are experimental.

## Schema

`schema_version` must be integer `1`, plus at least one of:

| Field | Accepted input |
|---|---|
| `orientation` | Integer `0..315` in 45-degree steps |
| `dpi_index` | Integer stage index `0..4` |
| `dpi_values` | Exactly five integers, each `1..65535` |
| `polling_rate` | Integer from `8000,4000,2000,1000,500,250,125`; must also be reported supported by the connected device |
| `layers` | Non-empty list of partial keymap/per-layer orientation objects, described below |
| `macro_buffer` | Hex string containing the complete device macro buffer; requires an advanced snapshot and must match its byte size exactly |

Unspecified settings are preserved. Unknown/duplicate fields, nulls, booleans, strings, and floats in place of integers are rejected. DPI limits are wire-encoding limits, **not verified sensor limits**; firmware may reject or quantize values. Use known-good values until DPI-value write behavior is verified. Offline validation cannot check the connected device's supported polling rates.

Example partial config:

```json
{
  "schema_version": 1,
  "orientation": 90,
  "dpi_index": 2
}
```

[`examples/pointer-config.json`](../examples/pointer-config.json) includes all four settings using values previously read from our device. It is an example, not a recommended preference or guaranteed factory default.

## Partial keymaps

A config may include pointer settings, layer bindings, or both. Example:

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
- `orientation`: optional integer `0..315` in 45-degree steps. This is the layer-specific angle, not the global/default orientation.
- Each layer must contain at least one of these fields. Unspecified layers/bindings are preserved; unknown names and nested fields are rejected.
- Keycodes must be strings with **exactly four hex digits**, such as `"0x0068"`. Lowercase digits and `0X` prefixes are accepted and normalized to `0xNNNN`. Integers, `KC_F13`, and `ctrl+c` strings are not accepted.
- Encoding validation is not semantic validation: firmware-specific action codes must be chosen from a verified catalog or existing binding. Do not invent arbitrary keycodes or map destructive firmware actions without understanding them. Read-back confirms storage, not what a physical press does.

`macro_buffer` replaces the **entire** VIA macro storage area with raw bytes; it is not a parsed list of human-readable macros. First create an advanced snapshot with `nape export FILE --advanced`, use its `macro_buffer` value as a base, and preserve the exact buffer length. Planning shows the byte count and SHA-256 before/after. This setter uses standard VIA buffer commands but is not hardware-tested; do not use it without a verified backup and explicit approval.

[`examples/keymap-config.json`](../examples/keymap-config.json) contains the keymap example. It intentionally proposes changed bindings; review the plan before any write. Button/dial, per-layer orientation, and macro-buffer setters have not yet been hardware-tested.

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

- Active DPI-stage selection and restoration are hardware-tested; DPI-value, orientation, polling-rate, button, and dial writes are simulated-device tested only. Setter layouts come from NapeBar. See the [hardware log](hardware-tests.md).
- Write mode accepts only the observed firmware token **`v1.1.6-ZK`**, with **only `3434:4004` connected in receiver slot 0**. Other firmware/slot combinations are refused, with no override flag.
- Before a setter, apply reads the supported full snapshot (including nine keymap layers), shows the diff, then saves and flushes/fsyncs the snapshot file. Backup failure prevents all setters.
- Only changed settings are sent: individual DPI values first, then DPI stage, global orientation, polling rate, requested layer bindings/orientations, and macro-buffer chunks. Tap-holds, combos, gestures, profiles, and active-layer selection have no write path.
- One receiver handle is used for the read/write/read-back sequence. Pointer setters are fire-and-forget; button/dial setters wait for a serialized command ACK before proceeding. Neither USB transmission nor an ACK proves acceptance.
- After writes, apply checks **all four pointer fields and the complete expected keymap**, including preserved entries. When requested, it also verifies every layer orientation or the entire macro buffer. Firmware quantization/rejection is a verification error, not success.
- Read-back checks immediate state, **not persistence across reboot**. Tap-holds, combos, gestures, profiles, active-layer selection, and other unexported settings cannot be verified.
- Apply is not atomic and offers **no automatic rollback**. A write error, timeout, mismatch, or interrupt after setters start may leave partial changes; the error identifies the snapshot and attempt count. Do not blindly retry.
- No device-wide locking or atomic snapshot is available. Keep the Nape awake/stationary, close other configurators, and do not run concurrent CLI/configuration commands.

### Recovery after a partial failure

Inspect `nape status --json` and export the current keymap first. Preserve the saved pre-write snapshot and error output. There is no full snapshot restore command. To propose recovery, create a new partial config with `schema_version: 1` and the affected pointer fields, layer bindings/orientations, or macro buffer from that snapshot. Validate and plan it, then obtain explicit approval before another `--write` using a **different** backup path. Do not submit the whole snapshot as config, overwrite unaffected settings unnecessarily, or claim it restores unexported tap-holds/combos/gestures/profiles.

If a requested setter remains unverified or the target fails the guards, consider Keychron Launcher rather than sending ad-hoc packets.
