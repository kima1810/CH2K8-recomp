# CHMOD backend continuation: Xbox evidence and verification handoff

## Authority and scope

The user resumed the original modloader task, initially allowing research and
verification. After one isolated game launch, the user instructed: do not open
the game and do not run tests; they will test remotely. The game instance was
closed. The editor may be opened, but none was needed for these backend changes.
No subsequent game launches, automated test executions or validator executions
were performed. Native backend compilation is reported separately from tests.

Repository remains `ZMO-beta1` at
`1caa20dc74c09380cba6498bc38cfb04e14e922e`; read-only GitHub inspection confirmed
the branch still points there. SDK source authority:
`work/third_party/rexglue-vulkan`, commit
`bd833a2ab69d305f99ddf57418fc38ffec8af93d`.
Studio source authority: `30a36266a55976c294187ee36ad878212e3c8b77`.
Supported retail XEX is the USA SHA256 documented in the manifest specification.

Status terminology remains: **Researched** = identified, not proven;
**Validated** = structural/isolated checks actually passed;
**In-game verified** = observed working in the recomp. The additions below are
**Researched; implemented, verification pending**. Successful compilation does
not promote them to Validated or In-game verified.

## Native roster evidence: correction to the first-pass blocker

The first pass stopped at SDK paths. Continued read-only inspection found a real
native roster pair in the preserved Dummy HDD profile. Its package is
`B13EBABEBABEBABE/54540818/00000001/Roster.ROS/Roster.ROS`, accompanied by
`B13EBABEBABEBABE/54540818/Headers/00000001/Roster.ROS.header`.
These paths are observations of game/runtime storage, not newly invented paths.
No user roster or Legacy save was overwritten by the investigation.

Observed payload length: **4061188 bytes**. The first big-endian word is
`0x003df800` (4061184), equal to the number of following bytes. Before the user
stopped testing, the existing Xbox Studio parser accepted the body starting at
byte 4, finding 5685 players, 379 arenas, 443 teams, 1373 coaches, 39 conferences
and 988 uniform rows. Starting at byte 0 failed. This is a structural observation,
not proof that an edited native save loads successfully in the game.

The observed header is **328 bytes**. Its binary fields agree with pinned SDK
`include/rex/system/xam/content_manager.h`:

| Field | Byte offset | Observed / required current contract |
| --- | --- | --- |
| Device ID | 0 | big-endian 1, Dummy HDD |
| Content type | 4 | big-endian 1, saved game |
| Display name | 8 | 128 big-endian UTF-16 code units |
| Filename | 264 / 0x108 | 42-byte ASCII field, `Roster.ROS` and terminator |
| Padding | 306 / 0x132 | retained |
| Aggregate XUID | 308 / 0x134 | big-endian 64-bit zero in this neutral header |
| Title | 316 / 0x13c | big-endian `54540818` |
| Remaining ABI padding | 320..327 | retained |

`static_assert_size(XCONTENT_AGGREGATE_DATA, 0x148)` is authoritative for the
header size. `ContentManager::WriteContentHeaderFile` serializes that struct;
`ReadContentHeaderFile` reads the same size. `ResolvePackageRoot`,
`ResolvePackagePath` and `ResolvePackageHeaderPath` determine directory/header
layout. `ContentPackage` mounts its directory through writable HostPathDevice.
`KernelState` supplies the selected user-data root. `UserProfile::UserProfile`
sets the pinned SDK's default XUID to `B13EBABEBABEBABE`.

The marketplace `InstallContent` STFS path is not used as a roster importer.
The API accepts the actual observed native save pair and does not rename an IFF
component as a save, generate an STFS container, invent another package filename,
rewrite another profile XUID, or infer every possible ROS wrapper revision.

New code: `tools/native_assets/mod_contracts.h::validate_roster_save` and the
`validate-roster` native CLI command. It checks the length/header and bounded
Xbox tables, strings, relationships and uniform routes. Relationship offsets
and biases come from Studio `roster.py`, `relationships.py`,
`docs/ROSTER_RELATIONSHIPS.md`, and `uniforms.py` / `docs/UNIFORMS.md`.
Opaque bytes remain in the original supplied payload; there is no semantic
rewriter or automatic old-Legacy conversion.

