# Agent guide: working with a Nape Pro

**Current CLI: 0.3.0.** Core reads and active DPI-stage selection/restoration are hardware-tested; other pointer/keymap setters, per-layer orientation, and raw macro-buffer writes remain simulated-device tested only. `apply` defaults to dry-run; actual writes require explicit `--write` and a new `--backup` path. Full restore, tap-holds, combos, gestures, profiles, active-layer switching, symbolic keycodes, and YAML loading are not implemented. Editing an export does not change the device.

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
2. Confirm the desired settings. Write a partial JSON config for pointer settings, layer button/dial bindings, per-layer orientation, or (experimentally) the full raw macro buffer. Use zero-based layer/stage indices and four-digit hex keycodes; omitted entries are preserved. Do not invent firmware action codes or promise physical behavior from a successful storage read-back.
3. Run `nape validate CONFIG`, then `nape plan CONFIG --json` or `nape apply CONFIG --dry-run`. Show the actual diff and disclose which setters lack hardware tests and that reboot persistence remains unverified.
4. Obtain explicit user approval for the exact changes before `nape apply CONFIG --write --backup NEW_FILE`. Do not treat a generic request to inspect/build/test the CLI as permission to alter settings. Write guards require the observed firmware/slot combination; do not bypass them with raw packets.
5. Apply verifies all pointer fields and the complete expected keymap, including preserved entries, plus any requested per-layer orientation or macro buffer. Re-run status/export as needed. On failure, stop: state may be partially changed and there is no automatic rollback. Follow the configuration guide rather than retrying blindly.

A standard export covers pointer settings, seven button entries per layer, and two dial directions across nine layers. `export --advanced` additionally reads per-layer orientation and the raw VIA macro buffer. Exports remain **incomplete backups**: tap-holds, combos, gestures, and profiles are omitted, and there is no restore command.

## Connection problems

| Symptom | Next step |
|---|---|
| No interfaces / JSON `[]` | Check receiver connection; in WSL check USB attachment, not just sharing. Discovery can exit successfully with no devices. |
| `open failed` | Check permissions on the selected `/dev/hidraw*` node; request narrowly scoped access, not access to all devices. |
| No paired device awake | Ask the user to wake the Nape and check 2.4 GHz mode. |
| Unexpected layer count or invalid fields | Stop: the firmware/device may differ from the tested Nape. Keep raw JSON for investigation. |
| Timeout | Check connection first. Do not run concurrent queries or automatically retry low-level requests: replies have no transaction IDs. |

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
