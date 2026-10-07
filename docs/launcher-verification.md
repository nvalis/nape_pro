# Official Launcher source verification

The advanced packet layouts and action catalog were checked against the [deployed Keychron Launcher v1.5.0 bundle](https://launcher.keychron.com/main.be11320b2a72b61b.js).
The [published 1.3.0 image](../research/nape-1.3.0.md) supplies the firmware contract where Launcher behavior differs or omits a command.
Only Nape `v1.3.0-ZK` is supported.
Source inspection and packet tests do not prove physical behavior, setter acceptance, or reboot persistence.
The [hardware matrix](hardware-tests.md) lists completed read-only device checks separately.

## Configuration evidence

| Area | CLI behavior |
|---|---|
| HID envelope | Unnumbered report ID 0, 32-byte payload on `FF60:61` |
| Layers | Effective `A3` and default `A7 35` kept separate; `A7 2D` sets default layer |
| Orientation | Effective `A7 20` and per-layer `A7 38/39`; CLI bounds-checks nine user layers |
| Polling | Primary bitmap/index `5/6`, secondary `10/11`; primary writes preserve secondary index |
| Buttons/encoder | Seven BE16 row-0 bindings per layer; encoder 0, directions 0/1 |
| Tap-holds | LE16 tap/held pairs; activation requires separate `CUSTOM(41)` binding; 30-record capacity |
| Combos | Indexed timeout/layer/columns/tap/held records; deletion compacts the 30-slot table |
| Gestures/force-scroll | Four LE16 actions and nibble-valued force modes; partial inputs preserve omitted fields |
| DPI | Five stored stages, enabled count `1..5`; custom `400..4000`, scroll-mode candidate `40..4000` |
| Sleep | Three raw LE16 fields; omitted values preserved, zero timers accepted without claimed semantics |
| Macro replacement | Complete backup, reset ACK, invalidation marker, exact echoed chunks, finalization, full read-back |
| Macro codec | Reserved-opcode text rejected; incomplete actions/slots fail decoding |
| Profiles/battery-report configuration | No-op host handlers in 1.3.0; not exposed |

The CLI does not copy Launcher's automatic retries or empty-record timeout behavior.
It requires returned evidence for absence, explicit write/backup guards, and preserved-state verification.
The firmware's same-subcommand zero-status ACKs supersede assumptions from Launcher helper methods.
Several settings handlers ignore backend errors, so a zero ACK cannot establish persistence.

## Named-action evidence

The [action catalog](action-catalog.md) uses the protocol-12 table selected by Launcher:

- Module `13814`, `getKeycodeEnum()`, selects export `xV` from module `44040` for protocol 12/13.
- Module `44040`, export `xV`, supplies numeric keyboard/mouse codes and layer/macro/custom bases.
- Module `44148` supplies `MO`, `TG`, `TO`, `MACRO`, and `CUSTOM` conversion and descriptions.
- Module `58618` supplies Nape aliases, settings, mouse Back, scroll directions, gesture/scroll modes, and tap-hold activation.
- Module `33550` shifts some trackball menu labels; displayed `MO(0)` corresponds to code `MO(1)`.
- Module `52411` decodes macros; module `61892` implements serial WebHID transport.

Examples are mouse Back `0x00D4`, wheel Up/Down `0x00D9/0x00DA`, momentary base `0x5220`, macro base `0x7700`, and custom base `0x7E00`.
The CLI accepts numeric four-digit hex bindings, not symbolic labels.
Do not invent combo-mask bits or claim physical release behavior from source descriptions.

## Boundaries

Generic Keychron mouse/demo code does not establish Nape support.
No debounce, lift-off distance, motion sync, lighting, or haptics support is claimed.
Flashing, bootloader, pairing, factory reset, and bulk record deletion remain outside configuration scope.
Retain raw replies when investigating disagreements rather than bypassing safety checks.
