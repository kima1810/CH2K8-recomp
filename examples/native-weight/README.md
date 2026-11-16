# User-authored native hook example

`../native-weight-example.chmod` packages this source's compiled Windows x64 DLL.
It is not installed or enabled automatically. It executes unsandboxed code and
requires the launcher's explicit native-DLL opt-in plus the updated runtime.
No game or proprietary assets are included. The module was compiled but not
loaded or exercised by the agent.

The researched hook is the Xbox player weight getter at guest `84752968`.
The example returns original pounds +10, capped at 400, only when the original
value is in Studio's Xbox menu range 100..400. It changes this getter's result,
not raw player records or saves, and does not intercept consumers reading weight
directly. Guest consumers may save data derived from getter results, so native
code uses an isolated profile without existing Legacy saves. It is not a claim
of changed physics, simulation or recruiting.

Authoring ABI: [mod_extension_abi.h](../../port/src/mod_extension_abi.h).
Export `ChmodQueryExtension` using Windows x64 C linkage; do not expose C++ STL,
guest/PPCContext pointers or guessed x64 patch addresses. The returned descriptor
and callback remain valid until process exit. Callbacks are synchronous,
thread-safe and non-throwing, and must not retain the borrowed context. Invalid
return values preserve the original. There is one exclusive registration.

Developers compile `extension.cpp` as an x64 DLL, then run `package.py DLL_PATH`.
Packaging only reads the binary and writes a ZIP; it does not execute the DLL.
Players install the `.chmod` through Mods and need no compiler/Python.
User gameplay acceptance remains pending.
