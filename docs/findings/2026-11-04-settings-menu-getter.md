# 2026-11-04: Settings menu getter registration

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
