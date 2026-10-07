# Firmware 1.3.0

The CLI recognizes the exact firmware token `v1.3.0-ZK`, including its optional build timestamp.
This is the only supported Nape firmware; reads and writes refuse every other version.
The implementation uses the [published-image disassembly](../research/nape-1.3.0.md), packet tests, and the read observations in the [hardware matrix](hardware-tests.md).
Binary evidence is not proof of physical behavior or reboot persistence.

## Read configuration

Keep the Nape awake, close Launcher, and run commands serially.
These commands send only getter requests:

```sh
uv run nape status --advanced --layer-orientations --records
uv run nape export nape-130.json --advanced --layer-orientations --records
```

Standard status includes `default_layer` from `A7 35`, separately from the effective `active_layer` reported by `A3`.
Held layer actions can make these differ.
The `active_layer` config field retains its existing name, but `A7 2D` changes the default layer on 1.3.0.
A target equal to the existing default layer is a no-op, even while a temporary layer is active.
`default_layer` is diagnostic output, not an additional config input.

`--advanced` adds `scroll_dpi`, custom DPI, cycling-stage count, sleep, gestures, force-scroll, and macros.
`--layer-orientations` reads all nine user layers.
`--records` scans 30 combo indices and all 63 row-0 layer/button tap-hold targets.
Snapshots include every queried target, with `null` for absent records, plus raw replies and capability metadata.
They are configuration evidence, not flash dumps or directly importable configs.

## Limits

| Config setting | 1.3.0 contract |
|---|---|
| `custom_dpi` | `400..4000`, LE16 via `A7 36/37` |
| `scroll_dpi` | `40..4000`, LE16 via `A7 3A/3B`; physical scroll-mode effect unverified |
| `dpi_values` | Exactly five LE16 stored values; setter itself does not clamp stage DPI |
| `dpi_index` | `0..4`, and below the enabled stage count |
| `dpi_stage_count` | `1..5`, despite release notes suggesting additional DPI settings |
| Layer orientations | `0..315` in 45-degree steps, user layers `0..8` |
| Combo index | `0..29`; no bulk-delete sentinel |
| Tap-holds | At most 30 records across the 63 accessible layer/button targets |
| Force gesture/scroll | Each value `0..15`, packed into one byte |

The firmware clamps custom and scroll-mode DPI.
The CLI rejects out-of-range targets instead of quietly applying a different value.
The `A7 3A` getter substitutes 400 when its stored field is outside `40..4000`, so a valid getter does not prove the underlying stored field is valid.
The firmware's layer-orientation handlers have no layer bounds check.
The CLI restricts reads and writes to the nine user layers rather than allowing access to adjacent settings bytes.
Zero-valued sleep timers are accepted on this known version, without claiming what zero means physically.

Example partial config, not a recommended preference:

```json
{
  "schema_version": 1,
  "custom_dpi": 1200,
  "scroll_dpi": 80,
  "dpi_stage_count": 3,
  "dpi_index": 1,
  "layers": [{"layer": 2, "orientation": 90}]
}
```

```sh
uv run nape validate examples/firmware-130-config.json
uv run nape plan examples/firmware-130-config.json
# Only after approving the diff:
uv run nape apply examples/firmware-130-config.json --write --backup before-130.json
```

## Records and deletions

Absent `A7 26` tap-holds and out-of-count `A7 28` combo reads return unchanged requests.
Only an actual response establishes absence.
Timeouts always abort; the CLI never converts a timeout into an empty slot.
Use `create: true` for a new record; updates require an existing record.
An already identical record makes creation a no-op; a different existing binding is never overwritten by a create target.

Combo deletion compacts the table.
Config indices refer to the original snapshot, not the indices after an earlier deletion.
The CLI updates nondeleted records first, deletes in descending index order, and verifies the complete shifted table.
A deletion of an already absent target is a no-op.
Tap-hold targets use layer/button keys, so their internal compaction does not change the config identifiers.
Tap-hold deletions run before creations to free capacity.

Before any 1.3.0 configuration write, the backup includes every accessible combo and tap-hold target, all keymaps and user-layer angles, device settings, gestures, force-scroll, and the full macro buffer.
Read-back compares preserved state as well as requested changes.
The backup is not atomic, and no whole-snapshot restore command exists.

## Status and persistence

Implemented Nape-specific setters wait for a same-subcommand `A7` response with payload byte 2 equal to zero.
This includes layer selection, tap-hold deletion, and stage-count writes.
Polling uses send/read-back verification; sleep requires zero status, keymap/encoder packets require matching ACKs, and macro chunks require exact echoes.

Several firmware handlers ignore settings-backend errors.
A zero status can therefore mean the runtime change succeeded while saving failed.
Immediate read-back checks reported state only, not power-cycle persistence.
Failed writes stop without retry or automatic rollback and retain the backup path in the error.

Profiles `A7 2B/2C` and host request `A7 30` are no-ops in the analyzed image and remain unexposed.
Delete-all sentinels, factory reset, firmware flashing, and bootloader commands are also outside the configuration interface.
Persistent record sizes and startup memory mappings remain in the research notes, not editable CLI settings.
