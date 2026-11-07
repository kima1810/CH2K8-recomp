# Native GPU progress waits

The audited retry loop in `sub_84DDA4D0` repeatedly reads the guest GPU progress
counter. Live sampling found it consuming CPU while waiting for the graphics
command processor. The observed counter is `FFCA3000` (physical `1FCA3000`).
This change replaces sustained spinning with native waits; it does not reduce
resolution, lighting, geometry, textures or shader quality.

## Implementation and invariants

After 64 retries, a host helper captures the SDK notification generation and
rechecks both words used by the original comparison: the read counter and the
device write cursor at offset 10908. If either changed, it returns immediately.
Otherwise it requests a wait of at most one millisecond, then returns to the
original guest checks. Windows scheduling can make the actual wait longer.
Original completion, cancellation, device flags, counter arithmetic, wraparound
and timeout decisions remain in the guest function. No counter is fabricated.

The SDK increments a generation and wakes sleepers after its existing primary
read-pointer writeback and `EVENT_WRITE_SHD` store. Windows uses
`WaitOnAddress`/`WakeByAddressAll`, with no notification mutex owned by a guest
thread. Capturing the generation before rechecking the words closes the
notification/check race; unrelated notifications merely trigger another check.
No GPU fences, barriers, query results or packet ordering are removed.

The helper validates aligned ordinary RAM and committed readable host mappings.
MMIO, guarded, inaccessible and executable pages retain polling. The versioned
exports are resolved dynamically from the GPU DLL, which is retained during use.
Missing exports disable native waiting for that scope. The complete original
guest body is SHA-256 pinned by `tools/gpu_wait_codegen.py`; unknown changes
require re-audit instead of silently applying the transformation. SDK preparation
also rejects unreviewed source edits and is idempotent.

`--no-ch2k8_native_gpu_wait` restores polling. Diagnostic timing is opt-in via
`--ch2k8_gpu_wait_stats`; normal play does not collect wait durations or thread
CPU samples. Rebuild the prepared SDK as well as the executable to enable the
notification exports.

## Measurements

Same-build D3D12 RTV-extent runs, seconds 120–180:

| Mode | Mean process CPU cores | Guest submissions | Median interval | 95th percentile |
|---|---:|---:|---:|---:|
| Polling | 2.775 | 2,684 | 17.759 ms | 34.931 ms |
| Native wait | 2.234 | 3,474 | 16.681 ms | 19.532 ms |

This is 19.5% less process CPU use. The demo selected different arenas, so the
submission increase and interval changes are observations, not a controlled FPS
uplift. Guest submissions are not unique displayed frames. The stronger direct
attribution is the waiting thread's diagnostic bins: 44.83 seconds blocked over
60.53 seconds, with 12.61 seconds of CPU time (20.8% of one core). Notification
counts indicate progress-generation changes, not proven guest completion.
Gameplay readbacks remain rendered at 1280x720; the optimized run visibly shows
players, court, crowd and HUD.

Unrestricted run directories under `port/out/render-diagnostics`:
`20261103-200315-057-gpu-d3d12-rtv-extent` and
`20261103-200636-849-gpu-d3d12-rtv-extent`.
Both use executable SHA-256
`7a6a867b3c97c3fea7b751a622d882269bab96ba2fa39a4bf3e4f9ef1c27fcf1`
and GPU DLL SHA-256
`cd37a4814886041c6fa0be598cb10e5dc8b52fb1e8aec1381c4b8cb62cea9470`.

The initial affinity experiments were invalid: the SDK resets process affinity
during startup. They are excluded. The benchmark now reapplies a requested mask
and records the effective mask in every CPU sample. Summaries verify the mask
over the selected window rather than trusting the launch request.

## Validation

Tests cover concurrent notifications and early notifications, bounded waits,
missing exports, disabled optimization, changed read/write words, MMIO and
inaccessible memory, emission idempotence and refusal of unknown guest bodies.
Complete-function comparisons cover 16 cases including counter wraparound,
pending producer updates, device flags and cancellation, comparing the complete
PPC context and a 1 MiB RAM image against the original function.

This reduces CPU contention and power spent polling. It does not establish a
stable 60 FPS result or performance on older physical hardware. Geometry and
rendering costs remain and require further measurement.
