# Findings index

- [2026-11-10 Archive input validation](2026-11-10-archive-input-validation.md) records extraction path checks and decoder validation.

- [2026-11-01 Native pause-menu fix](2026-11-01-native-pause-fix.md): user validates responsive menus and no black flashes with native D3D12 plus bounded ownership extents, including normal 1440p borderless launch. Automatic now uses that configuration; ROV remains a compatibility fallback.

- [2026-11-01 Menu writes and asymmetric blending](2026-11-01-menu-write-and-blend.md): proven full writes remove dynamic preservation work (3.00% incremental timed-menu reduction); exact asymmetric blending reduces the selected overlay draw 29.76%, with identical EDRAM. Aggregate blend savings and a complete severe-lag fix remain unestablished.

- [2026-11-01 Pause-menu GPU backlog](2026-11-01-pause-menu-gpu-backlog.md): user-opened 2K Nav capture and native wait attribution identify 115.2 ms median submissions, 72% graphics-thread fence waits and 96-99% GPU activity; distinguishes abnormal menu backlog from normal startup register pacing. Exact early-depth specialization preserves full EDRAM and reduces timed menu GPU work 7.25% in the same recording.

- [2026-11-01 Native depth specialization](2026-11-01-native-depth-specialization.md): exact ROV depth/stencil key, lossless interpolation packing and runtime validation; identical replay output with a further 31.69% target-draw and 7.76% median timed-action reduction against the previous native shader.

- [2026-11-01 Guarded vector output](2026-11-01-guarded-vector-output.md): two checked stack reloads unlock native stores in the third hot vector routine; paired work cost falls 17.35%, with 384 complete routine comparisons including forced fallbacks. D3D12 ROV and Vulkan FSI render correctly; an isolated same-build control records 34.8 ms enabled versus 50.5 ms disabled, with different demo scenes.

- [2026-11-01 Native pixel specialization](2026-11-01-native-pixel-specialization.md): exact draw-state variants remove generic ROV format/blend work; same-capture replay verifies byte-identical EDRAM and measures 27% less time for the leading draw, 8.8% less summed GPU work when replacing that one shader. Enabled for D3D12 ROV; same-build normal submission cadence remains about 40.5 ms with either setting.

- [2026-11-01 Proven native RAM stores](2026-11-01-proven-native-ram-stores.md): fresh profiling locates nearly a full worker core in three vertex routines; per-job bounds proof enables native stores in two routines, reducing their paired work costs 18–19%. Whole-game high FPS remains unestablished.

- [2026-11-01 Native constant state and packet decoding](2026-11-01-native-constant-state.md): cache skips 61% of shader-update requests; interleaved bulk decoding costs 71% less per word. Add native/accurate launcher choices and reliable DLL staging. Vulkan FBO black frames reproduce with optimizations disabled; Automatic selects ROV/FSI.

- [2026-11-01 Native GPU backend investigation](2026-11-01-gpu-backend-investigation.md): current Vulkan FBO/FSI and D3D12 RTV reach live demo play; roughly 55–60 ms guest submissions persist. Batching has no verified gain. Add bounded remote GPU experiments with native readbacks, CPU/AMD telemetry, profile validation and explicit comparison limits.

- [2026-11-01 Aligned vector byte stores](2026-11-01-aligned-vector-stores.md): preserve ordered volatile byte writes while removing aligned-loop overhead at 48 sites. Interleaved rendering measures another 14–15% lower routine work cost; 252 full-function comparisons and address/alias traces validate the candidate. Whole-game FPS gains remain unestablished.

- [2026-11-01 Remaining CPU hotspots and unpack](2026-11-01-remaining-hotspots-and-unpack.md): fresh 300-round sampling attributes 41% of guest samples to byte-store loops and 16% to unpacking. Bit-equivalent SIMD unpacking reduces whole-routine work costs another 3–9% against pack-only, with checksummed PDB/source attribution and 72 full-function comparisons.

- [2026-11-01 Hot functions and vector packing](2026-11-01-hot-functions-and-vector-pack.md): catalog eight recurring functions and the presentation import; bit-equivalent integer SIMD packing reduces measured whole-function work costs about 7–11% in interleaved tests. Retain baseline/compare modes and opt-in per-thread timing; full-game speedup is not established.
- [2026-11-01 Zero-argument callbacks](2026-11-01-gameplay-zero-argument-callbacks.md): optimized ROV run reaches tip-off, then exposes missing `8471B0A8`; original zero-r3 tail wrapper and sole missing sibling are registered after extending the bounded family audit to 21 entries.

