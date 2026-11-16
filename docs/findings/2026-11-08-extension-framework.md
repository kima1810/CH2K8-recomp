# Reusable native extension framework — 2026-11-08

Supported USA XEX SHA256:
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
Recomp base `1caa20dc74c09380cba6498bc38cfb04e14e922e`, working-tree additions;
ReXGlue `bd833a2ab69d305f99ddf57418fc38ffec8af93d` with existing project patches.
Studio parent `5917f68`, branch feat/chmod-extension-sdk.

Implemented infrastructure: portable nonguest `mod_framework` registry/dispatch,
strong-symbol runtime adapters, versioned x64 C ABI2 and C++ helpers, independent
capability/registration validation, deterministic composition, original-once,
callback scopes, checked player property access, terminal dispatch drain, rollback
initialization, no hot unload, launcher/schema/receipt API1.3 integration. ABI1
legacy packages retain their entrypoint and conservative overlap exclusivity.

## Evidence and available operations

Getter84752968: generated ch2k8_recomp.12.cpp, setter848425D8:
ch2k8_recomp.96.cpp. Read-only Ghidra12.2 on the existing Xbox default.xex project
with no analysis confirmed the translated PPC loads/extract/insert/store/return.
[Saved disassembly](../research/hooks/2026-11-08-weight-disassembly.txt) records
instructions and interpretation. Studio Xbox field metadata independently names
weight and menu100..400, anchor bias16/raw row156. This verifies function bodies
as static research, not game behavior or generic memory safety for arbitrary rows.
Runtime creates tokens only from the active native game call. No guest address
or structure offset is exposed by ABI2. ABI1 retains its previous opaque anchor.

Generated ch2k8_init.cpp and ch2k8_register.cpp map both addresses to `sub_` symbols;
DEFINE_REX_FUNC supplies weak aliases to preserved `__imp__` bodies. Nongenerated
strong wrappers intercept those map references and any symbolic direct calls.
No generated direct call sites for these two property symbols were found in this
snapshot; observed gameplay dispatch is not claimed. The synthetic direct/map
linkage fixture is prepared/compiled but unrun. New inlined/raw consumers require
separate adapter/codegen research. No generated source files were hand-edited.

Host main.cpp OnPostSetup is called before guest launch in SDK rex_app.cpp.
It initializes all modules then emits ready. OnShutdown suppresses new dispatch,
drains callbacks, emits stopping, retires registrations and invokes DLL shutdown
in reverse order. SDK OnDestroy invokes OnShutdown before general host cleanup;
this does NOT establish guest-save flush or terminated guest threads. No guest
session/game/save lifecycle hook has been invented.

Setter can transform supported pounds arguments before original, or an exclusive
replacement can skip the write. Getter supports after-result transformation or
replacement/original. Before/after observation and lifecycle observation dispatch
are implemented. Checked property read invokes original getter on a copied PPC
context; pending write modifies only the current setter argument. Stored values
are0..511; mod edits100..400, preserving unchanged native values outside that range.
Setter writes real data; getter consumers may persist derived behavior. Existing
code-selection profile isolation remains mandatory.

## Verification boundary

Recompiled runtime, three neutral DLLs and two synthetic framework/linkage test
executables compiled on Windows x64 Clang23.1.4/MSVC14.51 SDK26100. Compiler probes
were permitted. Example .chmod archives were produced without executing DLLs.
Test source includes registration/order/conflict/original/failure/unregister/
handle/lifecycle/no-mod fixtures and Python metadata/Studio attachment cases.
NO tests, extension DLLs, editor UI, game or save operations were executed. User
saves were not modified. No Windows popup was opened or closed. Ghidra research
was static/read-only; no performance gain is claimed.

Status per inventory: Researched, implemented, compiled. Not structurally validated
by test execution; not In-game verified. C++ exception fallback cannot catch
arbitrary native crashes or undo original/unsandboxed DLL side effects. Save edits
and user testing remain remote. Advanced gameplay/simulation/season/conference/
scheduling/UI/input/scorebug and public frame adapters remain research boundaries.

SDK canonical host is the Studio GitHub sdk/ directory; recomp carries a matching
source snapshot. The Studio source backend/CLI and future packaging include it.
The existing installed editor has the SDK folder added alongside its executable;
the editor executable was not rebuilt. No existing RPCS3 patch was recreated.

## Publication and deployment

SDK source/Studio integration published at
https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp/tree/feat/chmod-extension-sdk/sdk
(commit `6ed7c42`), draft PR https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp/pull/3.
Commit uses `[skip ci]` per the user's no-test instruction. No main merge or
release binary publication was performed. Existing installed Studio has SDK
source beside its executable; source CLI/builds expose the new attachment API.

Runtime executable and matching SDK DLLs deployed beside the existing launcher;
exe SHA256 `c8d10f9b3a5d1bb9f1af4e37927e75df1aaa9e65d27bb9a81cbd3be5f98641c2`.
Final map: getter original14047f190/strong142b93700; setter original141ea0160/
strong142b939e0. These native addresses are build evidence, not API contracts.
Receipt binds the exact exe/XEX with ABI1/2 and six required capabilities.
Previous binaries are retained on C: outside D:; user saves remain untouched.
Three neutral example .chmod archives are under examples/ and are not enabled.


Static PowerShell AST parsing and Python in-memory source compilation completed;
these inspected syntax without evaluating modules or executing tests. GitHub's
PR-associated workflow query returned no runs for the SDK commit; CI was skipped.
Native test executables remain unrun. The capability-receipt producer derives
hook names/capabilities from the versioned SDK inventory and requires strong/original
symbols for each exposed guest adapter. SDK snapshot hashes are recorded in
formats/sdk-snapshot.json for reproducible Studio/recomp handoff.
