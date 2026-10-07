# Relevant protocol command reference

For implementation planning, not instructions to send arbitrary packets. The [CLI reference](cli-reference.md) lists the commands agents can actually run. **Broad storage/read-back tests passed for DPI, polling, orientation/layer, keymaps, tap-holds, existing combos, sleep, gestures/force-scroll, and full macro replacement.** Physical actions and reboot persistence remain unverified; see the [hardware matrix](hardware-tests.md) for coverage and exceptions. Advanced packet layouts are matched to the deployed Keychron Launcher bundle, but source methods do not establish that Nape firmware supports them. Read-only hardware exceptions and unavailable replies are noted below. [Launcher source verification](launcher-verification.md) summarizes current source evidence and intentional differences. The [action catalog](action-catalog.md) supplies protocol-12 named bindings.

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
| `A3` | Current Nape layer | Byte `1` retained unchanged, `0..8`, matching Launcher | `status`, `export` |
| `11` | Dynamic keymap layer count | Byte `1`; expected `9` | `status`, `export` |
| `12 offset_hi offset_lo 0E` | Read seven keycodes for one layer | Echo bytes `1..3`; 14 keycode bytes start at `4`, each BE16 | `export` |
| `14 layer 00 direction` | Read encoder `0` binding | Echo bytes `1..3`; keycode at `4..5`, BE16 | `export` |
| `A7 0D` | Polling-rate information | Primary bitmap/index at `5/6`; secondary bitmap/index at `10/11`, retained for preservation/read-back | `status`, `export` |
| `A7 20` | Reported orientation | Byte `2` × `45` degrees; on tested firmware changed with active layer (layer 1: `90°`, layer 2: `0°`) | `status`, `export` |
| `A7 21` | Active DPI stage | Byte `2`, index `0..4` | `status`, `export` |
| `A7 24 stage` | Stage's DPI value | Bytes `2..3`, LE16 | `status`, `export` |
| `A7 26 layer 00 column` | One tap-hold binding | Echo layer/row/column at bytes `2..4`; tap LE16 at `5..6`; hold LE16 at `7..8` | Targeted config plan/apply |
| `A7 28 index` | One combo slot | Index `2`; timeout LE16 `3..4`; layer `5`; columns byte `6`; tap LE16 `7..8`; hold LE16 `9..10` | Targeted config plan/apply |
| `A7 2A` | Gesture actions | Four LE16 keycodes at `2..9`: up, down, left, right | `status/export --advanced` |
| `A7 31` | Battery | Byte `2` = percentage, byte `3` nonzero = charging | `status`, `export` |
| `A7 33` | Force gesture-scroll state | Byte `2` gesture mode, byte `3` scroll mode | `status/export --advanced` |
| `A7 38 layer` | Per-layer orientation | Launcher expects byte `2` × `45` degrees; tested Nape echoes requested layer in byte `2` and returns `00` in byte `3`, so no valid angle was decoded | `export --layer-orientations` (fails safely on tested firmware) |
| `B1` | Receiver protocol/features | Bytes `1..2`, LE16; bytes `3..4` retained as raw features | `receiver-info` |
| `B2` | Receiver paired-slot state | Three records starting at `2`, `7`, `12`: VID BE16, PID BE16, status byte | Receiver diagnostics and awake check |
| `B3` | Receiver firmware | NUL-terminated ASCII from byte `1` | `receiver-info` |

Keymap offset = `layer * 14`, layer `0..8`. Column order: `03`, `04`, `01`, `02`, `M1`, `M2`, `Press`. Encoder direction `0` = CCW; `1` = CW.

Polling-rate index/bitmap bit table: `0→8000`, `1→4000`, `2→2000`, `3→1000`, `4→500`, `5→250`, `6→125` Hz. This is a decoder table, **not** a claim that the Nape supports 8 kHz. Honor the device's supported-rate bitmap.

`BC` is an unsolicited receiver state notification, not a host command. Nape `A3` reports may also arrive asynchronously. The read allowlist admits only the commands above, VIA macro queries, and the implemented `A7` read subcommands. Tap-hold and combo reads are target-specific; the Launcher waits for a matching record and combo queries time out when no non-empty slot is returned. Guarded apply encodes only validated setters and performs read-back.

## Additional Launcher-derived reads

