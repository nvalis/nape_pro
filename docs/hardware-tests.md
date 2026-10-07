# Hardware verification status

## Test target

- Nape Pro `3434:4004`, firmware `v1.3.0-ZK Aug 20 2026 08:35:53`.
- Link-KM receiver `3434:D026`, firmware `0.1.3`, Nape awake in 2.4 GHz mode in slot 0.
- Linux hidraw backend, configuration collection `FF60:61`.
- VIA protocol 12, nine user keymap layers, five stored DPI stages, 16 macro slots, 2394-byte macro buffer.

Only Nape firmware `v1.3.0-ZK` is supported.
These observations concern this device and transport, not every physical behavior or connection mode.
USB Nape `3434:0440` uses the same CLI implementation and has packet tests, but 1.3.0 hardware checks here used the receiver.
Bluetooth is not implemented.

## Passing read-only checks

The updated CLI passed:

```sh
uv run nape status --advanced --records --layer-orientations
uv run nape export snapshots/nape-130-read-verified.json --advanced --records --layer-orientations
uv run nape validate examples/firmware-130-config.json
uv run nape plan examples/firmware-130-config.json --json
```

No configuration setters, resets, or flashing commands were sent.
The export is local evidence in the git-ignored `snapshots/` directory.

| Read | Observed result |
|---|---|
| Effective/default layer | Both 1, reported orientation 90° |
| Custom DPI | 400 |
| Scroll-mode DPI candidate | 400; physical effect unverified |
| Enabled stage count | 3 |
| Stored DPI stages | `[400, 800, 1200, 2400, 4000]`, stage 2 selected |
| Layer orientations | Layers 1 and 2 at 90°, all other user layers at 0° |
| Combo inventory | All 30 indices returned absent records |
| Tap-hold inventory | All 63 row-0 targets queried; `1:03` and `2:03` had held actions `0x5222` and `0x5221`, with zero tap actions |
| Sleep | Backlight 0, sleep 300, magnet scan 0 |
| Gestures and force modes | All zero |
| Macros | Complete 2394-byte buffer, 16 empty slots |
| Example plan | DPI index 2→1, custom DPI 400→1200, scroll-mode DPI 400→80; no writes |

## Pending hardware verification

All configuration setter families remain unverified on 1.3.0 hardware.
This includes their ACK/status behavior, immediate write/read-back, restoration, deletion compaction, physical effects, and reboot persistence.
The [published-image analysis](../research/nape-1.3.0.md) and packet tests establish implementation evidence, not completed device tests.

Any write test needs explicit approval, a new complete configuration backup, and a restoration plan.
Check getter responses and setter status first, then compare every supported preserved setting after the change.
Power-cycle persistence is a separate test because several firmware handlers ignore storage-backend errors.
Use passive input capture and the [action catalog](action-catalog.md) for physical acceptance checks rather than claiming a stored keycode executed correctly.

## Operational limits

- Keep the Nape awake and stationary, close Launcher, and run configuration commands serially.
  Receiver diagnostics can work while the Nape is asleep; Nape configuration reads cannot.
- Reads are not atomic and requests have no transaction IDs.
  Stop on a timeout; never infer an empty record from missing responses.
- Every configuration write first fsyncs a new backup with all supported configuration families.
  Any read or backup failure prevents setters.
- A failed write can leave partial changes.
  There is no automatic retry, rollback, or whole-snapshot restore command.
- Macro replacement resets the entire macro store before transfer.
  An interrupted transaction can leave macros empty or invalid.
- Immediate read-back verifies reported state, not saving or persistence.
  Zero status does not prove the settings backend succeeded.

See the [configuration guide](configuration.md) for recovery and the [1.3.0 guide](firmware-1.3.0.md) for limits and record compaction.
