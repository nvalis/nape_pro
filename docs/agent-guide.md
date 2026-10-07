# Agent guide: working with a Nape Pro

**Current CLI: 0.1.0, read-only.** You can inspect settings and export the keymap, but cannot apply a configuration yet. There is no `apply`, `set`, `restore`, YAML loader, or dry-run apply command. Editing an exported JSON file does not change the device.

See the [CLI/settings reference](cli-reference.md) for every command and field, and the [protocol reference](protocol-reference.md) for known commands not yet implemented.

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
- `receiver-info`, `status`, and `export` select one receiver automatically. For multiple receivers, pass `--index N` using a fresh **default** `nape devices` listing, not `devices --all`.
- JSON IDs are decimal: receiver VID/PID `13364`/`53286`, Raw HID usage page/usage `65376`/`97`.
- Keep the device stationary while exporting; reads are not an atomic snapshot.
- Export refuses to overwrite files and does not create parent directories. Use a new filename in an existing directory.

## Handling a request to configure

1. Read status and export the current state before proposing changes.
2. Confirm the desired angle, DPI stages, polling rate, layer, button, and dial actions. Use zero-based layer/stage indices and preserve unspecified settings.
3. Explain which requested settings are supported for reading and which are unimplemented. Do not invent write commands or assume hex keycodes are portable across firmware versions.
4. **Stop before applying:** this CLI has no settings-write support. Offer to implement a narrowly scoped writer or have the user use Keychron Launcher. Do not bypass the read-only allowlist with ad-hoc packets.
5. After a user changes settings through another tool, re-run `status` and export to a new file to compare results.

An export covers pointer settings, seven button entries per layer, and two dial directions across nine layers. It is **not a complete backup**: macros, tap-holds, combos, gestures, and per-layer orientation are omitted. There is no restore command.

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
# Restore Windows access when finished:
usbipd detach --busid <busid>
```

Attaching takes the receiver away from Windows. Obtain permission before doing this. Binding/force-binding requires Administrator PowerShell; do not assume the bus ID stays constant. Linux device permissions may reset after reconnection.

## When extending the CLI

Keep read and write paths separate. A future writer needs validated inputs, a visible diff/dry-run, explicit user approval, a prior snapshot, and read-back verification. Unknown settings must remain untouched; unsupported rollback must be disclosed. Commit implementation in logical blocks and run:

```sh
uv sync --extra dev --extra hardware
uv run pytest
uv run ruff check .
uv run ty check src
```
