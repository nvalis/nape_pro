# Relevant protocol command reference

For implementation planning, not instructions to send arbitrary packets. The [CLI reference](cli-reference.md) lists the commands agents can actually run. **Active DPI-stage selection/restoration is hardware-tested; other pointer and keymap setters remain experimental. Advanced writes remain unimplemented.** A command ID in this document does not establish firmware support.

## Tested transport and decoding

- Receiver: Link-KM `VID:PID = 3434:D026`, usage page/usage **FF60:61**, observed USB interface `3` (discover rather than hardcode it).
- Payload: 32 bytes, command first, zero-padded. Unnumbered HID report: hidapi output is a leading report-ID byte `00` plus the 32-byte payload; received payloads are 32 bytes.
- Do not confuse this channel with the receiver's **008C:01** bridge or **FFC1:01** mouse collections, which share another interface and use numbered reports.
- Issue requests serially. Match command, misc subcommand, and echoed keymap/encoder parameters; ignore unrelated notifications. No request IDs exist, so stop on timeout rather than accepting a possible late reply as a new transaction.
- Reply offsets below are zero-based **within the 32-byte payload**, excluding any HID report-ID prefix.
- Tested receiver firmware: `0.1.3`; Nape firmware: `v1.1.6-ZK`. The reader assumes nine layers, seven button entries, and five DPI stages.

## Reads verified on this device

| Request prefix (hex) | Meaning | Reply decoding | CLI use |
|---|---|---|---|
| `01` | VIA protocol version | Bytes `1..2`, BE16; observed `12` | Diagnostic query only, no dedicated CLI command |
| `A0` | Keychron protocol/instruction metadata | Raw fields; observed prefix `A0 01 00 01` | Diagnostic query only |
| `A1` | Nape firmware | NUL-terminated ASCII from byte `1` | `status`, `export` |
| `A3` | Current Nape layer | Byte `1`, wire `1..9`; CLI subtracts `1` | `status`, `export` |
| `11` | Dynamic keymap layer count | Byte `1`; expected `9` | `status`, `export` |
| `12 offset_hi offset_lo 0E` | Read seven keycodes for one layer | Echo bytes `1..3`; 14 keycode bytes start at `4`, each BE16 | `export` |
| `14 layer 00 direction` | Read encoder `0` binding | Echo bytes `1..3`; keycode at `4..5`, BE16 | `export` |
| `A7 0D` | Polling-rate information | Supported-rate bitmap at `5`; current-rate index at `6` | `status`, `export` |
| `A7 20` | Global/default orientation | Byte `2` × `45` degrees | `status`, `export` |
| `A7 21` | Active DPI stage | Byte `2`, index `0..4` | `status`, `export` |
| `A7 24 stage` | Stage's DPI value | Bytes `2..3`, LE16 | `status`, `export` |
| `A7 31` | Battery | Byte `2` = percentage, byte `3` nonzero = charging | `status`, `export` |
| `B1` | Receiver protocol/features | Bytes `1..2`, LE16; bytes `3..4` retained as raw features | `receiver-info` |
| `B2` | Receiver paired-slot state | Three records starting at `2`, `7`, `12`: VID BE16, PID BE16, status byte | Receiver diagnostics and awake check |
| `B3` | Receiver firmware | NUL-terminated ASCII from byte `1` | `receiver-info` |

Keymap offset = `layer * 14`, layer `0..8`. Column order: `03`, `04`, `01`, `02`, `M1`, `M2`, `Press`. Encoder direction `0` = CCW; `1` = CW.

Polling-rate index/bitmap bit table: `0→8000`, `1→4000`, `2→2000`, `3→1000`, `4→500`, `5→250`, `6→125` Hz. This is a decoder table, **not** a claim that the Nape supports 8 kHz. Honor the device's supported-rate bitmap.

`BC` is an unsolicited receiver state notification, not a host command. Nape `A3` reports may also arrive asynchronously. The shared read path admits only the command IDs in the table above; `A7` is restricted to subcommands `0D`, `20`, `21`, `24`, `31`. Guarded apply encodes separate pointer/keymap setters, requiring backup/target guards and read-back; it does not relax this read allowlist.

## Experimental pointer setter encodings

These are the pointer write payloads `apply` can construct, padded to 32 bytes with the same unnumbered HID envelope. Layouts come from the NapeBar source; only `A7 22` currently has a passing hardware write/restore test.

| Prefix (hex) | Meaning |
|---|---|
| `A7 23 stage dpi_lo dpi_hi` | Set one DPI stage value, LE16 |
| `A7 22 stage` | Select DPI stage `0..4` |
| `A7 34 angle_units` | Set global/default angle, degrees divided by 45 |
| `A7 0E rate_index` | Set polling rate using the decode table above |

Only changed values are sent, in the order above. Apply does not depend on setter ACKs: it waits briefly, then reads back all pointer fields and the keymap. Firmware may reject/quantize input; persistence across reboot is not established. Use the guarded CLI, never arbitrary raw packets.

## Experimental keymap setter encodings

These use the same 32-byte envelope and guarded apply path, but are not hardware-tested yet.

| Prefix (hex) | Meaning |
|---|---|
| `05 layer 00 column keycode_hi keycode_lo` | Set one row-0 button binding; column `0..6` follows the button order above |
| `15 layer 00 direction keycode_hi keycode_lo` | Set encoder-0 CCW/CW binding; direction `0`/`1` |

