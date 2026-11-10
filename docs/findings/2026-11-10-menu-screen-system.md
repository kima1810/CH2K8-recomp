# 2026-11-10: Menu screen system

## Question and method

How does the retail menu system define a screen, open it from a 2K Nav item,
fill its lists and option rows, and flip between pages? Retail USA XEX
(SHA-256 `71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`).
Static reads of `.rdata`/`.data` and headless Ghidra 12.1.4 + Xenon360
decompiles, plus the UI IFF banks read from a retail disc. Items marked
"observed in testing" were also exercised at runtime by inserting records
into the live menu data. 664 screen descriptors were scanned.

## Opening a screen from a nav item

- [CONFIRMED] `sub_847DFB10` activates a nav item: it calls item `+0x44`
  first (a zero return swallows the press), then dispatches on the item type.
- [CONFIRMED] Type `0xC` opens a screen: `sub_847E3558(menu, item+8)`, where
  item `+8` is a screen descriptor pointer (Legacy Home -> `LegacyMainMenu`,
  `.rdata:821474C0`). It then plays the menu-select cue.
- [CONFIRMED, observed in testing] An inserted copy of a type-`0xC` record with
  its descriptor replaced opens that descriptor with no callback. For type `0xB`
  records `sub_847DFB10` skips the activation callback, so a copied `0xB` record
  does not open its target.
- [CONFIRMED] `sub_847E3558` -> `sub_847E3088` (pop back to the right stack
  level) -> `sub_847E32E8` (push). A push fires events 5 (exit previous), 2,
  1 (create) and 3 (enter) on the menu object's screen stack (`+0xE4` depth,
  descriptors from `+8`). Event 3 loads the layout and fires event 4 (populate).
- [CONFIRMED, observed in testing] The off-season 2K Nav is
  `SlideOnNav_ABLMenu_Main` (`.rdata:82159E38`); items inserted there follow
  the same rules.

## Screen descriptor

A screen is a code descriptor in `.rdata` (0x50 stride region) plus a named
layout (an LAYT + SCNE pair of the same name in an IFF bank).

| Offset | Meaning (verified on `CoachMenu_CoachCarouselMenu`, `.rdata:8213D478`) |
| --- | --- |
| `+0x00` | `.data` runtime block |
| `+0x04` | name (UTF-16) |
| `+0x08` | event map: `{event id, -> list of {1, callback}}`, zero-terminated |
| `+0x0C` | handler: `847DC790` list (314 screens), `847DC348` plain (225), `847DCC78` SlideOnNav (71), `847DC530` option items (32) |
| `+0x18` | hint bar: triples `{button id, glyph string id, label string id}` |
| `+0x1C`, `+0x40` | option-item screens: item array, item count |
| `+0x20` | title bar: `{title string id, description string id}` |
| `+0x2C` | list panels: up to 4 x `{panel record, x, y, w, h}` (floats, screen space) |
| `+0x30` | layout name (`spreadsheet`, `options3`, `teamprofile`, `main_legacy_a`, ...) |
| `+0x38` | layout-node binding table (non-list screens, see below) |
| `+0x3C` | non-zero: the engine adds the 2K Nav hint |
| `+0x44` | `0x5E018C` on 639 of 664 descriptors |
| `+0x48` | flags, below |

- [CONFIRMED] Title, description, hints and column headers are English.iff
  string ids, copied into the instance at event 3.
- [CONFIRMED] `+0x48` flags (histogram `0xA0` x233, `0xA8` x176, `0x28` x66,
  `0x80` x56, ...): bit 31 = nav anchor (event 1 records the stack depth in
  menu `+0xE8`; 2K Nav jumps through `sub_847E3558` pop back to it first);
  bit 27 = play the menu-select cue on event `0xB` if the event map handles it;
  bit 28 = the same for events `0xC`/`0xD`.
- [GUESS] Bit 29 gates a per-controller state lookup (`sub_84760C88`) during
  event 6 (input): most likely "only the owning pad drives this screen".
- [CONFIRMED] Instance `+0x44C` runtime flags: `0x2000000` animated transition
  (`sub_847E2F38` / `sub_847E2E18`), `0x8000000` set/cleared by events
  `0x2B`/`0x2C`, `0x10000000` mutes menu sounds, bit 31 reverses page order.

