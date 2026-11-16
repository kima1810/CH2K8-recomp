# Adding a researched runtime adapter

1. Identify the supported Xbox XEX by SHA256. Inspect its PPC function in Ghidra,
   generated translation, descriptor/registration records and call sites. Record
   signature, side effects, alignment/endianness, valid argument ranges, caller
   threads, object ownership and lifetime. Other-platform findings are leads only.
2. Verify generation boundaries. This pinned ReXGlue emits `DEFINE_REX_FUNC(name)`
   as a weak alias to `__imp__name` and preserves the translated original body.
   A strong `REX_HOOK_RAW(sub_ADDRESS)` in nongenerated adapter source replaces
   symbol references while `__imp__sub_ADDRESS` stays callable as the original.
   Both generated guest function maps use `sub_...`. Direct symbolic native calls
   also resolve that strong symbol; changing the guest table alone is insufficient.
   The two current property functions have map references but no generated direct
   call sites were found in this snapshot. Do not claim observed direct execution.
3. Exclude internal codegen inlining/optimized bypasses for the target. If codegen
   lacks a distinct symbol, update the version-controlled manifest or postgenerator
   pipeline (`tools/run_codegen.py`, `fix_codegen.py`, `optimize_codegen.py`) with
   narrow checks, then regenerate. Never hand-edit generated .cpp/.h files. No
   codegen change was needed for the current adapters; a normal regeneration keeps
   the weak-alias/original structure. Review this assumption on SDK updates/LTO.
4. Add semantic C POD argument/result types and a new stable hook ID/version to
   the public SDK. Avoid guest addresses/PPCContext in public payloads. Use opaque
   callback-scoped tokens unless a persistent identity is independently verified.
   Add only supported operations, validation and checked data accessors. Define
   persistence effects and object/thread lifetime. Do not expose an unresearched
   function under a generic pointer API.
5. Add metadata to Studio SDK `hooks.json` and the matching runtime inventory,
   then run `tools/generate_mod_inventory.py`. CMake also regenerates the internal
   metadata include from the versioned inventory. Extend schema capability/ABI
   rules and distribute the matching inventory/SDK snapshot. The generic loader,
   registration registry, ordering, original invocation and packaging stay reusable.
6. Write the strong nongenerated wrapper. Translate PPC parameters internally,
   create typed arguments with `typed_call` or `typed_void_call`, supply original
   invocation and validation closures, and call Framework::dispatch. The generic
   engine handles before/replacement/after, callback order, scopes and failure.
   Adapters alone own guest memory validity; never trust a mod-created object token.
   Original closure must bypass the hook and execute at most once via the engine.
   Hooks without side effects may supply safe callback-scoped read accessors.
7. Preserve original behavior on the no-extension path, including guest register
   and FP effects. Define whether original results outside mod-edit ranges must be
   preserved (current getter allows native 0..511 but edits100..400). Do not claim
   that suppressing a function is harmless; replacement is an exclusive operation.
8. Add fixture tests for ordering/validity/fallback and source/linker coverage.
   Require the wrapper and `__imp__` originals in capability-receipt generation.
   Inspect final linker maps, registry references and symbolic direct call lowering.
   Rebuild the recomp and ship the new executable with an updated hash-bound
   receipt. Existing mods on existing adapters need no rebuild.
9. Record stages honestly: Researched, implemented, compiled, structurally validated
   (only after relevant isolated tests), In-game verified (only actual observation).
   The current work stops at compilation/static evidence by user instruction.

Architectural domains are listed in hooks.json. General function dispatch is
implemented; game session/save lifecycles, roster/conference semantic SDK, simulation,
season/competition, scheduling, UI/presentation, navigation and public frame hooks
still need verified adapters. Frame timing probes at 84DCB314/318 remain internal
diagnostics and are not misrepresented as scorebug events or SDK lifecycle APIs.
