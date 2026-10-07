# Agent guide: working with a Nape Pro

**Current CLI: 0.3.0.** Available configuration families have hardware storage/read-back coverage on Nape firmware `v1.1.6-ZK`; see the [current hardware matrix](hardware-tests.md) for exact scope. Custom DPI, stage count and per-layer orientation cannot be read reliably and targeted writes are blocked. Combo deletion/empty-slot creation, physical action execution and reboot persistence remain unverified. Profiles, YAML and symbolic JSON binding inputs are unsupported. Use the [named-action catalog](action-catalog.md) to translate intent into numeric keycodes without guessing.

`apply` defaults to dry-run; writes require explicit `--write` and a new `--backup` path. Editing an export does not change the device. Macro replacement resets the entire store and is not atomic. Failures may leave partial state; no automatic retry or rollback is performed. Intermittent transport timeouts remain unresolved.

See the [configuration guide](configuration.md) for the JSON schema, write guards, and failure recovery; the [CLI/settings reference](cli-reference.md) for every command/field; and the [protocol reference](protocol-reference.md) for implementation status.

## Normal workflow

Run from this repository; use `uv` for Python and CLI execution:

```sh
uv sync --extra hardware
uv run nape devices --json
uv run nape receiver-info --json
uv run nape status --json
uv run nape export nape-before.json
```

- Tested transport: Nape in **2.4 GHz mode**, awake, through Link-KM receiver `3434:D026`.
- Configuration channel: usage page **`0xFF60`**, usage **`0x61`**. Do not use its normal keyboard/mouse interfaces.
- `receiver-info`, `status`, `export`, `plan`, and `apply` select one receiver automatically. For multiple receivers, pass `--index N` using a fresh **default** `nape devices` listing, not `devices --all`.
- JSON IDs are decimal: receiver VID/PID `13364`/`53286`, Raw HID usage page/usage `65376`/`97`.
- Keep the device stationary while exporting; reads are not an atomic snapshot.
- Export refuses to overwrite files and does not create parent directories. Use a new filename in an existing directory.

## Handling a request to configure

1. Read status and export the current state before proposing changes.
2. Translate the request using the [action catalog and recipes](action-catalog.md). Confirm the target wire layer and physical control, distinguish dial scrolling from trackball scroll mode, and momentary holds from active-layer switches/toggles. For browser Back, disclose mouse Back versus a consumer action or OS shortcut. Write a partial JSON config using four-digit hex keycodes and explicit combo indices; omitted bindings are preserved. Stop and explain unresolved combo-mask/layer-label semantics rather than inventing them. Macro lists/buffers replace the entire store, not just mentioned slots.
3. Run `nape validate CONFIG`, then `nape plan CONFIG --json` or `nape apply CONFIG --dry-run`. Show the actual diff and disclose which setters lack hardware tests and that reboot persistence remains unverified.
4. Obtain explicit user approval for the exact changes before `nape apply CONFIG --write --backup NEW_FILE`. Do not treat a generic request to inspect/build/test the CLI as permission to alter settings. Write guards require the observed firmware/slot combination; do not bypass them with raw packets.
5. Apply verifies all pointer fields and the complete expected keymap, including preserved entries, plus any requested active layer, targeted advanced entries, gesture/scroll settings, and the preserved secondary polling index. For an active-layer-only switch, it does not compare the context-dependent orientation readout with the previous layer. Device-setting configs read/preserve all custom-DPI/count/sleep fields; macro configs back up and verify the full buffer. Disclose the destructive macro-reset phase explicitly before obtaining write approval. All record-read timeouts abort, even for create/delete targets. Re-run status/export as needed. On failure, stop: state may be partially changed and there is no automatic rollback. Follow the configuration guide rather than retrying blindly.

6. Ask the user to run the catalog's physical acceptance checks for the requested behavior, especially combo releases and tap-versus-hold activation. Report storage verification separately from runtime success; do not claim reboot persistence without a power-cycle check.

A standard export covers pointer settings, seven button entries per layer, and two dial directions across nine layers. `export --advanced` adds custom DPI, stage count, sleep, gestures, force-scroll fields, decoded macro slots, and the raw VIA buffer. Tap-holds/combos are read only for configured targets. Per-layer orientation uses a separate flag and currently fails on tested firmware. Exports remain **incomplete backups**: profiles are unavailable, and there is no whole-device restore command.

## Connection problems

| Symptom | Next step |
|---|---|
| No interfaces / JSON `[]` | Check receiver connection; in WSL check USB attachment, not just sharing. Discovery can exit successfully with no devices. |
| `open failed` | Check permissions on the selected `/dev/hidraw*` node; request narrowly scoped access, not access to all devices. |
| No paired device awake | Ask the user to wake the Nape and check 2.4 GHz mode. |
| Unexpected layer count or invalid fields | Stop: the firmware/device may differ from the tested Nape. Keep raw JSON for investigation. |
| Timeout | Check connection first and inspect state after a failed write. Hardware tests saw intermittent macro-read/reset and receiver-state timeouts, even at 5000 ms; increasing `--timeout-ms` is not a guaranteed fix. Do not run concurrent queries or automatically retry low-level requests: replies have no transaction IDs. |

For WSL, run in Windows PowerShell after checking `usbipd list`:

```powershell
usbipd attach --wsl --busid <busid>
# Detach when finished:
usbipd detach --busid <busid>
# If force-bound, also run in Administrator PowerShell to restore Windows access:
usbipd unbind --busid <busid>
```

Attaching takes the receiver away from Windows. Obtain permission before doing this. Binding/force-binding and unbinding require Administrator PowerShell; force-binding prevents Windows use even after detach. Do not assume the bus ID stays constant. Linux device permissions may reset after reconnection.

## When extending the CLI

Keep read and write paths separate. Preserve validated inputs, visible diff/dry-run, explicit approval, pre-write snapshot, and read-back checks when adding setters. Unknown settings must remain untouched; unsupported rollback must be disclosed. Extend hardware support only after targeted verification. Commit implementation in logical blocks and run:

```sh
uv sync --extra dev --extra hardware
uv run pytest
uv run ruff check .
uv run ty check src
```
