# 2026-10-22: First ReXGlue codegen of default.xex

Follow-up: [2026-10-30 native build and control-flow recovery](2026-10-30-native-build-and-control-flow.md)
reproduces and resolves the 16 fatal sites, identifies two additional owning
functions in the original grouping, and records recovered full switch tables.
The historical results below describe the original uncorrected generation.

## Question
Can ReXGlue recompile the CH2K8 360 executable as-is, and what does it trip on?

## Method
- Set up `port/` on the WWE SvR 2008 recomp layout: manifest, `config/default.toml`, `config/pointer_funcs.toml`, CMake files, a minimal `src/main.cpp`.
- Downloaded the prebuilt SDK `rexglue-sdk-0.10.0.24-dev.gbd833a2-win-amd64.zip` (44,717,595 bytes) from the rexglue/rexglue-sdk GitHub release `nightly-20261002-bd833a2a`. Its SHA-256 `1e19d7ec…27e7` matches the digest GitHub publishes. Unpacked to `port/sdk/` (gitignored).
- Ran `sdk\bin\rexglue.exe --log-file logs\codegen.log codegen ch2k8_manifest.toml` on the unmodified retail `work/ch2k8/XBOX/disc/default.xex`.

## Evidence
- ReXGlue loads the **retail (encrypted, LZX-compressed) XEX directly**: title ID 54540818, media ID 459AF3FE, version 0.0.0.2, file time 2007-10-19 22:02:18 UTC. No separate decryption step is needed for codegen.
- **Run 1** (385 s) failed validation with 8 `UnresolvedCall` errors: unconditional `b` tail calls into addresses not inside any function.
- **Run 2**, with those 8 targets added to `pointer_funcs.toml`, **succeeded** (418 s, exit 0). It wrote 287 files (140 `ch2k8_recomp.*.cpp`, 150 MB) and **53,803 functions**.
- Size warnings only: `sub_84E75D28` produces 8.8 MB of C++ and `sub_84B6ACB8` 1.0 MB, above `max_file_size_bytes`. `sub_84E75D28` is one real function (a single `mflr`/`blr`) made of about 170k straight-line `lis/addi/li/sth/stw` stores, i.e. a compiler-generated static-data initializer.
- **16 `REX_FATAL` fallbacks** remain. Each only fires if that path runs:

| Function | Site | Issue |
|---|---|---|
| `sub_84C208D8` | `bctr` @ `0x84C20964`, branches 0x84C20948–0x84C20B68 | jump table (2 cases) and 10 conditional branches unresolved |
| `sub_84D40778` | 0x84D40810–0x84D40834 | 4 conditional branches unresolved |
| `sub_84DAB6FC` | `0x84DAB70C` → `0x84DAB6F4` | branch to 8 bytes **before** the function start: the start is likely mis-detected |

## Conclusion
- The 360 static-recompilation path works on CH2K8 out of the box. It needed only 8 manual function starts to produce a complete codegen.
- The next blocker is the build toolchain (CMake, clang 20+, Ninja, MSVC/Windows SDK libraries), not the analysis.

## Confidence
- Codegen success, function count, fatal-site list: [CONFIRMED] (logs in `port/logs/`, gitignored).
- The 8 added addresses being true function starts: [GUESS]. They could be mid-function labels of mis-split functions. Check in Ghidra.
- `sub_84E75D28` being a static initializer: [LIKELY], from the instruction mix and the single return.

## Open questions
- Fix the 3 fatal-site functions: recover the jump table at `0x84C20964` and correct the start of `sub_84DAB6FC` (and possibly the boundaries of `sub_84C208D8` and `sub_84D40778`).
- Install the build toolchain and compile. See whether clang copes with the 9.7 MB `ch2k8_recomp.41.cpp`.
- First boot: does it reach the legal screens with the stock Xenos GPU plugin?
