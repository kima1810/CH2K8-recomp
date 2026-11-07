# Menu render-target writes and asymmetric blending

## Question

Can exact color-write and blend decisions reduce the native GPU backlog in 2K Nav without changing its rendering?

## Method

Use the original user-opened menu recording as the fixed workload. Compile candidates in manually operated live runs, then identify exact native shader instruction matches before replacement. Require identical nonzero full EDRAM against both original and supplied optimized controls before warmed, alternating GPUTime measurements. No game input is sent by diagnostics.

## Full-write specialization

**[CONFIRMED]** The recorded recurring shader has RT0 keep masks `{0,0}`. These masks are dynamic in its translated shader, forcing preservation logic and preventing the driver from eliminating old-color loads even when the whole target is overwritten. Add an exact full-write bit to the existing 16-bit pixel state by biasing the low 15-bit encoding and reserving zero for dynamic state. Valid Xenos MSAA modes 0-2 leave enough space; reserved mode 3 keeps the dynamic path. No key grows beyond the original eight-byte modification.

Only the first target's X/Y keep-mask components can fold to zero. Swizzles selecting other components remain dynamic. Eligibility requires a full normalized RGBA write mask and a supported color format. The production-format contract test executes the actual SDK keep-mask function for 4,096 format/mask combinations and confirms every eligible case has zero keep bits. Unknown formats retain dynamic handling. Independently reject a specialized draw if original system constants do not agree with the encoded proof.

**[CONFIRMED]** Capture `20261101-201454-694-capture-optimized` contains candidate inventory shader 15, matching the previous early-depth shader apart from the intended RT0 keep-mask substitutions. Both candidates reproduce identical full nonzero 10 MiB EDRAM at events 3532, 682 and 12264 of the original menu recording. With the preceding optimized shader supplied as control, three warmed pairs reduce total timed action sums from 25.167/25.169/25.176 ms to 24.412/24.420/24.415 ms: **3.00% median incremental reduction**. The selected draw falls **3.46%**. This experiment replaces one recurring shader resource, not the complete renderer.

## Asymmetric blend investigation

**[CONFIRMED]** The most expensive recorded menu draw, event 8503, has blend control `0x00010706`: RGB source-alpha plus inverse-source-alpha destination, with alpha overwrite. The previous exact blend palette supports symmetric color/alpha combinations, leaving this control dynamic. Its translated shader therefore retains generic factor/operation branches. The recorded keep mask is again zero, MSAA is 4x, and RT0 format flags are `0x4C`.

Expand the 31-entry reversible palette to include this exact asymmetric mode and standard alpha accumulation. Keep 29 symmetric modes; two displaced constant-factor modes safely return to dynamic handling. Bump the shader cache version and preserve per-draw validation. No shader hash or menu-state heuristic routes production draws. Capture `20261101-202701-667-capture-optimized` contains candidate inventory shader 67, an exact instruction match for full-write baseline inventory shader 67 from the preceding capture except for the intended blend-control literal substitutions. Native routing remains state-based.

**[CONFIRMED]** With the manually operated game closed, both supplied controls reproduce the original nonzero 10 MiB EDRAM at events 3532, 8503 and 12264. Warmed paired event-8503 GPU times are 0.71288/0.50380, 0.71444/0.50184 and 0.71764/0.50184 ms (baseline/candidate): **29.76% median target-draw reduction**. Whole-recording sums vary from a 3.60% regression to a 0.46% reduction; their median 0.26% change does **not** establish an aggregate improvement. The stable selected-draw saving is reported separately from this noisy total.

## Conclusion and confidence

Full-write specialization measurably reduces the tested menu GPU work with identical output. The asymmetric mode also measurably reduces the expensive selected overlay draw with identical output. Full-write specialization is enabled by default after validation; `--no-ch2k8_native_full_write` restores its original dynamic masks. The broader `--no-ch2k8_native_pixel_state` fallback remains available for blend specialization. These changes do not establish a complete severe-lag fix or a displayed-FPS gain.

## Open questions

Assess remaining native ROV/MSAA costs. The paused recording processes a full-resolution 4x-MSAA scene; previously inspected live-demo variants also include 1x-MSAA passes. This is a likely contributor, not a paired proof that pausing alone changes the whole renderer's sample count.

## Validation

The full repository suite passes **91 tests, one environment-dependent skip**. Both Release game builds and the pinned dual-backend SDK build/install pass. Exhaustive key checks cover **49,152** disjoint full/dynamic-mask pixel states, plus 524,288 interpolation round-trips and all 128 depth/hint patterns. The format contract uses the actual upstream function across 4,096 input combinations. The schema/cache version is bumped for both the biased key and updated blend palette. Unknown formats, reserved MSAA modes and controls outside the exact palette retain dynamic handling. All game assets, bytecode, captures and logs remain local.

The subsequent [native pause-menu configuration](2026-11-01-native-pause-fix.md) resolves the user-tested lag and black flashes; these shader improvements remain in the retained ROV compatibility path.
