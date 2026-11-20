# Remote acceptance — prepared, not executed

No game or test execution was performed by the agent. Compilation is separate.
Use disposable profiles and preserve user files before your own runtime checks.

1. Compile/run `tests/mod_framework_tests.cpp` with mod_framework.cpp via the
   standalone tests CMake project. These are synthetic dispatch fixtures, not
   guest integration. Confirm phase order, dependency/module order, two result
   transformations, exclusive replacement conflicts, original-once caching,
   invalid transform rollback/disable, checked pending setter, expired tokens,
   unregister, ready/stopping and no-mod fallback after stop.
2. Run prepared Python CHMOD suites including `test_chmod_sdk.py`. Confirm ABI 1
   packages still import, ABI 2 needs1.3, unknown capabilities/ABI/type/duplicate
   claims reject, hashes/PE/path bounds reject, and asset-only metadata never loads
   DLLs. Test explicit replacement collisions and two nonexclusive observers.
3. Inspect a fresh regenerated build/link map: getter and setter strong symbols
   must come from mod_extensions.cpp; __imp__ originals must remain distinct.
   Verify generated registration maps refer to strong names. Test both a synthetic
   direct symbolic call and function-pointer map call; do not infer direct guest
   coverage from registry-only testing. Inspect raw/inlined consumers separately.
4. Install the three compiled neutral examples via Mods. Decline native opt-in:
   launch must reject. Opt in: ready should log once, observation should log only
   on a reached getter; identity transform and original-delegating replacement
   should preserve observed behavior. Reach the researched setter through game
   interaction, not guessed memory writes. No tuning/presentation patch is included.
5. Register several observers/transformers, reorder priority and add exact package
   dependencies. Dependencies precede dependents; phases compose in documented
   forward order. Duplicate exclusive replacement must fail before gameplay.
6. Exercise original invocation twice, failing replacement before original,
   failing replacement after original, invalid output, throwing C++ callbacks,
   same-hook recursion and cross-hook nesting in synthetic fixtures. Verify
   callbacks disable individually and original side effects are never duplicated.
   Do not use access violations as a claimed recoverable callback test.
7. Test initialization failure in a later module: no ready/gameplay callbacks
   publish, prior registrations retire and shutdown order reverses initialization.
   DLL process side effects remain unsandboxed. Missing exports/dependencies and
   wrong descriptor sizes/ABIs yield actionable recovery instructions.
8. Close normally: stopping follows suppression/drain, then module shutdown in
   reverse order. Test concurrent callbacks and unregister: in-flight snapshots
   can finish, no new callback uses retired registration, user data remains live
   until shutdown. No FreeLibrary/hot reload is expected. A hanging callback cannot
   be safely forcibly unloaded.
9. Confirm code selection uses isolated Dummy HDD profile and existing Legacy
   saves remain separate. Check supported setter persistence only in disposable
   saves. Getter behavior can affect later persisted guest calculations too.
10. Use Launch without mods after failed native loading/crash. It must bypass ALL
    extension loading even persisted cvars, use baseline assets/profile, and retain
    existing save backup policies. Confirm native .chmod + assets + native roster
    activation is coherent, including updates and rollback. Test data-only updates
    adding code require manual review and opt-in; required capabilities must be
    checked against the executable-bound API1.3 receipt.

Record revision, package digests, machine, observed behavior and failures. A DLL
compilation or synthetic fixture result is not gameplay or performance evidence.

Native Presentation Button Style is available through a new capability with the
existing ABI 2 host. See [contract, build and remote acceptance](BUTTON_STYLE.md).
Its source consumer is an actual mod; in-game behavior remains unverified.
