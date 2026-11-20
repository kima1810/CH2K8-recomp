# PS3 roster conversion to Xbox

The US retail PS3 and Xbox roster bodies can be related by a lossless
transformation for the stock files and the edited save examined here. The
forward transform produced all 4,026,784 bytes of the retail Xbox ROST
component from the PS3 reference. Applying the inverse to the converted
custom save recovered all 4,061,184 PS3 payload bytes.

## Record layout

Offsets in this document are relative to the decoded ROST body, without the
four-byte big-endian save length. Per-player offsets are relative to the
editor window that begins 16 bytes before the engine's player anchor.

| Record | PS3 stride | Xbox stride | Count |
| --- | ---: | ---: | ---: |
| Player | 308 | 316 | 5,685 |
| Player-format template | 308 | 316 | 10 |
| Team | 704 | 704 | 443 |
| Conference | 2,964 | 2,964 | 39 |

- The player window starts at `0x271AC` on both platforms in the examined
  revision. The template table pointer at `0x14` moves by `0xB1A8`. The
  following tables and the text targets move by `0xB1F8`. The eight-byte
  difference after the latter position in the stock component's total size
  comes from 32-byte alignment.
- Relative pointers are signed big-endian words. For text, the target is
  field address plus displacement minus one. The stock text pool is
  byte-identical after relocation, and native reads decode the text as
  UTF-16BE. Relocate the 40,000 leading string-index words, the player name
  fields, and header text anchors at `0xB0`, `0xB4`, and `0xB8`.
  Preserve null words `0` and `-1`.
- Rebase all 18 player links at team offsets `0x6C..0xB0` with the new
  player stride. The team, conference, coach, arena, and other table data
  after the expanded player windows retain their relative positions.
- Rotate PS3 RGBA into Xbox ARGB for all 33 four-byte team colors at
  `0x1A0..0x220` and the conference color at `+0x20`.

## Player packing

Player fields between `+0x18` and `+0x7F` share a byte layout, including
all 30 rating words. Build the packed-field map by matching each varying PS3
bit in `+0x80..+0xB5` to its unique Xbox bit signature over the 5,695
identically ordered stock player-format rows. Compare the complete byte image
with the stock Xbox component before converting a save. Require separate
executable evidence for fields the stock corpus leaves zero. The examined
inputs used a one-to-one map with 165 bits.

| Edited field | PS3 window | Xbox window | Evidence |
| --- | --- | --- | --- |
| Confidence | byte `+0x80` | byte `+0x80` | Player menu field layouts |
| Right shoulder | word `+0x84` bits 13..16 | word `+0x84` bits 5..8 | Packed shoulder field layouts |
| Eye color | byte `+0x90` bits 0..1 | word `+0x90` bits 13..14 | Player getters |
| T-shirt | word `+0x90` bits 11..12 | word `+0x90` bits 0..1 | Player getters |
| Four-bit property | word `+0x90` bits 28..31 | word `+0x90` bits 17..20 | Matching intermediate field at `+0x34` bits 0..3 |

The last property is unnamed. PS3 `0x749390` passes its high nibble to
`0x7524CC`. Xbox `0x84D0073C..0x84D00744` reads the same intermediate
nibble and inserts it at bits 17..20 of the word at engine anchor
`+0x80`. The edited input sets the high bit in 18 rows. A stock-only
comparison leaves that bit unmapped.

## FaceGen

| Field | PS3 window | Xbox window |
| --- | --- | --- |
| Coefficients A, 50 bytes | `+0xB6` | `+0xBC` |
| Coefficients B, 30 bytes | `+0xE8` | `+0xEE` |
| Coefficients C, 50 bytes | `+0x106` | `+0x10C` |
| Custom morph flag | word `+0x98`, bit 0 | word `+0x9C`, bit 26 |
| Dedicated preset | byte `+0x9F`, low nibble | byte `+0xA0`, low nibble |
| Procedural seed | word `+0x1C` | word `+0x1C` |

The coefficient tail is part of the same engine record even where it crosses
the end of the editor's biased row window. The custom flag controls whether
the runtime applies generation. Preserve it independently of coefficient
presence. This matters for saves with a nonempty coefficient block and a
clear custom flag.

For the US retail Xbox executable, `0x84738710`, `0x84738730`, and
`0x84738750` read the three arrays from engine anchor offsets
`0xAC`, `0xDE`, and `0xFC`. `0x84CF5220` and `0x84D005D0`
copy all 50/30/50 bytes through an intermediate representation.
`0x84CF9950` tests the gate, `0x84CF0C88` resolves the preset, and
`0x84CF7B28` seeds default generation. `0x8473D718` encodes
coefficients over the same ±12 range observed in the PS3 encoder.

## Validation

The custom Xbox output passed native roster validation for all 5,685 players,
443 teams, 39 conferences, and 988 uniform routes. Every uniform route matched
a unique world bank and a unique selection bank in the US retail Xbox
installation. Studio reparsed the names and ratings and matched them to
the source. The [CHMOD roster contract](../formats/chmod-1.1.md#native-roster-save)
accepted the length-prefixed payload with an existing 328-byte neutral
Dummy HDD header and staged it in an isolated profile.

These results establish data portability for the examined saves. In-game
rendering, gameplay, and hardware Xbox 360 packaging remain unverified.