These queries are performed by `status/export --advanced` or when a config targets custom DPI, stage count, or sleep. Standard status/export remain unchanged. On tested firmware, `A7 36` and `A7 3C` return the exact zero-padded query, so the snapshot preserves the raw response and represents these values as unavailable (`null`); configs targeting them are refused. Sleep returns usable state and remains independently readable/plannable. No defaults are guessed.

| Prefix | Reply decoding | Config field |
|---|---|---|
| `A7 36` | LE16 bytes `2..3`; exact zero-padded query echo is treated as unavailable (`null`) | `custom_dpi` |
| `A7 3C` | Byte `2`, valid values `1..5`; exact zero-padded query echo is treated as unavailable (`null`) | `dpi_stage_count` |
| `A7 0B` | Backlight/sleep/magnet-scan LE16 at `3..4`, `5..6`, `7..8`; read verified on tested firmware | Partial `sleep` map: `backlight`, `sleep`, `magnet_scan` |

Sleep units and zero semantics are not established. Like Launcher, the CLI rejects a reply with both backlight/sleep values zero and refuses configs that would make read-back unusable. The Launcher helper `numToHighLow` defaults to `LowToHigh`, confirming little-endian setter values despite its name.

## Experimental pointer setter encodings

These are the pointer write payloads `apply` can construct, padded to 32 bytes with the same unnumbered HID envelope. Layouts come from the NapeBar source; DPI selection/values, polling, orientation/layer, tap-hold create/delete, existing-combo updates, sleep, and gestures/force-scroll have passing storage tests. Custom DPI, stage count, per-layer orientation, and combo deletion remain unavailable or untested as noted in the hardware matrix.

| Prefix (hex) | Meaning |
|---|---|
| `A7 23 stage dpi_lo dpi_hi` | Set one DPI stage value, LE16 |
| `A7 22 stage` | Select DPI stage `0..4` |
| `A7 37 dpi_lo dpi_hi` | Set separate custom DPI; ACK `A7 37` |
| `A7 3D count` | Set enabled cycling-stage count `1..5`; fire-and-forget, guarded by immediate selection/count queries and final read-back |
| `A7 0C backlight_lo backlight_hi sleep_lo sleep_hi magnet_lo magnet_hi` | Set merged sleep state; ACK byte `2 == 0` means success |
| `A7 34 angle_units` | Set reported orientation, degrees divided by 45; set/restore hardware-tested |
| `A7 39 layer angle_units` | Set per-layer angle; Launcher packet layout, but GET/read-back is broken on tested Nape |
| `A7 25 layer 00 column tap_lo tap_hi held_lo held_hi` | Set one tap-hold action pair; keycodes LE16 |
| `A7 27 index timeout_lo timeout_hi layer columns tap_lo tap_hi held_lo held_hi` | Set one combo slot; keycodes and timeout LE16 |
| `A7 29 up_lo up_hi down_lo down_hi left_lo left_hi right_lo right_hi` | Set all four directional actions; keycodes LE16 |
| `A7 2D layer` | Switch active layer; Launcher sends the supplied layer byte directly; tested firmware emits no matching ACK, so CLI verifies with `A3` read-back |
| `A7 2E index` | Delete one combo slot |
| `A7 2F layer 00 column` | Delete one tap-hold; Launcher waits for `A7 25`, but tested firmware omits that ACK. CLI verifies empty record through targeted read-back |
| `A7 32 gesture scroll` | Set force gesture-scroll bytes; ACK byte `2` equal to zero means success |
| `A7 0E rate_index secondary_index` | Set primary polling rate while copying the current secondary index |

Only changed values are sent. ACK-based setters wait for their observed marker; active-layer switching is verified by `A3` read-back because the tested firmware omits its `A7 2D` ACK. Macro writes use the complete transaction described below. ACKs do not prove persistence, so apply also reads back requested state. On an active-layer-only change, apply does not compare `A7 20` against the previous layer's angle; combining a layer switch and orientation target is refused. Per-layer orientation cannot be verified on tested firmware and plan/apply fail before sending that setter. Do not send arbitrary raw packets.

## Experimental keymap setter encodings

These use the same 32-byte envelope and guarded apply path. A layer-0 button and CCW encoder set/restore passed full-keymap hardware read-back.

| Prefix (hex) | Meaning |
|---|---|
| `05 layer 00 column keycode_hi keycode_lo` | Set one row-0 button binding; column `0..6` follows the button order above |
| `15 layer 00 direction keycode_hi keycode_lo` | Set encoder-0 CCW/CW binding; direction `0`/`1` |

