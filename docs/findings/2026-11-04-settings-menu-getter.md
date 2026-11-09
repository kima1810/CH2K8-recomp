# 2026-11-04: Settings menu getter registration

Updated 2026-11-08 with the twin getter `84CA8B60`.

## Question

Why does the game terminate after changing a setting and backing out of the
settings menu?

## Evidence and method

- `ch2k8_003.log` and `ch2k8_005.log` both end with `Call to invalid or
  unregistered function at guest address 0x84CA8998`. The user reports the crash
  on every attempt after changing settings and backing out.
- Windows records `C0000409` in `ucrtbase.dll`, consistent with runtime fatal
  termination. The minidump holds no guest memory.
- The target lies in the gap `[84CA8998,84CA89A8)` between `sub_84CA88F8` and
  `sub_84CA89A8`. A live `ReadProcessMemory` of the loaded image, checked against
  the known `7D8802A6` at `84CA88F8`, gives a complete four-instruction body:
  materialize `8565CC80`, `lwz r3,0x20C(r11)`, `blr`.
- A scan of the loaded image finds one raw reference, at `8555F4D0`, inside the
  list `[8555F4C8,8555F4E4)`. Its other six entries are registered. The preceding
  word is 7, which matches the entry count; the format is not decoded.
- The adjacent `sub_84CA88F8` stores to offset 524 (`0x20C`). Whether it uses the
  same object is inferred, and the specific setting is not identified.

## Correction

Added `0x84CA8998 = { size = 16 }` to `pointer_funcs.toml`. The original load and
return are preserved. No replacement value or game logic bypass is introduced.

## Validation

- Native generation, compilation, and link: **PASS**.
- The generated mapping now includes `84CA8998` with the four original instructions.
- Generated field-load execution check: **PASS**.
- In-game retest: **PASS**. The user confirms the crash is fixed. Other
  unregistered callbacks may remain.

## 2026-11-08: Half-length getter

- `ch2k8-20261108-191915-7204.log` fatals with `0x84CA8B60` after the user
  changes the half length. Windows again records `C0000409` in `ucrtbase.dll`.
- A live memory read of a probe launch (separate user-data folder) gives
  `lis/addi 8565CC80`, `lwz r3,0x210(r11)`, `blr`; `84CA8B70` is registered next.
- An image scan finds one reference, at `8555F52C`. No other slot around it is
  missing. The function is the twin of `84CA8998`, beside `sub_84CA8AC0`, and
  reads the neighbouring field.
- The same scan lists 51 unregistered pointer-list targets at function gaps
  across the image. Most resemble compiler tables (this-adjust thunks,
  save/restore helpers); none is registered without separate review.

Correction: `0x84CA8B60 = { size = 16 }`. The settings-getter test is now
parametrized over both getters.