Layer indices are `0..8`; keycodes are BE16. Apply waits for a matching command ACK before the next keymap setter and stops on timeout without retry. ACKs do not establish the requested stored value: final read-back compares every layer/button/dial entry to the merged target, including unchanged entries.

## Full known NAPE subcommand list

All are under top-level **`A7`**. Names below omit the common `KC_USER_CMD_NAPE_` prefix (gesture-scroll names are from Launcher). **Source-only** means documented externally but neither exposed by this CLI nor verified here. Unknown IDs/gaps are deliberately omitted, not presumed supported.

| Subcommand | Name | Direction | Current support |
|---|---|---|---|
| `20` | `GET_ORI` | Read | Verified global/default angle |
| `21` | `GET_DPI` | Read | Verified active stage |
| `22` | `SET_DPI` | Write | Hardware-tested selection and restoration via apply |
| `23` | `SET_DPI_VALUE` | Write | Experimental apply; not hardware-tested |
| `24` | `GET_DPI_VALUE` | Read | Verified stage DPI |
| `25` | `SET_TAPHOLDS` | Write | Source-only |
| `26` | `GET_TAPHOLDS` | Read | Source-only |
| `27` | `SET_COMBOS` | Write | Source-only |
| `28` | `GET_COMBOS` | Read | Source-only |
| `29` | `SET_GESTURE` | Write | Source-only |
| `2A` | `GET_GESTURE` | Read | Source-only |
| `2B` | `SET_PROFILE` | Write | Source-only |
| `2C` | `GET_PROFILE` | Read | Source-only; enum exists, no CLI operation |
| `2D` | `SET_LAYER` | Write | Source-only |
| `2E` | `DEL_COMBOS` | Write | Source-only |
| `2F` | `DEL_TAPHOLDS` | Write | Source-only |
| `30` | `BAT_REPORT` | Write | Source-only reporting configuration |
| `31` | `GET_BAT_REPORT` | Read | Verified battery status |
| `32` | `Set_Force_Gesture_Scroll` | Write | Source-only |
| `33` | `Get_Force_Gesture_Scroll` | Read | Source-only |
| `34` | `SET_ORI` | Write | Experimental apply; `protocol set-orientation` still only previews |
| `38` | `GET_LAYER_ORI` | Read | Source-only; enum exists, no CLI operation |
| `39` | `SET_LAYER_ORI` | Write | Source-only; enum exists, no CLI operation |

Orientation uses units of 45 degrees. DPI stages are `0..4` on tested hardware. Per-layer orientation and profile indexing/layouts still need device verification. Do not infer a DPI write range or tap/hold timing limits from these command IDs.

## Other relevant commands

These IDs are reported by the linked sources, **not hardware-tested write support**. None are admitted by the current read allowlist. Single-key, encoder, and polling-rate setters have experimental apply implementations; other entries remain source-only.

| Prefix (hex) | Name / purpose | Direction |
|---|---|---|
| `04` | `DYNAMIC_KEYMAP_GET_KEYCODE`, one key | Read |
| `05` | `DYNAMIC_KEYMAP_SET_KEYCODE`, one key (experimental apply) | Write |
| `13` | `DYNAMIC_KEYMAP_SET_BUFFER`, keymap bytes | Write |
| `15` | `DYNAMIC_KEYMAP_SET_ENCODER` (experimental apply) | Write |
| `0C` | `DYNAMIC_KEYMAP_MACRO_GET_COUNT` | Read |
| `0D` | `DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE` | Read |
| `0E` | `DYNAMIC_KEYMAP_MACRO_GET_BUFFER` | Read |
| `0F` | `DYNAMIC_KEYMAP_MACRO_SET_BUFFER` | Write |
| `10` | `DYNAMIC_KEYMAP_MACRO_RESET` | Write/reset |
| `A7 0E` | Polling-rate setter from NapeBar (experimental apply) | Write |

A top-level `0D` is a macro query, whereas **`A7 0D`** is a polling query. Do not confuse the command namespaces. Buffer-based keymap writes and macro encodings/capacities remain unimplemented. Setter acceptance, persistence, acknowledgements, and restoration behavior still need hardware verification; apply currently checks immediate read-back only.

Factory reset, bootloader, firmware-update, RGB, Hall Effect, and generic high-rate mouse protocols are outside this reference's Nape configuration scope. Do not send them during configuration inspection.

## Sources and local implementation

- [NapeBar NapeHID.swift](https://github.com/ky0209/NapeBar/blob/main/Sources/NapeBar/Protocol/NapeHID.swift): Nape-specific pointer/keymap layouts and candidate setters.
- [Launcher command map](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/command-map.md): VIA and full NAPE command IDs.
- [Mouse/trackball notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/mouse-protocol.md): NAPE feature descriptions; generic mouse material is not automatically applicable.
- [Receiver notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/bridge-dongle-protocol.md): receiver commands; collection/report details differ from our tested Raw HID path.
- Local: [`channel.py`](../src/nape_cli/channel.py), [`receiver.py`](../src/nape_cli/receiver.py), [`snapshot.py`](../src/nape_cli/snapshot.py), [`protocol.py`](../src/nape_cli/protocol.py), [`apply.py`](../src/nape_cli/apply.py), [`config.py`](../src/nape_cli/config.py).

External sources are reverse engineering, not authoritative firmware specifications. Prefer our hardware-tested read behavior when source descriptions disagree.