Layer indices are `0..8`; keycodes are BE16. Apply waits for a matching command ACK before the next keymap setter and stops on timeout without retry. ACKs do not establish the requested stored value: final read-back compares every layer/button/dial entry to the merged target, including unchanged entries.

## Full known NAPE subcommand list

All are under top-level **`A7`**. Names below omit the common `KC_USER_CMD_NAPE_` prefix (gesture-scroll names are from Launcher). **Launcher-derived** describes source/packet-test evidence only; the support column states hardware coverage separately. Unknown IDs/gaps are deliberately omitted, not presumed supported.

| Subcommand | Name | Direction | Current support |
|---|---|---|---|
| `20` | `GET_ORI` | Read | Verified angle readout; observed value depends on active layer on tested firmware |
| `21` | `GET_DPI` | Read | Verified active stage |
| `22` | `SET_DPI` | Write | Hardware-tested selection and restoration via apply |
| `23` | `SET_DPI_VALUE` | Write | Stage-0 value set/restore hardware-tested (450/800); sensor effects/range unverified |
| `24` | `GET_DPI_VALUE` | Read | Verified stage DPI |
| `25` | `SET_TAPHOLDS` | Write | Record creation/read-back hardware-tested; ACK command `25`; activation unverified |
| `26` | `GET_TAPHOLDS` | Read | Launcher-derived targeted read |
| `27` | `SET_COMBOS` | Write | Existing record update/restore hardware-tested; ACK command `27`; activation unverified |
| `28` | `GET_COMBOS` | Read | Launcher-derived indexed read; no entry/timeout returns no record |
| `29` | `SET_GESTURE` | Write | Full four-direction storage set/restore hardware-tested; ACK command `29` |
| `2A` | `GET_GESTURE` | Read | Launcher-derived read of four LE16 keycodes |
| `2B` | `SET_PROFILE` | Write | Enum only; no operation found in deployed Launcher bundle |
| `2C` | `GET_PROFILE` | Read | Enum only; no operation found in deployed Launcher bundle |
| `2D` | `SET_LAYER` | Write | Hardware-tested switch/restore; tested firmware omits ACK, so verified through `A3` read-back |
| `2E` | `DEL_COMBOS` | Write | Launcher-derived indexed delete; ACK command `2E` |
| `2F` | `DEL_TAPHOLDS` | Write | Deletion hardware-tested; no matching ACK on tested firmware, so verified by targeted read-back |
| `30` | `BAT_REPORT` | Write | Source-only reporting configuration |
| `31` | `GET_BAT_REPORT` | Read | Verified battery status |
| `32` | `Set_Force_Gesture_Scroll` | Write | Two-byte storage setter hardware-tested; status ACK; physical semantics unverified |
| `33` | `Get_Force_Gesture_Scroll` | Read | Launcher-derived two-byte read |
| `34` | `SET_ORI` | Write | Hardware-tested set/restore; `protocol set-orientation` still only previews |
| `36` | Custom DPI get | Read | Unusable request echo on tested firmware; reported as `null` |
| `37` | Custom DPI set | Write | Same-subcommand ACK layout; guarded apply blocked by unavailable getter |
| `38` | `GET_LAYER_ORI` | Read | Launcher expects angle units in byte `2`; tested firmware echoes requested layer, so response is unusable |
| `39` | `SET_LAYER_ORI` | Write | Launcher-derived setter; apply blocked by unusable read-back on tested firmware |
| `3C` | DPI gear count get | Read | Unusable request echo on tested firmware; reported as `null` |
| `3D` | DPI gear count set | Write | Ordered selection/count path implemented; guarded apply blocked by unavailable getter |

Orientation uses units of 45 degrees. DPI stages are `0..4` on tested hardware. The deployed Launcher bundle includes no profile getter/setter use; profile indexing/layout remains unknown and unsupported. On this Nape, `GET_LAYER_ORI` reply byte `2` echoes the request layer and byte `3` is zero, so per-layer angle cannot be determined. Layer-8 orientation state cannot be confirmed; no trustworthy read-back is available. Do not retry or infer a DPI write range or tap/hold timing limits from command IDs.

## Other relevant commands