- [2026-11-01 Vulkan and launcher](2026-11-01-vulkan-and-launcher.md): isolated pinned SDK enables both native APIs; explicit backend selection and a Windows launcher expose resolution, refresh and window mode. Fix Windows dependency symlink placeholders and exclusive-mode refresh forwarding; runtime validation is recorded in the finding.

- [2026-10-31 Remote renderer profiling](2026-10-31-remote-renderer-profiling.md): autonomous device captures, guest submission probes and read-only AMD telemetry establish roughly 78 ms submission intervals, normal GPU clocks, and roughly 19 ms summed action time per repeated scene batch. CPU/synchronization leads remain; AVX2 and RTV draw-extent experiments show no verified speedup.

- [2026-10-31 Performance investigation](2026-10-31-performance-investigation.md): completed 319-second user trace identifies 30.95 seconds of startup pipeline creation and later GPU-busy presentation records around 200–250 ms. These are not individual gameplay-frame times; see the subsequent remote profiling finding for refined attribution.

- [2026-10-31 Live gameplay black screen](2026-10-31-live-gameplay-black-screen.md): user confirms ROV restores live gameplay, replay and camera edits; approximately 272-second run closes normally. ROV becomes the working launcher setting; slowdown, one black player head and depth-resolve warnings remain under investigation.

- [2026-10-31 Packed vector geometry](2026-10-31-packed-vector-geometry.md): pre-run-out black flash report leads to a verified packed-vector translation error; correct source half, biased float bits, component order and overflow handling. Visual retry remains required.

- [2026-10-31 Gameplay flag callback](2026-10-31-gameplay-flag-callback.md): log 008 reaches `848E3A00`; recovered its flag-bit clearing body and audited 42 nearby code-pointer candidates.

- [2026-10-31 Scripted gameplay callback](2026-10-31-scripted-gameplay-callback.md): the next attempt stops on `84AB8CA8`; verified its global-load/tail-call body and audited 87 code-pointer candidates in the containing data region. Added the sole missing entry; gameplay retry remains required.
- [2026-10-31 Arena introduction callbacks](2026-10-31-arena-intro-callbacks.md): arena/player/crowd presentation is visible with geometry corruption; crash reaches `848B6FA0`. Audited 185 interleaved records and repaired their two missing targets; gameplay retry remains required.
- [2026-10-31 Gameplay startup callbacks](2026-10-31-gameplay-startup-callback.md): successive attempts reach unregistered `8471B2F0` and `8471B2E8`; audited their complete 25-entry family, registered four missing thunks in total, and added calling-convention execution checks. Gameplay retry remains required.
- [2026-10-31 Menu boot](2026-10-31-menu-boot.md): the user confirms a successful native menu boot; a subsequent gameplay attempt and crash are recorded in the callback finding above.
- [2026-10-30 Native build + control-flow recovery](2026-10-30-native-build-and-control-flow.md): native build succeeds; resolved 16 fatal fallbacks, recovered 37 switch tables, corrected VMX shifts and incremental builds, and survived a 30-second startup observation. Menu boot was subsequently user-confirmed; gameplay entry failure and its mapping fix are recorded above.
- [2026-10-09 Phase 0 inventory + USRDIR archive](2026-10-09-phase0-inventory.md): split archive `AA00B3BF` decoded and round-tripped; TOC size is bytes; 300 files shared with 2K9, whose IFFs are byte-swapped.
- [2026-10-22 Port target + archive rebuild](2026-10-22-port-target-and-archive-rebuild.md): the port targets the 360 XEX; the USRDIR archive can now be rebuilt with resized or relocated entries (an identity rebuild is byte-identical; not yet boot-tested).
- [2026-10-22 First ReXGlue codegen](2026-10-22-rexglue-first-codegen.md): ReXGlue reads the retail XEX directly; codegen succeeds with 8 manual function starts (53,803 functions); 16 fatal fallbacks in 3 functions remain.
- [2026-10-22 Xbox 360 disc inventory](2026-10-22-xbox360-disc-inventory.md): the 360 disc uses the same `AA00B3BF` archive (13 × 512 MiB, 3,378 entries) and the PS3 tools work unchanged; audio banks differ; XEX is XDK 2.0.5632.
- [File inventory (CH2K8 vs 2K9)](file_inventory.md): per-extension and per-family tables, plus a side-by-side of shared formats.
