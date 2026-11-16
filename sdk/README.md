# CHMOD extension SDK (ABI 2 / mod API 1.3)

Canonical SDK host: [College Hoops Recomp Modding Studio](https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp), `sdk/`.
The recomp carries a matching SDK snapshot for building runtime adapters. This is
Windows x64 native code, with explicit launcher opt-in and full user access.
Checked interfaces are not a sandbox. No existing emulator patches are reproduced.

Status: researched/implemented; runtime and three neutral example DLLs compile.
No tests, DLL execution or gameplay acceptance have been performed for ABI 2.
See [contracts](CONTRACTS.md), [mod author guide](AUTHORING.md),
[adding an adapter](ADDING_HOOKS.md), [inventory](hooks.json), and
[remote acceptance](ACCEPTANCE.md).

Build from an x64 Visual Studio C++ developer terminal (CMake 3.25+, Windows SDK):

```powershell
cmake -S sdk -B C:/dev/chmod-examples -A x64
cmake --build C:/dev/chmod-examples --config Release
python sdk/package.py --dll C:/dev/chmod-examples/Release/chmod_observe.dll --manifest sdk/examples/minimal/observe.json --output C:/dev/neutral-observe.chmod
```

Ninja/Clang builds work with the Visual Studio/Windows SDK environment initialized.
The configure step performs compiler probes; it does not execute game code.
The `observe`, `transform`, and `replace` projects are neutral demonstrations:
observation, identity setter-argument transformation, and replacement delegating
to the original. They do not implement gameplay changes or certify integration.
Players need only the launcher/runtime, not these build tools.

For mixed packages supply `--payload-root` containing authored assets/rosters and
a matching manifest. Hashes for non-DLL payloads remain author-declared and are
validated by Studio/launcher. The tool updates only the DLL hash and emits a
reproducible ZIP-compatible .chmod. It never loads the DLL or accesses game saves.
Use Studio's canonical contract validation before distribution. Do not include
compiler runtime dependency DLLs as undeclared payloads; target the distributed
runtime's CRT, and avoid additional unprovided DLL dependencies.

Native Presentation Button Style is available through a new capability with the
existing ABI 2 host. See [contract, build and remote acceptance](BUTTON_STYLE.md).
Its source consumer is an actual mod; in-game behavior remains unverified.
