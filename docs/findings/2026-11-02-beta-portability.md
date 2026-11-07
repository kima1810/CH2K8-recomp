# ZMO beta 1 portability and ISO validation

Historical dependency design: the bundled Python described here has been replaced by [native launcher tools](2026-11-02-native-launcher-tools.md). See BETA.md for current tester requirements.

## Changes

The distributable now includes an isolated, hash-pinned Python 3.14.10 embeddable runtime, x64 Microsoft C++ CRT DLLs, the pinned SDL controller database and its license, all transitive asset-preparation modules, and third-party notices. No tester Python, PATH changes, compiler, SDK, developer checkout or first-run download is required. `prepare_beta_deps.ps1` prepares maintainer dependencies; `package_beta.ps1` rejects missing components, checksum mismatches, non-x64 binaries and unresolved non-system PE imports before creating a ZIP. Version metadata records the source revision, dirty state and actual runtime hashes.

Launcher preflight checks the Windows/CPU target, DLL loading, writable locations, supported USA default.xex SHA-256, complete extracted-disc parts or imported-folder metadata, Python module availability, and D3D12 device creation or Vulkan loader presence. A successful check is not a gameplay or Vulkan feature certification. Rendering options retain their existing defaults and compatibility fallback.

ISO import validates the supported executable identity and archive extents before extraction, checks a minimum free-space lower bound, and records validation metadata in new installations. Invalid games, incomplete images, existing destinations, cancellation and simulated disk-full failures are covered. The full decoded installation can need more space than the initial estimate; failed imports discard only their own staging directory.

Spaces, brackets and Unicode path tests exposed PowerShell 5.1 wildcard handling in process redirection, working directories and ZIP output. Process creation uses literal .NET paths; ZIP creation uses ZipFile. The pinned SDK patch also preserves UTF-8 cvar paths for game/user/update data and opens runtime logs through filesystem paths instead of narrow fopen. Native framebuffer captures preserve Unicode paths too. The launcher scrolls when the desktop is smaller than its contents and displays a responsive preparation dialog while loose resources validate.

Export bug report works even for a broken installation. Reports include selected/last launch options, version, actual binary hashes, available OS/CPU/GPU/driver information, preflight failures and bounded runtime/import log tails. Common paths are redacted. Game data and saves are excluded; reports are never uploaded automatically. Startup errors are surfaced instead of disappearing with the hidden console. `BETA_TESTING.md` supplies the reproducibility checklist and compatibility matrix.

## Local evidence (November 2, 2026)

- A retail USA Xbox 360 ISO of 7,835,492,352 bytes passed inspection: expected default.xex SHA-256 `71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`, 13 parts, 3,378 archive entries and a 6,492,522,496-byte virtual archive address space.
- A full ISO-to-loose import completed from a relocated beta with developer tools removed from PATH and invalid PYTHONPATH/PYTHONHOME values. It produced editable resources and native loader maps without physical 0A-0M chunks. The original image was opened read-only. Small fixtures separately verify source hashes, transactional cancellation, malformed directory rejection, all four partition offsets, wrong-game rejection and low-disk handling.
- The rebuilt native runtime mounted the newly imported 13-part virtual archive and produced a visibly correct 1280x720 title-screen capture on D3D12 / Automatic. A further capture succeeded with Unicode and brackets in the executable, imported game-data, user-data, log and capture paths, again with a minimal PATH. The test-owned process stayed alive for 45 seconds and was then stopped. This is title-screen boot evidence, not a gameplay-completion claim.
- The runtime reported an AMD Radeon RX 6650 XT. Other GPU families and controllers still need independent tester records.
- The SDK runtime and application rebuilt successfully. The final automated suite passed 105 tests with 21 skips for absent local tooling or optional platform data. A subsequent inventory-only regression check also passed.

## Limits

Only one physical hardware configuration has been exercised here. NVIDIA, Intel graphics, older CPUs, Windows 10, varied audio/controllers, high-DPI displays, Legacy, full-game completion, saves and edited assets require matrix testing. SSE4.1 Windows x64 with D3D12 is the binary beta target; ARM, 32-bit Windows, Linux and macOS are outside this package. Vulkan remains experimental and imported loose resources require D3D12. Folder preparation may take several minutes; the launcher reports that phase instead of appearing frozen.

The Python archive comes from [Python.org](https://www.python.org/downloads/release/python-31410/); controller mappings come from [SDL_GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB/tree/07af1d50187e94c861c9f9f5d8a55b148f11306b). CPU preflight uses Microsoft's [IsProcessorFeaturePresent](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent) SSE4.1 flag.
