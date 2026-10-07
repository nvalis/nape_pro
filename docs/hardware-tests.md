# Hardware verification log

Tested receiver: Link-KM `3434:D026`, firmware `0.1.3`. Nape: receiver slot 0, paired ID `3434:4004`, firmware `v1.1.6-ZK Mar 9 2026 16:31:16`. Tests ran over the receiver's `FF60:61` Raw HID channel in WSL.

## Active DPI stage: write and restore — passed

A temporary, approved test used `nape apply --write` to select an existing stage, then restore the original. DPI values and keymap were never intentionally changed.

| Step | Verified state |
|---|---|
| Before | Stage `2`, DPI `1600`; stages `[450,800,1600,3200,4000]` |
| Apply `{"schema_version":1,"dpi_index":1}` | Stage `1`, DPI `800`; apply reported `verified: true` |
| Apply `{"schema_version":1,"dpi_index":2}` | Restored stage `2`, DPI `1600`; apply reported `verified: true` |
| Export after restoration | Firmware, layer count, active layer, angle, DPI selection/values, polling rate/support, and all nine keymaps equal the original snapshot |

Commands used after connecting/waking the device:

```sh
uv run nape plan snapshots/dpi-stage-test.json --json
uv run nape apply snapshots/dpi-stage-test.json --write --backup snapshots/before-dpi-stage-test.json --json
uv run nape status
uv run nape apply snapshots/dpi-stage-restore.json --write --backup snapshots/before-dpi-stage-restore.json --json
uv run nape export snapshots/after-dpi-stage-restore.json
```

The config, pre-write snapshots, and final export remain in local `snapshots/` (gitignored). The receiver was detached from WSL after the test. It was previously **force-bound**, so Windows access still requires `usbipd unbind --busid 7-2` in Administrator PowerShell. This session's unbind attempt failed for lack of administrator privileges; detach alone does not restore force-bound devices.

**What this establishes:** `A7 22 stage` changes the active DPI stage on this target; immediate read-back and restoration work. Each apply saved a new supported-state snapshot before its setter.

**What it does not establish:** persistence after reboot; other setter support; macro/gesture/advanced-state preservation (those features are not exported). Simulated-device tests cannot substitute for separate hardware tests of other setters. Do not infer that all writes are hardware-verified from this result.
