# End-of-half switch table (Quick Game halftime crash)

## Question and method

Why does a played Quick Game close without a log line at the end of the first
half? Reproduce with 1-minute halves, CPU vs CPU, on the current generation
(`control_flow.toml`, `inline_switches.toml`), read the Windows crash dump, and
check the referenced table in the retail XEX.

## Evidence

- [CONFIRMED, crash dump] The process exits at the end of the first half with
  no fatal or error line in the runtime log. The dump records exception
  `0xC000001D` (illegal instruction) in `sub_84C67120`.
- [CONFIRMED, generated code] The generated `bctr` switch at `84C67838` in
  `sub_84C67120` has only `case 0`; every other index reaches
  `__builtin_trap()` ("Switch case out of range").
- [LIKELY] That trap is the fault: it is the only one-case trap switch in the
  generated code, and the dump symbolizes into the same function. The faulting
  instruction was not matched to that exact site.
- [CONFIRMED, image] The table at `84C6783C` follows the `bctr` (`lis r12,-31546`,
  `addi r12,r12,30780`, `rlwinm r0,r3,2,0,29`, `lwzx`, `mtctr`). In the retail
  XEX it holds 12 words: 4 x `84C6789C`, then 8 x `84C6788C`. The 13th word is
  `rlwinm r11,r24,1,0,30`, the first instruction of the code at `84C6786C`.
  The index is checked only for `< 0`, as in the 12-case sibling at
  `84C67D74` (`sub_84C67D10`), which has the same 4/8 shape and is already listed.
- [CONFIRMED, exporter source] `ghidra/ExportInlineSwitches.java` accepts a
  table only when the pointer array ends exactly at the first case body (line
  49), and here one instruction (`84C6786C`) sits between them. 43 of the image's 1,846
  inline tables have that shape.
- [CONFIRMED, image vs generated code] After regeneration, every inline table in the image was compared
  with the generated switch (same site idiom as the exporter; table length =
  consecutive aligned `.text` targets up to the first forward case body,
  cross-checked against the `cmplwi`/`bgt` bound where one exists, 949 sites).
  1,846 of 1,846 sites match: no switch recovers fewer cases than the image,
  and no generated target differs. One bound disagreement (`84AA9740`) is a
  range test on another value, not the selector, which is set to 0-3 just
  before the table. Run against the pre-fix function, the same comparison
  reports `84C67838` as 1 of 12.

## Correction and validation

Add the table to `inline_switches.toml` (`address = 0x84C67838`, `register = 3`,
the 12 labels above). No stub, no bypass.

- Generation `[complete]`, `tests/test_audit_inline_switches.py` and
  `tests/test_fix_codegen.py` pass (its numeric test is skipped without
  `clang++` on the path).
- Runtime, same save and settings: first half -> "Player of the half" ->
  Halftime Adjustments -> second half -> final buzzer -> post-game autosave
  -> End of Game menu -> Quit -> Quick Game screen -> clean close.
  0 fatal lines, no unregistered-call line, no crash dump. Save diff: only
  `User.USR` and `Game Records.REC` (+ headers) changed.
- This run also reaches the End of Game menu callbacks registered in
  [2026-11-10 End-of-game menu callback](2026-11-10-end-of-game-menu-callback.md),
  on the current generation.

## Limits

One Quick Game, one team pairing, 1-minute halves. Which values of the switch
index occur in other modes was not traced.
