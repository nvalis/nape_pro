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

Unspecified settings are preserved. Unknown/duplicate fields, nulls, booleans, strings, and floats in place of integers are rejected. DPI limits are wire-encoding limits, **not verified sensor limits**; firmware may reject or quantize values. Use known-good values until write behavior is verified. Offline validation cannot check the connected device's supported polling rates.

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

Settings application is not implemented yet. Keep the device awake in 2.4 GHz mode through the Link-KM receiver; do not run concurrent configuration commands.
