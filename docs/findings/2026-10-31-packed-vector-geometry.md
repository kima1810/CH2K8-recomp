# 2026-10-31: Packed vector translation and pre-run-out geometry

## Question and evidence

The user reports a black flash before player run-outs and associates it with
the previously visible stretched/black polygons. The timing and visual symptom
are user-observed. Their exact rendering cause is not yet runtime-confirmed.

Inspection found a separate, reproducible CPU translation error in the pinned
SDK's `vupkd3d128` type 6 (`NORMPACKED64`), used at 163 generated instruction
sites, and its matching `vpkd3d128` pack at 89 sites. The earlier fix corrected invalid 44-bit shifts but did not validate
the complete instruction semantics.

## Method and correction

Compare the emitted code with Xenia's `EmitULONG_4202020` implementation and
its SIMD constants in `x64_seq_vector.cc` and `x64_emitter.cc`. Xenia's word
layout differs from ReXGlue's; the test oracle explicitly reverses word order
at its boundaries. The test's adapted Xenia oracle retains its BSD notice.

- Read packed bits from the guest vector's last 64 bits (ReXGlue `u64[0]`),
  rather than its first 64 bits (`u64[1]`).
- Sign-extend the three 20-bit components and construct biased float bits
  by integer addition to `0x40400000` (3.0f), rather than numeric int-to-float
  conversion. The fourth component adds to `0x3F800000` (1.0f).
- Write guest XYZ to host lanes 3, 2, 1, and W to host lane 0.
- Match Xenia's quiet NaN result for the signed minimum component `-524288`.
- Snapshot the source before writing, preserving correctness when source and
  destination are the same register.

For a zero packed input the old translation returned four numeric zeros;
the corrected result is guest `(3.0, 3.0, 3.0, 1.0)`. The difference is
**[CONFIRMED]** by the independent SIMD test. Geometry consuming such vectors
can be corrupted; attribution of the user's exact black polygons is **[LIKELY]**
until a visual retry validates the change.

The persistent correction recognizes the complete exact pinned emission block;
unexpected shapes are left untouched, and repeated correction is idempotent.

The matching pack path also incorrectly performed numeric float-to-int
conversion in reversed component order. Correct it to clamp biased floats,
extract their mantissa bits, and place packed output in the requested half.
All 89 observed pack sites use a 64-bit merge with shift 0 or 2; correction
is deliberately limited to those exact shapes. NaNs select the lower bound,
matching SIMD max/min behavior. Other destination bits are preserved.

## Validation

Numeric checks cover 3,456 combinations of component boundaries and all 16 W
values, plus 10,000 deterministic random vectors, with poisoned unused halves.
Both aliased and distinct source/destination registers match the Xenia SIMD
oracle bit for bit. Zero-input expected constants are independently asserted.
Pack tests also cover those vectors and unpacked results, plus special float
values including infinities, quiet/signaling NaNs, saturation edges and signed
zero. Both observed merge positions preserve the unmodified destination half.

- Native generation, compilation, and link: **PASS**.
- All **163 unpack** and **89 pack** instruction sites match the corrected
  exact emission in a generated-output check.
- Independent SIMD comparison and expanded callback execution test: **PASS**.
- Full regression suite: **29 passed, 1 skipped** (absent PS3 dump).
- Inline-switch audit: **1,762 compared**, zero truncations/disagreements.
- Generated fatal fallbacks: **0**.
- Latest callback family: **12/12 registered**.

## Separate crash evidence

Log 009 terminates at 13:20:58 with another missing indirect target,
`8471B108`. Original instructions verify a one-instruction tail branch to
already registered `84718AE0`, followed by zero padding. This is separate
from the geometry translation error; correcting rendering does not register
missing callbacks.
The 12 contiguous eight-byte callback slots `[8471B0B8,8471B118)` contain
seven further missing entries. Their complete bodies mask r3 to a byte and
tail-call, or simply tail-call; all destinations already exist. Register all
eight missing entries and extend the generated-body calling-convention test.
Only `8471B108` has been observed at runtime.

## Open questions

Visual confirmation of the black-flash and polygon fix, successful gameplay,
additional translation errors, and performance profiling remain outstanding.

Primary source inspected locally:
[Xenia vector backend](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/src/xenia/cpu/backend/x64/x64_seq_vector.cc)
and [constants](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/src/xenia/cpu/backend/x64/x64_emitter.cc).