New launcher behavior: `New-ChmodRosterProfile` stages a separate Dummy HDD root,
copies only User/Settings data, backs up the baseline roster pair, then publishes
the supplied pair atomically. It passes that root through existing
`--user_data_root`. A hash of the complete coherent mod selection determines
persistent profile identity. Unchanged sets reuse their saved data; updates and
changed linked assets receive fresh roots. Disabling returns to the original
root. Existing Legacy saves are never copied, overwritten or migrated. The game
must still load/select the roster itself. Multiple active rosters reject.

Limitations: profile selection beyond the pinned default, other native package
names/header sizes, unknown appearance/face/model references, checksum variants,
roster import UI behavior, persistent-save transitions and live roster loading
remain unverified. This does not establish that editing a base roster changes an
existing Legacy save. The binary's scheduling/simulation/recruiting/tournament
behavior is not altered by this implementation.

## Source-compatible SCNE evidence

Studio `geometry.py::source/import_obj` explicitly limits writing to embedded
single-component Xbox cloth and unquantized Xenos float3 positions. Its
`scene.py::preview` uses 176-byte mesh records, vertex count at descriptor+8,
stream count in the high halfword at descriptor+12, 24-byte CPU stream rows,
64-byte declarations and native 16-bit index streams. Studio's supplied-corpus
evidence is recorded in `docs/XBOX_FORMATS.md`; its preview is not gameplay.

New native `validate_cloth_positions` reads these source-derived extents and
allows only finite position triples on word-aligned streams. Replacement length
and every non-position byte must match. The launcher additionally binds source
SHA256, bank hash, record index/ID/type, exact component path and unambiguous
ownership. Overlapping binary component modifications reject rather than merge.
Native `Folder::bank` already preserves fixed component bounds and regenerates
compatibility headers while leaving the guest loader responsible for resources.

API name is deliberately `cloth.positions`, not arbitrary `SCNE.replace`.
Split GPU-backed geometry, quantized positions, arbitrary model replacements,
new topology and universal FBX/glTF importing are unsupported. New code is not
claimed to have passed Studio's corpus tests; those results describe Studio's
separate implementation and serve only as research input here.

## Uniform identities and registration boundary

`uniforms.py` maps active roster owner/artwork/variant fields and resolves world
and selection names through uppercase-ASCII CRC32. API 1.1 checks both hash
identities against the installation and requires all linked asset dependencies
to be selected. Mixed DDS/cloth+native roster packages activate as one unit.

Native `folder.h::augment` can register checked template-based uniform banks;
Studio has offline cloning/routing evidence. That is insufficient to certify a
new package-level bank writer or all native roster/save ID relationships. The
package API still rejects missing uniform banks and has no arbitrary bank import.
Additional jersey registration is a documented blocker, not an invented new ID
allocator. Native source tools having a low-level mechanism does not make every
new resource safe for runtime use.

## Hook architecture: corrected, more precise findings

The pinned SDK **does** expose dynamic
`FunctionDispatcher::SetFunction(uint32_t guest_address, PPCFunc*)`, and updates
its dispatcher map plus Memory's module function table. It rejects addresses
outside registered modules. `rex/hook.h` defines `REX_HOOK` using typed
`HostToGuestFunction` marshaling and `REX_HOOK_RAW` for direct context/base access.
`rex/ppc/function.h` defines PPC register/stack argument translation. These are
real source APIs, not evidence of a stable package ABI or a verified gameplay
hook point.

Generated code also makes static calls. For example,
`port/generated/default/ch2k8_recomp.103.cpp` contains guest call `84D33D60` to
`84DCB0C8` as the direct native call `sub_84DCB0C8(ctx, base)`, bypassing a
dispatcher lookup. The generated register/init files separately register
`sub_84752968` at guest `84752968`; its body loads the word at `r3+140` and
returns a rotated/masked nine-bit value in r3, agreeing with Studio's weight
field evidence. This does not establish that a dispatch-table replacement would
intercept every direct call or safely change a Legacy/scorebug function.

