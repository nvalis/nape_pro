# Named keycodes and actions

Use this catalog to translate a request into a **partial numeric JSON config**. Names below are reference labels, not accepted JSON binding strings: write `"0x00D4"`, not `"mouse.back"` or `"KC_MS_BTN4"`.

**Scope:** Nape firmware `v1.1.6-ZK`, VIA protocol **12**, official Launcher v1.5.0. Numeric values and action labels are source-verified; **physical execution and reboot persistence are not verified**. Do not use older QMK/VIA tables: mouse and custom codes differ by protocol version. See [source evidence](launcher-verification.md) and [hardware coverage](hardware-tests.md).

## Physical controls and layers

| Config button | Wire column | Meaning |
|---|---|---|
| `03` | 0 | Button labelled 03 |
| `04` | 1 | Button labelled 04 |
| `01` | 2 | Button labelled 01; keep the leading zero |
| `02` | 3 | Button labelled 02 |
| `M1` | 4 | Physical M1 button, **not macro slot 1** |
| `M2` | 5 | Physical M2 button, **not macro slot 2** |
| `Press` | 6 | Dial push button |

Rotation bindings belong in `dial`: `ccw` (encoder direction 0) and `cw` (direction 1), not in `buttons`. An encoder sends discrete actions; a held/momentary action needs a meaningful press/release source and should not be assigned to rotation as a substitute for a button hold.

Config layers and `active_layer` use unchanged wire indices `0..8`. **Ask which wire layer to edit** when a request says “second layer.” Launcher trackball menus shift some display labels: displayed `MO(0)` uses code `MO(1)`. Do not silently subtract/add one across all layers. Editing `layers[N]` does not select that layer, and setting `active_layer` is not a hold binding.

`combos.columns` is still a raw byte. Wire column order alone does not prove bitmask semantics; the CLI does not accept a named button list for combos. Do not invent a mask or assume a free combo index. Existing-record updates are storage-tested; empty-slot creation and deletion are not.

## No action and transparency

| Named action | Launcher symbol | Hex | Meaning |
|---|---|---|---|
| `none` | `KC_NO` | `0x0000` | No action; not pass-through |
| `transparent` | `KC_TRNS` | `0x0001` | Pass through to an underlying layer; runtime resolution unverified |

## Mouse, scrolling and browser navigation

These are ordinary binding candidates for buttons, dial directions, gesture entries and tap/held record fields. The parser checks encoding, not whether a particular placement behaves sensibly.

| Named action | Launcher symbol | Hex | Meaning |
|---|---|---|---|
| `mouse.left` | `KC_MS_BTN1` | `0x00D1` | Left button |
| `mouse.right` | `KC_MS_BTN2` | `0x00D2` | Right button |
| `mouse.middle` | `KC_MS_BTN3` | `0x00D3` | Middle button |
| `mouse.back` | `KC_MS_BTN4` | `0x00D4` | Mouse Back; usual choice for browser Back on this pointing device |
| `mouse.forward` | `KC_MS_BTN5` | `0x00D5` | Mouse Forward |
| `scroll.up` | `KC_MS_WH_UP` | `0x00D9` | Vertical wheel up |
| `scroll.down` | `KC_MS_WH_DOWN` | `0x00DA` | Vertical wheel down |
| `scroll.left` | `KC_MS_WH_LEFT` | `0x00DB` | Horizontal wheel left |
| `scroll.right` | `KC_MS_WH_RIGHT` | `0x00DC` | Horizontal wheel right |
| `pointer.up` | `KC_MS_UP` | `0x00CD` | Move pointer up, **not scroll** |
| `pointer.down` | `KC_MS_DOWN` | `0x00CE` | Move pointer down |
| `pointer.left` | `KC_MS_LEFT` | `0x00CF` | Move pointer left |
| `pointer.right` | `KC_MS_RIGHT` | `0x00D0` | Move pointer right |
| `browser.back` | `KC_WWW_BACK` | `0x00B6` | Browser consumer action; distinct from mouse Back |
| `browser.forward` | `KC_WWW_FORWARD` | `0x00B7` | Browser consumer action |
| `browser.refresh` | `KC_WWW_REFRESH` | `0x00B9` | Browser consumer action |