## Layouts and chrome

- [CONFIRMED] Layouts are composed from shared templates in `global.iff`:
  `template_titlebar`, `template_helpbar`, `template_menulayout`,
  `template_navigation`, `template_quicknav`, `spreadsheet`,
  `menuhelp_tip_window`, plus SCNE art (`titlebar`, `bar_selected`,
  `bar_unselected`, `sliderbar`, `toggle_onoff`, `checked`, cursors).
- [CONFIRMED] Screen-specific layouts: `legacy.iff` (51 LAYT), `frontend.iff`
  (23), `frontend_sync.iff` (43). Reuse is heavy: `spreadsheet` 29 screens,
  `options3` 18, `options` 16, `teamprofile` 15.
- [CONFIRMED] Title bar, help bar, frames, background and the 2K Nav hint are
  drawn by the engine from those templates and filled from descriptor data:
  there is no per-screen chrome art. A descriptor that points at a stock layout
  gets the stock chrome and its transitions.
- [CONFIRMED] LAYT records are small binaries with hashed names
  (`spreadsheet` 192 bytes, `template_titlebar` 672). Existing community
  tooling decodes SCNE/TXTR; LAYT has no public decoder.

## Lists: rows are pulled through bindings

- [CONFIRMED] A binding record is `{fn, u32 kinds}`: the low 16 bits of the
  second word are the argument count, nibbles the argument kinds
  (`sub_847E7330`): 0 literal (from the binding's tail), 1 panel, 2 cell,
  3 row index (panel `+0x8C`), 4 column index (`+0x90`), 7 row count (`+0x58`),
  9 column count (`+0x60`), 10 row item (`+0x3C[row]`), 11 column item
  (`+0x40[col]`), 12 cell data, 13 menu. Called through `sub_847E78C0`
  (up to 4 arguments).
- [CONFIRMED] List panels sit at instance `+0xD8` (0xDC each, up to 4), set up
  by `sub_847EC140` from the descriptor's `+0x2C` entries: `+0x50` panel record,
  `+0x54` -> table definition, `+0x94` selection, `+0x7C`/`+0x78` counts,
  `+0x3C` row items, `+0x40` column items.
- [CONFIRMED] Table definition (carousel: `.rdata:8213C03C`): `+0x08` ->
  `count()` binding, `+0x0C` -> `item(row)` binding, `+0x24..` column records,
  zero-terminated. Carousel: `count = sub_84BCAC30()` (end minus start of a
  static array), `item(i) = sub_84BCAC48(i)` (array at `85B813C8`, stride 0x14).
- [CONFIRMED] Column record: `+0x00` flags | width (px), `+0x34` cell callback
  `(out_text, row_item)` returning a string id or formatted text (e.g.
  `sub_84C3EF80`: row -> coach name), header string after it.
- [CONFIRMED] `sub_847EC3A8(panel)` refreshes a panel (re-runs count, clamps the
  selection, relays out). A list needs no row array in game memory: it supplies
  count/item/cell functions, and row items may be plain indices.
- [CONFIRMED] Focus and selection are engine-owned. The list handler maps pad
  events `0xC`-`0x11` (move/page) and `0x13`-`0x16` (shoulders) to the list
  widget (`847EE9F8`, `847EF0C0`, ...); `84C3AD90` reads the selection. Button
  events (`0xA`, `0xB`, `0xC`, `0x12`, ...) reach the screen's event map. Menu
  sounds come from `sub_847DD140`. Pop-ups: `sub_847CDD88(menu, {string id + args}, -1)`.

## Non-list screens: layout-node bindings

- [CONFIRMED] `LegacyMainMenu` has no list panels (`+0x2C` = 0). Its values
  come from a layout-node binding table (descriptor `+0x38` -> `85547490` ->
  `85546910`): entries `{kind, node-name hash, callback, index}`, 0x18 each.
  Groups: header fields (13, `84C6EAB0`), schedule (`84C6F4C8`), standings
  (`84C6F8D8`), recruiting (`84C6F220`), top players (`84C6F140`), injuries
  (`84C6FB50`), interest (`84C70208`), drills (`84C6F3E8`). The values these
  read are in [2026-11-10 Legacy mode internals](2026-11-10-legacy-mode-internals.md).

## Option-item screens

- [CONFIRMED] Handler `847DC530` with layout `options` is item-based like the
  2K Nav: descriptor `+0x1C` = item array (`.data`, 0x5C per item), `+0x40` = count.
- [CONFIRMED] Item: `+0` type (5 toggle, 7 value/enum, 4 slider), `+4` -> label
  string id, `+0x0C..+0x24` seven callbacks `{max, min, get, dec, inc,
  text(out), width(out)}`, `+0x34` visibility. Example, Shot Clock: max 1, min 0,
  get/inc/dec on a global, text from a two-entry Off/On table (`.data:84F7562C`).
- [CONFIRMED] Settings block at `8565CC80` (`+0` = current mode, which drives
  the per-mode visibility callbacks); Injuries `8565CC98`, Fatigue `8565CC9C`
  (getters `84818388` / `84818398`).
- [CONFIRMED] The Legacy creation screen is an option-item screen:
  `GameModeMenu_FranchiseMenu` (`.rdata:821440E8`, items `.data:85543BB8`,
  9 items): Number Of Users (7), Half Length (7), Simulated Half Length (7),
  Injuries (5), Player Transfers (5, `84BD4A50`), Players Leave Early (5,
  `84BE1740`), Popup Help (5), Customize Conferences (5), Customize Schedule (5).
  `OptionsMenu_GamePlayMenu` has 18 items, including Fatigue, Injuries and
  Team Unity.
- [CONFIRMED] Pad mapping on option screens: `0xC`/`0xD` value left/right
  (`847E2308` / `847E2200`), `0x13`/`0x14` move, `0x15`/`0x16` value,
  `0x25`-`0x28` item refresh.
- [CONFIRMED] `options3` is a list layout (list handler `847DC790`; Team Stats,
  Customize Schedule and Save Legacy use it), not the toggle widget.

## Multi-page cards

- [CONFIRMED] Each page of a card is its own descriptor. `ConferenceCardMenu`
  (host; pushes the first page with `sub_847E3420`) has 7 pages (Information,
  Standings, Team/Individual Leaders, Top Players, Historical Champions, Awards,
  Tournament); page table `.data:85540BE0` = `{page descriptor, tab label string
  id}` x 7, count 7 at `855400AC`. `CoachCard_*` (Records, Achievements, Goals,
  Notes) are four descriptors on the `coachcard` layout.
- [CONFIRMED] A page installs a page strip by writing its pointer to instance
  `+0x448` on open (`sub_84C458D8`, in the event maps of all 7 conference pages;
  strip `.data:855400A8` = `{current index, count, -> table}`).
- [CONFIRMED] The input handler `sub_847DB168` (event 6) then flips pages:
  next `sub_847D9240`, previous `sub_847D92F8`; both wrap the index, play the
  increment/decrement cue and swap screens with `sub_847E3418(menu,
  table[i].descriptor)`. Screens without a strip receive events `0x10`/`0x11`.
  The header shows the tab label and page count (`sub_847DA920`, `sub_847E6A00`).
- [LIKELY] The physical page button comes from a runtime-filled mask table
  (`8572A61C..8572A66C`, read only by `sub_847DB168`, zero in the image).

## Host callbacks for new screens

- [CONFIRMED] In the pinned ReXGlue SDK, `FunctionDispatcher::AllocateThunk(host_fn,
  caller)` returns guest addresses from a 64 KB reserve past the end of game
  code (`code_base + code_size .. +0x10000`, `function_dispatcher.cpp`),
  registered in the table indirect calls use. Such an address cannot collide
  with a game function. Checks before use: at or past the end of `.text`,
  outside every `.pdata` range, and `GetFunction(addr)` returns the thunk.

## Limits

Static except where marked. Descriptor `+0x44`, the `.data` runtime block and
flag bit 29 are not fully named. How the row-list widget lays out more than
four panels, and the exact page-flip button, were not traced.
