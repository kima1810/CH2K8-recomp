# 2026-11-01: CPU vertex-work bottleneck and proven native RAM stores

## Fresh evidence

**[CONFIRMED]** D3D12 ROV run `20261101-130343-293-gpu-d3d12-rov`
records a 56.932 ms median guest submission interval (58.210 ms p95) between
120 and 180 seconds. These are guest submissions, not unique displayed FPS.
The native readbacks contain rendered scenes. Average process CPU is 3.113 cores.

On guest worker thread 24212, three routines account for 57.463 seconds of
instrumented wall time in that 60-second window:

| Address | Calls | Work units | Wall seconds | ns / work unit |
|---|---:|---:|---:|---:|
| `84723778` | 475,946 | 113,064,892 | 24.587 | 217.459 |
| `84723CC0` | 237,973 | 54,963,379 | 12.345 | 224.611 |
| `84724930` | 238,041 | 2,091,403 | 20.531 | 9816.811 |

Checksummed PDB/source attribution on 300 guest-worker IP observations finds
115 in the first routine, 65 in the second, and 110 in the third. Approximate
source-operation attribution includes 135 `stvlx`, 37 packing, 24 `lvlx` and
23 unpacking observations. These are sampling leads, not exact cycle counts.
**[LIKELY]** This CPU translation work is a principal limit in the sampled
scene; GPU activity alone does not establish that GPU capacity is the cause.

## Rejected approaches

Two versions of per-store RAM validation were tested and left disabled. The
first added outlined-helper overhead. The second inlined the fast checks but
saved only about 1–3% within the routines, without a whole-run cadence gain.
Isolated compiler exception-mode, local-context and fused-math timing probes
also provided no meaningful benefit. No compiler or floating-point behavior
change is shipped from those probes.

## Per-job span proof

`tools/prove_vector_store_ranges.py` follows scalar register bounds and low-bit
alignment through guest labels and branches. Unknown operations become unknown;
increasing backedge bounds widen to unknown. It rejects unsupported control
flow, calls that could clobber the output base, and unstable output bases.

**[CONFIRMED]** For `84723778` and `84723CC0`, all 16 partial-store sites use a
stable descriptor+116 output pointer and offsets at most 40944, aligned to four
bytes. A 40960-byte writable span covers every possible store. The proof fails
closed for `84724930`, which keeps byte stores.

The optional RAM variant validates that entire span once per call. It excludes
device windows, alias boundaries, address wrap, protected/uncommitted memory,
executable memory, and overlap with the register context or helper scope.
Eligible stores use explicitly byte-swapped 32/64/128-bit native instructions.
Each store stays within its original 16-byte block and page. If a page becomes
write-watched after validation, the native write faults and retries through the
runtime's existing mechanism, like its native `stvx` implementation. Ineligible
jobs retain the original ordered volatile byte path.

The transform retains all older variants, upgrades v1–v3 sources to v4, restores
original bodies before regeneration, and is idempotent. Generated sources and
game data remain local.

## Paired runtime result

Run `20261101-135743-275-gpu-d3d12-rov` randomly chooses unchanged byte stores or
the proven native variant per call, within the same game process. Between
120 and 180 seconds:

| Address | Byte ns / work | Native ns / work | Reduction |
|---|---:|---:|---:|
| `84723778` | 236.958 | 192.620 | 18.7% |
| `84723CC0` | 236.354 | 193.265 | 18.2% |

There are 1,342,319,008 widened store instructions and no byte fallbacks in
those sampled native jobs. The third routine retains byte stores. Whole-run
median submissions are 56.633 ms (60.547 ms p95), with both variants mixed.
Both native readbacks are nonblack; visual inspection shows players, arena,
and HUD. Different autonomous runs do not lock teams, camera, or scene timing.

The optimized-only run `20261101-140135-752-gpu-d3d12-rov` records 51.346 ms
median submissions (59.109 ms p95), 1140 submissions in the same 60-second
window, versus the initial baseline's 56.932 ms and 1052 submissions. That is
9.8% lower median submission time and 8.4% more submissions. Native images show
correctly rendered demo gameplay. Scene differences prevent treating this as
an exact causal whole-game FPS result; the randomized routine measurements
above isolate the implementation effect more directly. The verified path is
now enabled by default, with `baseline` available as a fallback.

**[CONFIRMED]** Consistent high frame rate is not achieved: even this improved
sample remains around 51 ms per guest submission. `84724930` remains an
unoptimized native-store candidate; packing/unpacking, partial loads, and
remaining translated vector arithmetic also need further work. Replacing a
graphics API alone has not removed this CPU-side cost.

## Validation

The complete routine harness makes 336 context-and-memory comparisons against
the corrected original bodies, covering all four optimized variants and
bounded/random descriptors. Standalone store checks cover 49,152 offsets,
source overlap, RAM/device boundaries, mapped/private RAM, page protections,
prepared-span bounds, and write-watch retries. Range tests exercise unknown
values, partial writes, backedges, and the exact two locally proven functions.
Both normal and dual-backend Release builds succeed.
The suite passes 82 tests, with one environment-dependent skip.

The subsequent [guarded-vector finding](2026-11-01-guarded-vector-output.md)
extends widening to the third routine using checked reload values, without
assuming that guest-stack contents remain stable. Its newer tests and controls
supersede the earlier third-routine limitation above.

`--ch2k8_ram_store=baseline|optimized|compare` controls this path independently
within the existing combined pack/unpack/store optimization. Opt-in hot logs
add `ram_optimized`, native instruction counts and fallback counts; the summary
continues to accept older CSVs. No profiling is enabled in normal play.