Application/OS support can differ. “Browser Back” normally maps here to `mouse.back`; disclose that choice. Use the consumer action only when intended. An OS shortcut such as Alt+Left is a third, distinct choice, not a synonym for either code.

## Common keyboard and media actions

| Named action | Launcher symbol | Hex |
|---|---|---|
| `key.enter` | `KC_ENT` | `0x0028` |
| `key.escape` | `KC_ESC` | `0x0029` |
| `key.backspace` | `KC_BSPC` | `0x002A` |
| `key.tab` | `KC_TAB` | `0x002B` |
| `key.space` | `KC_SPC` | `0x002C` |
| `key.delete` | `KC_DEL` | `0x004C` |
| `key.right` | `KC_RGHT` | `0x004F` |
| `key.left` | `KC_LEFT` | `0x0050` |
| `key.down` | `KC_DOWN` | `0x0051` |
| `key.up` | `KC_UP` | `0x0052` |
| `modifier.left_ctrl` | `KC_LCTL` | `0x00E0` |
| `modifier.left_shift` | `KC_LSFT` | `0x00E1` |
| `modifier.left_alt` | `KC_LALT` | `0x00E2` |
| `modifier.left_gui` | `KC_LGUI` | `0x00E3` |
| `modifier.right_ctrl` | `KC_RCTL` | `0x00E4` |
| `modifier.right_shift` | `KC_RSFT` | `0x00E5` |
| `modifier.right_alt` | `KC_RALT` | `0x00E6` |
| `modifier.right_gui` | `KC_RGUI` | `0x00E7` |
| `media.mute` | `KC_MUTE` | `0x00A8` |
| `media.volume_up` | `KC_VOLU` | `0x00A9` |
| `media.volume_down` | `KC_VOLD` | `0x00AA` |
| `media.next` | `KC_MNXT` | `0x00AB` |
| `media.previous` | `KC_MPRV` | `0x00AC` |
| `media.stop` | `KC_MSTP` | `0x00AD` |
| `media.play_pause` | `KC_MPLY` | `0x00AE` |

Source-defined ranges: `KC_A..KC_Z` = `0x0004..0x001D`; `KC_1..KC_9` = `0x001E..0x0026`, `KC_0` = `0x0027`; `KC_F1..KC_F12` = `0x003A..0x0045`; `KC_F13..KC_F24` = `0x0068..0x0073`. Keyboard codes describe keys, not guaranteed characters on every host layout. GUI means Windows/Command according to OS.

## Layer and macro action families

`n` below is the **code argument/wire target**, not a shifted Launcher display label.

| Named family | Launcher symbol | Protocol-12 encoding | Intended action |
|---|---|---|---|
| `layer.momentary(n)` | `MO(n)` | `0x5220 + n`; e.g. `MO(2)` = `0x5222` | Activate while held |
| `layer.toggle(n)` | `TG(n)` | `0x5260 + n`; e.g. `TG(2)` = `0x5262` | Toggle on/off |
| `layer.switch(n)` | `TO(n)` | `0x5200 + n`; e.g. `TO(2)` = `0x5202` | Switch on press, not temporary |
| `macro.play(n)` | `MACRO(n)` | `0x7700 + n`; slots `0..15` | Execute an already configured macro |

Only targets `1..8` are exposed in the inspected trackball layer menu. Do not infer layer-0 action support from arithmetic. These actions are not physically tested; momentary release and layer interaction need acceptance checks. Do not use a dial rotation as a momentary-layer hold source. Macro triggers are binding codes; macro contents are configured separately and replace the complete store. Macro step keycodes are limited to `0x0000..0x00FF`, so layer/custom/macro-trigger codes cannot be embedded as macro key actions.