These are standard VIA IDs. Button/encoder writes and the complete macro transaction have hardware storage tests; other unexposed commands remain untested. The CLI supports macro-buffer reads and complete backed-up replacements. Macro reset is internal to a changed full-buffer replacement only, never exposed as a standalone command or admitted to the read channel. Other listed buffer commands are not exposed.

| Prefix (hex) | Name / purpose | Direction |
|---|---|---|
| `04` | `DYNAMIC_KEYMAP_GET_KEYCODE`, one key | Read |
| `05` | `DYNAMIC_KEYMAP_SET_KEYCODE`, one key (experimental apply) | Write |
| `13` | `DYNAMIC_KEYMAP_SET_BUFFER`, keymap bytes | Write |
| `15` | `DYNAMIC_KEYMAP_SET_ENCODER` (experimental apply) | Write |
| `0C` | `DYNAMIC_KEYMAP_MACRO_GET_COUNT` | Read; advanced export |
| `0D` | `DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE` | Read; advanced export |
| `0E` | `DYNAMIC_KEYMAP_MACRO_GET_BUFFER` | Read; advanced export |
| `0F` | `DYNAMIC_KEYMAP_MACRO_SET_BUFFER` | Guarded macro transaction; exact echoed-packet ACK required |
| `10` | `DYNAMIC_KEYMAP_MACRO_RESET` | Internal first step of backed-up changed macro replacement; command ACK required |
| `A7 0E` | Polling-rate setter from NapeBar (experimental apply) | Write |

A top-level `0D` is a macro query, whereas **`A7 0D`** is a polling query. Macro GET/SET packets use BE16 offsets at `1..2`, byte count at `3`, and data at `4..`, in 28-byte chunks. Launcher protocol v11+ macro encoding is: `00` ends a macro; `01,type,value` encodes Tap (`1`), Down (`2`), Up (`3`); Delay is `01 04` + ASCII decimal milliseconds + `7C`; other bytes are character-stream bytes. Older v9 key actions use `[type,keycode]`; the Launcher decoder also recognizes `04 ASCII_decimal 7C` delays, though the CLI only encodes delays for v11+. Structured macros use the device-reported VIA protocol version and slot count. Macro exports require every reported slot to end in `00`; malformed/truncated buffers fail. Text planning rejects protocol-reserved opcodes. Launcher writes reset first, invalidate the last byte with `FF`, transfer acknowledged chunks, then finalize the last byte with `00`. The CLI performs that complete workflow after fsyncing the full pre-write macro snapshot. It transfers all bytes except the reserved last byte, keeping `FF` in place until finalization, then compares the entire read-back buffer. Markers as well as chunks require exact echo ACKs (stricter than Launcher), and mismatches/timeouts stop without retry or automatic finalization. Structured-text replacement and exact raw-buffer restoration passed hardware tests, including reset/chunk/marker ACKs. Intermittent timeouts occurred; physical macro execution and reboot persistence remain untested.

Factory reset, bootloader, firmware-update, and pairing operations remain out of scope. RGB, Hall Effect, and generic high-rate mouse protocols are also outside this reference's Nape configuration scope. Do not send them during configuration inspection.

## Sources and local implementation

- [NapeBar NapeHID.swift](https://github.com/ky0209/NapeBar/blob/main/Sources/NapeBar/Protocol/NapeHID.swift): Nape-specific pointer/keymap layouts and candidate setters.
- [Launcher command map](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/command-map.md): VIA and full NAPE command IDs.
- [Deployed Keychron Launcher v1.5.0 bundle](https://launcher.keychron.com/main.be11320b2a72b61b.js): packet construction and decoding methods inspected for active layer, tap-holds, combos, gestures, force-scroll, layer orientation, and macro encoding.
- [Mouse/trackball notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/mouse-protocol.md): NAPE feature descriptions; generic mouse material is not automatically applicable.
- [Receiver notes](https://github.com/Tymon3310/keychron-vial/blob/main/docs/launcher/bridge-dongle-protocol.md): receiver commands; collection/report details differ from our tested Raw HID path.
- Local: [`channel.py`](../src/nape_cli/channel.py), [`receiver.py`](../src/nape_cli/receiver.py), [`snapshot.py`](../src/nape_cli/snapshot.py), [`protocol.py`](../src/nape_cli/protocol.py), [`apply.py`](../src/nape_cli/apply.py), [`config.py`](../src/nape_cli/config.py).

External sources are reverse engineering, not authoritative firmware specifications. Prefer our hardware-tested read behavior when source descriptions disagree.
