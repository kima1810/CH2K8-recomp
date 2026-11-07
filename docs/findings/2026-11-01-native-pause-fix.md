# Native D3D12 pause-menu fix

## Question

Resolve the severe live 2K Nav lag rather than stopping at shader microbenchmark improvements. Preserve correct gameplay, replay and camera transitions.

## Method

Test the actual user-operated gameplay/menu path with native D3D12 host render targets. Prior fixed-function tests were autonomous demos, not this transition. No game input or UI control is sent by the agent. Preserve coherence, queries, barriers, save data and existing shader caches. Run isolated configuration changes and obtain user confirmation of visible behavior.

## Evidence

**[CONFIRMED by user and runtime]** `20261101-211517-510-gpu-d3d12-rtv` uses host render targets instead of ROV. The user reports that 2K Nav is lagless, but brief black flashes occur before and during gameplay and recover. Native hardware depth/stencil and blending remove the software pixel-operation bottleneck from the menu path. This run does not establish that all rendering transitions are correct.

**[CONFIRMED rejection]** `20261101-212139-065-gpu-d3d12-rtv` disables asynchronous shader compilation and shader storage for this process, without deleting any cache. The log confirms `async_shader_compilation=false`; no cached shader/pipeline load is recorded. The user still observes flashes during ordinary uninterrupted gameplay, while the menu stays responsive. The SDK's pending-pipeline draw-omission branch is real, but this control rejects it as the cause of these particular flashes. Do not describe synchronous compilation alone as their fix.

**[CONFIRMED from pinned source]** The draw-extent estimator documents that broad EDRAM ownership transfers can corrupt neighboring render targets when format conversion is lossy. `execute_unclipped_draw_vs_on_cpu` bounds eligible unclipped draws using their vertex positions and otherwise retains the conservative fallback. This preserves the native rendering path and ordering; it does not discard geometry or infer a paused state. The apparent direct-host-resolve shortcut was also inspected: in this SDK it ultimately calls the same dump path, so disabling it was not pursued as an independent correctness fix.

**[CONFIRMED by user]** `20261101-213037-751-gpu-d3d12-rtv-extent` repeats the synchronous, cold-storage native test with **only the bounded-extent option added**. The user checks uninterrupted gameplay, 2K Nav, and camera/replay changes and reports **no flashes and a responsive menu**. The process closes normally, exit zero. Between elapsed 70 and 100 seconds, 1,030 guest submissions have median interval **29.987 ms**, p95 **35.045 ms**; these are mixed tested scenes, not a locked paused-state or unique-displayed-FPS metric. Fence-wait bins are negligible (roughly 0.1 ms per second), compared with the earlier ROV paused trace's approximately 72% graphics-thread fence occupancy and 115.181 ms median submission interval. Different scenes prevent assigning a precise whole-game speedup ratio.

**[CONFIRMED final user validation]** The normal launcher is then run at the user's saved **2560x1440 borderless, 60 Hz**, with Automatic rendering and ordinary persistent shader storage enabled. The launched process is 6860. The user again checks gameplay, 2K Nav, and replay/camera changes and reports **responsive, no black flashes**. This validates the normal launch configuration rather than only a diagnostic command line. The normal game may remain open for the user; it is not terminated for offline checks.

## Change

Automatic D3D12 now selects:

- `--render_target_path_d3d12=rtv`
- `--execute_unclipped_draw_vs_on_cpu`
- `--no-async_shader_compilation`

The explicit Native D3D12 choice uses the same configuration. Synchronous creation retains every draw while pipelines are compiled; the extent option is the isolated change that resolved the observed flashing. The default keeps persistent shader caching enabled. **Accurate Xbox blending** retains the ROV compatibility path and all preceding measured optimizations. Vulkan Automatic remains FSI; Vulkan Native/FBO remains experimental. No global driver, OS or GPU tuning is applied.

The diagnostic benchmark gains temporary `-ShaderCompilation synchronous` and `-ColdShaderCache` switches for reproducible cold-storage controls. Launcher argument tests cover the new default, explicit native and compatibility selections, API separation and quoted paths. Seven launcher tests pass. Both existing Release binaries remain the tested builds; this final change alters launch configuration, not game code. The preceding complete suite passes 91 tests with one environment-dependent skip.

## Conclusion and confidence

**[CONFIRMED in the user-tested scenarios]** The severe menu lag and native-path black flashes are resolved with the tested native-target configuration, including the user's ordinary 1440p borderless launcher. The isolated extent result supports **[LIKELY]** ownership-transfer corruption as the flash mechanism; no captured bad transfer has been reverse-engineered to prove its exact address-level cause.

## Open questions

Full-match completion, every team/camera, Legacy/save stability, and the separate UGA black-head report are not established by this validation. Consistent 60 FPS is not claimed. Use the retained ROV compatibility mode for a newly encountered rendering incompatibility.