## Nape-specific bindings

| Named action | Launcher symbol | Hex | Placement / caveat |
|---|---|---|---|
| `trackball.gesture_hold` | `MO(9)` | `0x5229` | Nape gesture-mode alias; not keymap layer 9 |
| `trackball.scroll_hold` | `MO(10)` | `0x522A` | Nape trackball-scroll alias; not ordinary dial scrolling or keymap layer 10 |
| `tap_hold.activate` | `CUSTOM(41)` | `0x7E29` | Button only; requires that layer/button's separate tap-hold record; Launcher excludes dial activation |
| `orientation.cycle` | `CUSTOM(43)` | `0x7E2B` | Source-labelled orientation loop; physical effect unverified |
| `dpi.cycle` | `CUSTOM(44)` | `0x7E2C` | Source-labelled DPI loop; not a `dpi_index` setting |
| `mouse.double_left` | `CUSTOM(46)` | `0x7E2E` | Source-labelled double left click; physical effect unverified |

The protocol-12 custom base is `0x7E00`. Do **not** use it to invent unlisted actions; some custom codes invoke pairing or bootloader operations. Custom DPI activation is not recommended because the setting cannot be read/verified on tested firmware. Raw `force_gesture_scroll` bytes remain undocumented semantically; do not change them merely to configure the wheel.

## Recipes and acceptance checks

All recipes require a selected wire layer, review of existing bindings/records, `validate`, `plan`, approval of the diff, and a new backup path for `apply --write`. No write is needed to consult this catalog.

### Vertical dial scrolling and button 01 as Back

This example edits **wire layer 0** only. Choose the user's intended layer instead; it does not switch the active layer. Reverse the two scroll codes if the requested direction differs.

```json
{
  "schema_version": 1,
  "layers": [
    {
      "layer": 0,
      "buttons": {"01": "0x00D4"},
      "dial": {"ccw": "0x00D9", "cw": "0x00DA"}
    }
  ]
}
```

Also available as [an example config](../examples/vertical-scroll-browser-back.json). Omit `buttons` for wheel-only changes or `dial` for Back-only changes. No gesture/force-scroll changes are needed. Acceptance: on the selected layer, turn each direction in a scrollable page, check vertical axis/direction, then press 01 in a browser with navigation history and confirm Back, not Backspace.

### Hold M1 + M2 to activate another layer temporarily

**Not yet a verified, ready-to-apply recipe.** Intended representation: one combo on the source layer, selecting M1 and M2, `tap = none`, `held = layer.momentary(target)`. For a confirmed target wire layer 2, the held code is `0x5222`; this does not resolve what the user means by “second layer.”

Before building a config:

1. Confirm source and target wire layers; do not substitute `active_layer` for a hold action.
2. Verify M1/M2 combo mask encoding from device/Launcher evidence. `48` is a candidate **only if** bits 4 and 5 are confirmed to select these columns; it is not established by the catalog.
3. Inspect the chosen combo slot without overwriting another binding. The CLI has no slot-count query; a timeout is not an empty slot. Empty-slot creation remains untested and may be unavailable.
4. Review overlap with individual M1/M2 actions and other combos. Do not alter target-layer bindings or use `transparent` blindly to resolve release behavior.
5. After an approved change, test M1 alone, M2 alone, both held, release each in both orders, and a short simultaneous tap. Confirm return to the prior layer and no stuck modifier/layer. The full hold/release path remains physically unverified.

### Single-button tap versus hold

A tap-hold record alone is insufficient. The same layer/button must have the `tap_hold.activate` binding (`0x7E29`) **and** a targeted record with the desired `tap`/`held` codes. Use `create: true` only for a positively confirmed empty record; otherwise edit the existing record. Confirm short tap, long hold, release, and preserved bindings. Deleting the record does not automatically restore the button's former binding; include an explicit replacement binding when removing activation.
