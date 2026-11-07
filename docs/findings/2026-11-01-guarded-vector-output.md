# 2026-11-01: Guarded vector output with graphics dependencies preserved

## Current bottleneck

**[CONFIRMED]** Profile `20261101-154440-171-gpu-d3d12-rov` retains the native
pixel-state optimization and the existing CPU fast paths. Seconds 120–180
record 51.069 ms median guest submissions. Three routines occupy 57.139 seconds
of measured worker wall time in this 60-second window:

| Routine | Calls | Work units | Wall seconds |
|---|---:|---:|---:|
| `84723778` | 527,310 | 125,279,950 | 21.991 |
| `84723CC0` | 263,655 | 60,914,469 | 11.333 |
| `84724930` | 263,739 | 2,317,525 | 23.815 |

PDB/source-checksummed sampling finds 126 of 129 guest executable observations
in these routines, including 62 in `84724930`. Its old `_ram_fast` suffix is
not evidence of wide stores: that body still uses byte stores because the
unguarded bounds proof fails. The extended sampler records 408 total samples
across the selected threads before the bounded game exits; it does not complete
all requested rounds. The earlier 90-observation sample is separate.

Approximate source attribution finds 29 partial-store, 21 unpack, 16 pack and
11 partial-load observations. These are instruction-pointer samples, not exact
cycle counts. The largest remaining measured routine is the third one.

## Conditional range proof

**[CONFIRMED]** Fourteen of its sixteen output-store offsets already admit the
existing scalar range/alignment proof. Two offsets are restored from volatile
guest-stack loads at `r1-356` and `r1-364`. Treating the stack contents as stable
would be unjustified: output writes can alias guest memory and other writers
are not ruled out.

The new conditional proof recognizes only a stack reload immediately followed
by its matching partial store. It emits a check **after the original load**:
the loaded value must be at most 40944 and four-byte aligned. This is an
eligibility window, not an assumed maximum for legal game data. A failure
permanently disables wide stores for the remainder of that invocation; the
loaded value and original byte-store behavior are preserved.

As before, the complete 40960-byte output span must first be ordinary writable
RAM, exclude device/alias boundaries and address wrap, and avoid overlap with
the host register context and helper scope. The two checked reloads provide
the missing range facts only on paths where widening remains enabled.
Unsupported structured control flow and branches that could reinitialize the
span after a failed check are rejected. No stack-value caching or earlier
reload is introduced.

All sixteen sites can then use the already validated endian-correct native
32/64/128-bit stores. Existing memory-watch fault/retry behavior and the
fallback are retained. The original bodies and preceding optimization variants
remain available, and regeneration/restoration remain idempotent.

## Measured routine gain

Run `20261101-155140-885-gpu-d3d12-rov` randomly interleaves native and byte
paths per invocation within one game process. For `84724930`, seconds 120–180:

| Variant | Calls | Work units | ns / work unit |
|---|---:|---:|---:|
| Byte stores | 122,992 | 1,078,928 | 10158.705 |
| Guarded native stores | 122,736 | 1,079,896 | 8395.770 |

**[CONFIRMED]** The native variant costs **17.35% less per work unit** in this
paired sample. It executes 675,334,624 widened store instructions and no byte
fallbacks. The first two routines retain their independently verified native
paths. This comparison also interleaves their older byte variants; its overall
54.584 ms median therefore is not an optimized-only frame-rate measurement.

## Graphics integration

The existing vector encodings and every guest-memory output remain unchanged.
The work still finishes through the original CPU job path before existing
graphics consumers use the data. No GPU readback, new resource format, extra
upload, relaxed coherence, or new CPU–GPU fence is introduced. The native pixel
shader optimization remains enabled for D3D12 ROV; Vulkan FSI uses the same CPU
improvement without changing its shader implementation.

**[CONFIRMED]** These routines read and write CPU-visible guest memory and
update the guest register context. A direct GPU-compute replacement would need
identified resource ownership, consumers and ordering dependencies. Those
contracts have not been recovered, so this change reduces observed CPU work
without pretending that moving a job to a GPU and reading it back is free.
Unknown engine purposes retain their address-based names.

## Normal rendering observations

With no hot-function timing, D3D12 run `20261101-155844-670-gpu-d3d12-rov`
records 25.922 ms median submissions, 38.654 ms p95 and 2191 submissions in the
60-second window. Its later native image shows coherent live play at 3:51.
Vulkan FSI run `20261101-160810-117-gpu-vulkan-fsi` records 25.613 ms median,
29.618 ms p95 and 2371 submissions; its later image also shows coherent live play
at 3:51. Neither sampled image is black.

The archived old executable, using identical GPU/runtime DLLs, records 50.512 ms
median in `20261101-160253-842-gpu-d3d12-rov`. Its matchup and executable path
differ. That large apparent improvement exceeds the isolated routine result
and must not be advertised as a controlled doubling of FPS.

An isolated same-build control uses executable
`a6cfd69935294ca349c116e2e29993a0a33395e88e4d14c183f041acf79fe8ef`
and GPU DLL `58cd1fb2a3f47626b716b932b56c7be5908dc3081a56ea16b69077edde93a00c`
for both runs. Only the new guarded-store switch changes; preceding CPU and
GPU optimizations remain enabled. Runtime logs confirm the requested values.

| Run | Guarded stores | Median ms | p95 ms | Submissions |
|---|---|---:|---:|---:|
| `20261101-161332-197-gpu-d3d12-rov` | Disabled | 50.524 | 52.088 | 1183 |
| `20261101-161900-360-gpu-d3d12-rov` | Enabled | 34.846 | 43.877 | 1754 |

Both produce nonblack rendered game images. **[CONFIRMED]** This removes the
different-executable/path explanation for that pair, and the observed cadence
is better with the new path. Teams and cameras still differ: neither the large
earlier sample difference nor this pair establishes a fixed whole-game speedup
percentage or unique displayed FPS. The randomized per-routine 17.35% result is
the stronger isolated implementation measurement. Consistent high frame rate
has not yet been achieved.

## Validation and controls

The suite passes **89 tests, one environment-dependent skip**. Both Windows
Release builds succeed. The existing 336 complete routine comparisons preserve
all register-context bytes and two MiB of guest memory. An additional 48
complete-routine comparisons force each guarded reload to unaligned,
out-of-span and wrapping values; they verify actual wide-store use before
fallback, byte fallback afterward, and identical context/memory results.
Standalone memory-watch and ordinary-RAM checks continue to pass.

The new init-only `--no-ch2k8_guarded_vector_store` disables just this third
routine's native stores while preserving the earlier CPU and GPU improvements.
The selector's independent behavior is exercised against the real production
implementation. The broader `--ch2k8_ram_store=baseline|optimized|compare`
control still applies to all three routines. The bounded benchmark exposes
`-GuardedVectorStore baseline|optimized` for isolated same-build controls.
The guarded path is enabled by default.

Frame observations are guest submissions, not unique displayed frames; demo
teams/cameras are not locked. Consistent 60 FPS, full-match completion, Legacy,
save behavior, replay/camera transitions and the reported UGA head remain
unverified by this work. No game data, generated routines or raw captures are
committed.
