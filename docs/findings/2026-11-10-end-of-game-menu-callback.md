# End-of-game screen callback (Quick Play buzzer crash)

## Question and method

What is the unresolved target of the Quick Play buzzer crash recorded in
[2026-11-02 Codegen and save review](2026-11-02-codegen-and-save-review.md)?
Reproduce with a played Quick Game, read the runtime log, then inspect the
referencing data and the original body in the retail XEX.

## Evidence

- [CONFIRMED, runtime log] A played Quick Game (1-minute halves) reaches the
  final buzzer and the achievement write (`Achievement unlocked: 00000051`).
  `User.USR` and `Game Records.REC` are rewritten (post-game autosave). Fourteen
  seconds after the achievement line the runtime logs `[FATAL] Call to invalid or
  unregistered function at guest address 0x84C945E8`.
- [CONFIRMED, image] The only aligned reference to `84C945E8` is
  `.rdata:8215A7F8`, inside the event list `{1, 84C945E8, 0}` at `8215A7F4`.
  That list is event 1 of the event map at `8215A83C`
  (`{1 -> 8215A7F4, 4 -> 8215A80C, 6 -> 8215A824}`), which is the `+0x08` event
  map of the screen descriptor `SlideOnNav_PauseMenu_EndOfGameBase` (`8215A8E0`).
  Kind 1 entries are called as `fn(menu)` (see
  [2026-11-10 Menu screen system](2026-11-10-menu-screen-system.md)). No
  generated code builds the address with `lis`/`addi`.
- [CONFIRMED, image] Original body `[84C945E8,84C94600)`: `lis r11,0x85D1`,
  `li r10,0`, `addi r11,r11,-0x62DC` (= `85D09D24`), `stw r10,0(r11)`,
  `stw r10,4(r11)`, `b 84C7B900`. The word before it is an unconditional branch
  (`b`) ending the previous entry; `mflr r12` at `84C94600` begins the next
  function.
- [CONFIRMED, image] `84C6E378` has the same kind of reference: a lone `blr`,
  the only target of the event list `{3, 84C6E378, 0}` at `82147490`, which is
  event 6 of the event map at `821474A8` of `LegacyMainMenu` (`821474C0`). The
  word before it is an unconditional branch; zero padding follows. It is
  structurally verified, not runtime-observed.
- [LIKELY] These two are the only unregistered targets of this shape. A scan of
  every referenced `{small kind, code pointer, ...}` record in `.rdata`/`.data`
  (3,363 records, which include these event lists) found only these two, but
  it ran against an older codegen registry of the same XEX, not this
  repository's.

## Correction and validation

Register the original 24-byte body and the 4-byte sibling in
`pointer_funcs.toml`. Nothing is stubbed or bypassed; the guest code runs as shipped.

- On this repository's generation, with
  [End-of-half switch table](2026-11-17-end-of-half-switch.md) also applied
  (without it the game stops at halftime first): a played Quick Game goes
  final buzzer -> post-game autosave -> End of Game menu -> Quit -> Quick Game
  screen. The log has 0 fatal lines and no unregistered-call line, and the
  process closes cleanly.

## Limits

The record scan has not been re-run against the current generated registry.
Other indirect targets remain unaudited.
