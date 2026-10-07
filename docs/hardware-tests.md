# Current hardware verification status

## Supported test target

- Link-KM receiver `3434:D026`, firmware `0.1.3`.
- Nape Pro `3434:4004`, firmware `v1.1.6-ZK Mar 9 2026 16:31:16`.
- Nape awake in 2.4 GHz mode, receiver slot `0`; no other connected paired device.
- Receiver Raw HID channel `FF60:61`, tested in WSL. Discover the interface rather than hardcoding a path.
- VIA protocol version `12`; nine keymap layers, five stored DPI stages, 16 macro slots, 2394-byte macro buffer.

Results apply to this target, not every firmware or connection mode. Direct USB Nape access and Bluetooth are not verified/supported transports.

## Coverage

“Storage verified” means a guarded configuration change and restoration passed immediate read-back. It does **not** mean physical action execution or reboot persistence was tested.

| Feature | Current evidence / limitation |
|---|---|
| Discovery / receiver diagnostics | Reads verified |
| Core status / nine-layer keymap export | Reads verified |
| Advanced status / export | Sleep, gesture/force-scroll and complete macro reads verified; unavailable optional fields retained as `null` |
| DPI selection | Storage verified for stage selection and restoration |
| DPI values | Storage verified for stage 0 at 450 and 800 DPI; sensor effects and full valid range unverified |
| Global orientation | Storage verified at 90° and 135°; reported value depends on active layer |
| Active layer | Storage verified for wire layers 1 and 2; verification uses `A3`, not a setter ACK |
| Primary polling rate | Storage verified at 500 and 1000 Hz; secondary index preserved and verified; actual reporting frequency unverified |
| Button / encoder bindings | Layer-0 M1 and CCW edits/restoration passed complete keymap read-back; individual named actions were not physically tested |
| Tap-hold records | Creation and deletion storage verified; activation binding and tap/hold execution unverified |
| Combo records | Existing slot update/restoration storage verified; deletion and empty-slot creation untested; button-mask and runtime semantics unverified |
| Sleep | Partial raw-field edit/restoration storage verified; omitted fields preserved; units and zero semantics unverified |
| Gestures / force-scroll | Binding/raw-byte edit/restoration storage verified; physical effects unverified |
| Structured / raw macros | Complete structured-text replacement and exact raw-buffer restoration storage verified, including reset/chunk/marker ACKs; action execution unverified |
| Custom DPI / cycling-stage count | Getters echo the zero-padded request; exported as `null`; targeted plans/writes refused |
| Per-layer orientation | Getter echoes requested layer, not a trustworthy angle; guarded plan/apply blocked. Layer-8 orientation state cannot be confirmed |
| Profiles | No usable Nape operation found; not implemented |
| Firmware / bootloader / pairing / factory reset | Outside scope; not tested or exposed |

Configuration fields in the completed broad sweep matched the pre-test export after restoration. Targeted tap-hold deletion and combo restoration were also verified. Backups and raw diagnostic evidence are local in git-ignored `snapshots/`; exports are not complete device backups.

## Operational limitations

- **Intermittent transport timeouts remain unresolved**, including receiver-state queries, macro-buffer reads and macro-reset ACK waits. A 5000-ms timeout does not reliably eliminate them.
- Requests have no transaction IDs. Run commands serially, close other configurators, and do not silently retry failed writes.
- Active-layer changes omit the expected `A7 2D` ACK on tested firmware. Apply uses layer read-back; orientation is not compared against the previous layer's angle. Switch layers and set orientation in separate applies.
- Tap-hold deletion omits the expected `A7 25` ACK. Apply verifies the targeted empty record instead. Other ACK requirements, including macro reset and exact buffer echoes, remain enforced.
- Macro replacement resets the entire store, then invalidates/transfers/finalizes it after saving a full-buffer backup. Interrupted writes can leave macros empty or invalid.
- A failure may leave partial changes. There is no automatic retry, rollback, or whole-snapshot restore. Inspect current state before proposing recovery.
- Physical behavior, combo release timing, and persistence across power cycles remain unverified. Use the acceptance checks in the [action catalog](action-catalog.md) after approved configuration changes.

See [configuration](configuration.md) for write guards/recovery and [Launcher verification](launcher-verification.md) for source evidence.