Existing `config/perf_hooks.toml` mid-assembly probes at guest `84DCB314` /
`84DCB318` bracket VdSwap. Their no-register host callbacks in `frame_timing.cpp`
are timing diagnostics. They are not scorebug selectors or gameplay hooks.
No verified Xbox scheduling/recruiting/tournament/scorebug/menu contract was
found in the symbol records or existing research reports searched. No PS3 or
other-title function address was promoted into this game.

Therefore package code remains rejected; no unsandboxed DLL is loaded. A future
point must prove its game purpose, calling convention, arguments, ownership,
thread/lifecycle and direct/indirect coverage, then receive source/codegen
integration before a dynamic mod may register it. Optional DLL support still
needs an explicit user opt-in and minimal versioned ABI. Guest PPC addresses
must not be treated as native x64 patch locations. See `hook_registry.json`.

## Cache/update implementation and evidence

Native `materialize` immediately skips banks already containing `blocks` or
`loose_segments`. `Folder::bank` reads decoded components and generates headers
under `_runtime`; this is the source basis for linking only pre-decoded
`blockN.dat` files in standard `blocks` banks. Metadata, DDS and other/migrating
payloads are independent copies. Every staged replacement unlinks its target
before writing. A prepare lock serializes preparation, and old receipt-bearing
GUID caches are collected after a new publication. Cross-volume/denied hardlinks
fall back to copies. This reduces D: duplication without changing source files;
hardlink isolation and cleanup behavior still require user acceptance.

GitHub release updates now have bounded downloads, source URL/size checks,
package ID/tag matching, ordinary package/resource checks, native preparation
before switching an enabled asset update, immutable version
installation, settings backup and atomic selection switch with a stale-settings
hash guard. Failed updates remove only their newly installed version. The
previous installed version and isolated save profile remain available. Download
and rollback logic has not been run. No custom hosting or code update loader.

## Build and test record

The native launcher tool was compiled using the existing Microsoft x64/LLVM
toolchain, without SDK rebuilding and without running the produced program.
Build outputs are in the larger C: writable workspace, not another D: game copy.
`ch2k8_tools.exe` in the current runtime is replaced only after compilation.
Compiler diagnostics included the pre-existing `std::filesystem::u8path`
deprecation warning. This is a build result, not a validation or gameplay claim.
The beta packager now accepts the retained portable runtime/CRT/controller files
as its default source after D: cleanup, without restoring duplicate build trees.
It includes the current schema, evidence, status and acceptance documents.

`tests/test_chmod_contracts.py` adds synthetic roster/header rejection cases,
cloth position/non-position rejection and isolated-profile preservation/reuse
cases. These tests are **written but not run**. Existing native tool discovery
was adjusted to find the retained portable tool after D: cleanup. API 1.0's
historical 68-passed/one-skipped result must not be reported as current coverage.

Before the user's stop instruction, the isolated baseline game reached a window
and encountered a Windows Firewall prompt. That is not a baseline gameplay,
edited-texture, roster-load or hook acceptance result. The prompt was not acted
on by the agent; the test process was closed. No gameplay evidence is claimed.

## Original deliverable status

| Requested step | Current result |
| --- | --- |
| 1: research/specification | Published current schema, identity rules, primary sources and blockers |
| 2: install/discovery/launcher | Backend implemented; 1.1 controls/recovery need user acceptance |
| 3: texture replacement/restore | Historical isolated DDS proof; current code and live visual acceptance pending |
| 4: source-compatible resources/new jerseys | Narrow cloth-position backend implemented; new uniform registration blocked |
| 5: native roster/Dummy HDD | Actual save/header researched; isolated exposure backend implemented, not live verified |
| 6: executable hooks/extensions | Real SDK mechanisms researched; game-specific contracts/direct-call coverage blocked; code rejected |
| 7: mixed/update/recovery/baseline | Source/tests/checklist supplied; user reserves all remaining execution |

This record does not mark the full game-specific wishlist complete. It identifies
the supported implemented subset and the precise evidence gates that remain.
