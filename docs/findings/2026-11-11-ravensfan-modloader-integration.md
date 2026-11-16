# RavensFan findings and the modloader

Source is `origin/RavensFan-beta` at `51132f7f22422e79797fb891cac4d6039ccecfb9`.
The [menu research](2026-11-10-menu-screen-system.md),
[Legacy research](2026-11-10-legacy-mode-internals.md), and
[settings getter finding](2026-11-04-settings-menu-getter.md) are retained here
with their original confidence labels. The research targets retail USA Xbox 360
XEX SHA-256 `71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.

The existing Button Style adapter matches the independently researched option
screen handler, descriptor table/count, 0x5C stride and callback positions.
The runtime now centralizes this layout in `port/src/mod_option_menu.h`.
It verifies that each newly allocated thunk falls in the entrypoint reserve and
that both the dispatcher registry and generated indirect-call fast table return
the intended function. The appended row gets fresh work state. The existing
Button Style package, public SDK ABI and hook ID are compatible with this change.
The new callbacks use runtime thunk allocation. Interception of the existing
guest menu handler still uses a recompiled wrapper.

The separate `84CA8998` settings getter is a stock function reached indirectly.
Its verified 16-byte body is registered through `port/config/pointer_funcs.toml`
so regenerated runtimes can call it. This is separate from thunk allocation.

Legacy integration candidates, in order of available evidence:

- **Prestige observation.** Generated `sub_84D09CF0` independently confirms a
  team argument in r3, four 9-bit fields from `+0x2B0` and `+0x2B4`, and a
  single-precision result in f1. A typed read-only snapshot can expose the
  four values and original result without exposing a writable team pointer.
  Establish caller contexts and team lifetime before publishing it.
- **Injuries and fatigue.** The generated map already includes getters
  `84818388` and `84818398`. The findings identify their globals, while
  mode ownership, settings writers and persistence still need tracing before
  offering mutations or an additional option row.
- **Legacy screens.** List bindings and node bindings provide routes for
  read-only data providers. Verify each callback ABI and lifetime on one
  target screen before generalizing from option rows to list screens.
- **Development, drills, recruiting and carousel.** Start with observation
  at named entry points. These operations change state in several places,
  including queued calendar tasks and snapshots. Their writes need explicit
  side-effect and save round-trip evidence.
- **Conference swaps.** The native routine updates both member lists, team
  metadata and derived state. A direct conference-pointer edit would leave
  those relationships inconsistent. A future operation needs the native swap
  contract and isolated Legacy save verification.

Code generation and the Windows x64 build completed. The regenerated map
registers `84CA8998` and the generated body loads the original settings field
at `+0x20C`. The installed executable and GPU/runtime DLLs match the capability
receipt. Verification was limited to compilation and static inspection. New
Legacy SDK hooks remain pending, and the upstream runtime observations remain
attributed to the original findings.
