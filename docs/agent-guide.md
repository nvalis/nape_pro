# Agent guide

Only Nape firmware `v1.3.0-ZK` is supported.
Core and advanced reads, all user-layer angles, complete record export, and dry-run planning passed on the connected device through the receiver.
Configuration setters, physical effects, and reboot persistence still need hardware verification.
See the [hardware matrix](hardware-tests.md), [1.3.0 guide](firmware-1.3.0.md), and [configuration guide](configuration.md).

`apply` defaults to dry-run.
Writes require explicit approval for the exact changes, `--write`, and a new `--backup` path.
A request to inspect, implement, test, commit, or push the CLI is not permission to change device settings.
Macro replacement resets the entire store; failures can leave partial state and never trigger automatic retries or rollback.
Profiles, YAML, and symbolic JSON binding inputs are unsupported.
Use the [action catalog](action-catalog.md) rather than guessing numeric codes.

## Inspect first

```sh
uv sync --extra hardware
uv run nape devices --json
# Receiver-only diagnostics; skip for direct USB:
uv run nape receiver-info --json
uv run nape status --advanced --records --layer-orientations --json
uv run nape export nape-before.json --advanced --records --layer-orientations
```

The supported configuration collection is `FF60:61`, on receiver `3434:D026` or USB Nape `3434:0440`.
Do not use normal keyboard/mouse collections or the numbered bridge channel.
With multiple configuration candidates, pass an index from a fresh default `nape devices` listing, not `devices --all`.
Indices identify collections, not receiver slots or USB interface numbers.
Receiver diagnostics select only a receiver and can work while the Nape is asleep.
Wireless configuration needs the Nape awake in 2.4 GHz mode.

JSON VID/PID values are decimal: receiver `13364/53286`, USB Nape `13364/1088`, usage page/usage `65376/97`.
Keep the device stationary and close other configurators.
Reads are not atomic and exports never overwrite files or create parent directories.
The full export covers supported configuration, not installed flash or a whole-device restore format.

## Configure only after approval

1. Read status and export current state.
2. Translate intent with the action catalog.
   Confirm the wire layer and physical control, dial versus trackball scrolling, and momentary holds versus default-layer switching.
   Snapshots separate effective `active_layer` from `default_layer`; the existing `active_layer` config field sets the default.
   Preserve omitted bindings and do not invent combo masks or shifted layer labels.
3. Write a partial JSON config, then run `validate` and `plan --json` or `apply --dry-run`.
   Show the real diff and disclose unverified setter behavior and persistence.
   The retained examples are [device settings](../examples/firmware-130-config.json) and [full device configuration](../examples/nape-two-layer-config.json), not guaranteed preferences or factory defaults.
   The full config includes empty-record deletions and complete macro replacement.
4. Obtain approval for the exact diff before `apply --write --backup NEW_FILE`.
   Receiver writes require only Nape `3434:4004` awake in slot 0; both transports require firmware `v1.3.0-ZK`.
   Never bypass guards with raw packets.
5. Apply backs up every supported configuration family before setters and checks preserved state afterward.
   Combo deletion compacts the table, so config indices refer to the original snapshot and deletions run in descending order.
   Creation requires a confirmed empty record or an already identical record; timeouts never establish absence.
   Disclose macro reset before approval because macros replace the complete store.
6. After a failure, stop and preserve the backup and error.
   Inspect current state before proposing recovery, never blindly retry or finalize a partial macro transfer.
7. Ask the user to run physical acceptance checks for the requested behavior.
   Report immediate storage read-back separately from action execution and power-cycle persistence.
   Zero status does not prove saving succeeded.

Switch layers and set global orientation in separate applies.
Per-layer angles and five-stage limits come from the firmware contract.
No bulk record deletion, profiles, flashing, factory reset, or pairing commands are exposed.

## Connection problems

| Symptom | Next step |
|---|---|
| No interfaces or `[]` | Check connection; in WSL check attachment, not just sharing |
| Open failed | Check the selected path and request permissions only for that node |
| No paired device awake | Ask the user to wake the Nape and check 2.4 GHz mode |
| Unsupported firmware | Stop; only `v1.3.0-ZK` is supported, with no override |
| Invalid fields or layer count | Stop and preserve evidence; do not infer defaults |
| Timeout | Check connection and inspect state after failed writes; do not retry automatically or run concurrent queries |

On Linux, after discovering the current path, temporary access can be granted with `sudo setfacl -m u:$(id -un):rw /dev/hidrawN`.
Permissions can reset on reconnection.
For WSL, obtain permission before attaching because it takes the device away from Windows:

```powershell
usbipd attach --wsl --busid <busid>
usbipd detach --busid <busid>
# If force-bound, also restore Windows access in Administrator PowerShell:
usbipd unbind --busid <busid>
```

Check `usbipd list` rather than assuming a stable bus ID.
Sharing alone is not attachment, and detach alone does not undo force-binding.

## Development

Keep getters and setters separate.
Preserve validation, visible diffs, explicit approval, complete backups, and full read-back checks.
Keep static binary evidence distinct from device verification.
Commit changes in logical blocks and run:

```sh
uv sync --extra dev --extra hardware
uv run pytest
uv run ruff check .
uv run ty check src
```
