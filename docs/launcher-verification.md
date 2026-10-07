# Current official Launcher source verification

The CLI's advanced Nape layouts and action catalog were checked against the deployed [Keychron Launcher v1.5.0 bundle](https://launcher.keychron.com/main.be11320b2a72b61b.js). This is implementation evidence, **not a firmware specification or proof of runtime behavior**. Hardware coverage is maintained separately in [hardware-tests.md](hardware-tests.md).

## Configuration behavior

| Area | Current CLI behavior |
|---|---|
| HID envelope | Unnumbered report ID `0`, 32-byte payload; verified through Link-KM `FF60:61` |
| Active layer | Read `A3` byte `1` unchanged; setter `A7 2D layer` uses the same wire value. Tested firmware omits the setter ACK; CLI verifies read-back |
| Orientation | `A7 20` angle units × 45; global setter `A7 34` requires its ACK. Per-layer getter `A7 38` is unusable on tested firmware, so guarded writes are blocked |
| Polling | Primary bitmap/index at `5/6`, secondary at `10/11`; primary setter preserves secondary index and verifies it |
| Buttons / encoder | Seven BE16 row-0 keycodes per layer; encoder `0`, directions `0/1`. Setter ACK checks include encoder direction |
| Tap-holds | Targeted layer/column records with LE16 tap/held actions; activation requires a separate `CUSTOM(41)` button binding. Tested deletion is verified by read-back without Launcher's expected ACK |
| Combos | Indexed timeout/layer/columns/tap/held records; columns passed through unchanged. CLI requires positive evidence for empty records, never a timeout |
| Gestures / force-scroll | Four LE16 directional actions and two raw mode bytes; partial inputs merged with preserved state |
| Custom DPI / cycling-stage count | Layouts implemented, but getters echo requests on tested firmware. Values become `null` and targeted configs are refused |
| Sleep | Three LE16 raw fields; omitted values preserved; unusable all-zero backlight/sleep state refused |
| Macro replacement | Full backup, reset ACK, final-byte invalidation, chunk transfer, finalization, complete read-back. Exact echoes required for chunks and markers |
| Macro codec | Protocol-dependent action/text decoding; reserved-opcode text rejected during planning; incomplete slots/actions fail decoding |
| Profiles | Enum IDs exist, but no usable Nape profile operation was found; unsupported |

Intentional differences from Launcher: no automatic retry, no empty-record inference from timeout, explicit write/backup guards, and complete expected-state read-back. Neither an ACK nor source parity establishes persistence.

## Named-action evidence

The [action catalog](action-catalog.md) uses the **VIA protocol-12** table selected by Launcher, not a generic QMK table:

- Module `13814`, `getKeycodeEnum()`: protocol `12/13` selects export `xV` from module `44040`.
- Module `44040`, export `xV` (enum `E`): numeric keyboard/mouse codes and layer/macro/custom bases.
- Module `44148`: symbolic conversion (`MO`, `TG`, `TO`, `MACRO`, `CUSTOM`) and momentary/toggle/switch descriptions.
- Module `58618`: Nape/trackball action aliases and record/setting operations. It identifies mouse Back, scroll directions, gesture/scroll mode bindings, and tap-hold activation.
- Module `33550`: trackball menus. Its displayed `MO(0)` corresponds to code `MO(1)` (similarly shifted toggle/switch labels); UI labels must not be treated as wire indices.
- Module `52411`: macro decoding; module `61892`: serial WebHID transport.

Protocol-12 examples: mouse Back `0x00D4`, wheel Up/Down `0x00D9/0x00DA`, momentary base `0x5220`, macro base `0x7700`, custom base `0x7E00`. These differ from older protocol tables in the same bundle.

The catalog is a numeric lookup reference; the CLI still accepts four-digit hexadecimal bindings, not symbolic names. Combo button-mask encoding, actual momentary-layer release behavior, and UI layer correspondence require additional verification. Do not fill these gaps by assuming generic keyboard behavior.

## Scope boundaries

Generic Keychron mouse/demo features do not establish Nape support. No debounce, lift-off distance, motion sync, lighting or haptics support is claimed. Firmware flashing, bootloader, pairing and factory reset are outside configuration scope. When source and tested firmware disagree, retain raw replies and prefer hardware-backed behavior without bypassing safety checks.
