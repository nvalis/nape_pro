# Pointer configuration

Use a separate, partial **JSON config** rather than editing an exported snapshot. Snapshots contain diagnostic/unsupported fields and are deliberately rejected as configs. YAML and keymap configuration are not implemented.

## Schema

`schema_version` must be integer `1`, plus at least one of:

| Field | Accepted input |
|---|---|
| `orientation` | Integer `0..315` in 45-degree steps |
| `dpi_index` | Integer stage index `0..4` |
| `dpi_values` | Exactly five integers, each `1..65535` |
| `polling_rate` | Integer from `8000,4000,2000,1000,500,250,125`; must also be reported supported by the connected device |

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

## Validate and plan

```sh
uv run nape validate examples/pointer-config.json
uv run nape validate examples/pointer-config.json --json
uv run nape plan examples/pointer-config.json
uv run nape plan examples/pointer-config.json --json
```

Validation is offline. Planning reads the current device and shows only changed values; it never writes settings. `plan` supports `--index N` and `--timeout-ms 1500`, like `status`. JSON plans contain `mode: "dry-run"` and `changes`, whose entries have `setting`, `before`, and `after`. DPI changes identify individual stages as `dpi_values[0]` etc.

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

- Active DPI-stage selection and restoration are hardware-tested; DPI-value, orientation, and polling-rate writes are simulated-device tested only. Setter layouts come from NapeBar. See the [hardware log](hardware-tests.md).
- Write mode accepts only the observed firmware token **`v1.1.6-ZK`**, with **only `3434:4004` connected in receiver slot 0**. Other firmware/slot combinations are refused, with no override flag.
- Before a setter, apply reads the supported full snapshot (including nine keymap layers), shows the diff, then saves and flushes/fsyncs the snapshot file. Backup failure prevents all setters.
- Only changed settings are sent: individual DPI values first, then DPI stage, orientation, polling rate. Keymap and advanced settings have no write path.
- One receiver handle is used for the read/write/read-back sequence. Setters have no reliable ACK here; successful USB transmission alone is not acceptance.
- After writes, apply checks **all four pointer fields**, including omitted fields, and verifies the exported keymap is unchanged. Firmware quantization/rejection is a verification error, not success.
- Read-back checks immediate state, **not persistence across reboot**. Advanced/unexported settings cannot be verified.
- Apply is not atomic and offers **no automatic rollback**. A write error, timeout, mismatch, or interrupt after setters start may leave partial changes; the error identifies the snapshot and attempt count. Do not blindly retry.
- No device-wide locking or atomic snapshot is available. Keep the Nape awake/stationary, close other configurators, and do not run concurrent CLI/configuration commands.

### Recovery after a partial failure

Inspect `nape status --json` first. Preserve the saved snapshot and error output. There is no full snapshot restore command. To propose restoring just pointer settings, create a new config with `schema_version: 1` and the snapshot's `orientation`, `dpi_index`, `dpi_values`, and `polling_rate`; validate and plan it, then obtain explicit approval before another `--write` using a **different** backup path. Do not submit the whole snapshot as config or claim it restores macros/advanced behaviors.

If a requested setter remains unverified or the target fails the guards, consider Keychron Launcher rather than sending ad-hoc packets.
