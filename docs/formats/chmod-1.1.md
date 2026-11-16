Historical profile; see [current API 1.2](chmod-1.2.md).

# CHMOD schema 1, mod API 1.1.0

Current specification for the existing Windows launcher. The required `mod.json`
and payloads live in one ZIP-compatible `.chmod`, or the same unpacked folder.
There are three conceptual content classes: assets, native rosters/saves, and
executable extensions. This implementation admits the researched asset/roster
subset below and **rejects executable content**, including mixed packages that
declare it. Legacy is never a fourth content class.

API 1.1 additions are **Researched; implemented and compiled, verification
pending**. The user stopped agent-run testing and reserved acceptance for remote
testing. Earlier API 1.0 results do not validate the new implementation.

## Manifest

Use [chmod.schema.json](chmod.schema.json) plus the semantic rules here.
Retain schema version `1`. `requires.mod_api` is `1.1.0` for new capabilities;
`1.0.0` DDS packages remain accepted. `requires.recomp` is `ZMO-beta1` and the
supported USA retail XEX SHA256 is
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.

Required fields: `schema_version`, unique `id`, `name`, `author`, numeric-release
SemVer `version`, `requires`, `content`, `capabilities`, `dependencies`,
`incompatible`, and `assets`. Optional fields: `roster`, `update_source`.
Unknown keys reject. Content/capability arrays must exactly describe the payload:

| Content | Capability | Contract |
| --- | --- | --- |
| `assets` | `dds.replace` | Existing Xbox TXTR DDS template replacement |
| `assets` | `cloth.positions` | Existing single-component CPU SCNE, only verified float3 positions |
| `rosters` | `roster.expose` | Actual native `Roster.ROS` plus its SDK aggregate content header |

`assets` is an array, possibly empty for a roster-only package. `content` contains
`assets` iff that array is nonempty and `rosters` iff `roster` exists.
Capabilities are the unique exact set used by those entries. No empty package.
Versions have three nonnegative numeric components without leading zeroes,
suffixes or ranges. Dependencies pin exact ID/version pairs, cannot cycle or
repeat IDs, and must already be selected. Incompatibilities block activation.
Enabled state, selected version and low-to-high priority belong only to launcher
settings. Installed versions are immutable; reinstallation of a version refuses.

Each asset has `bank_hash`, `record_index`, `record_id`, `record_type`, `target`,
`source_sha256`, package-relative `file`, and replacement `sha256`. These are
actual imported Xbox bank/record identities; filename-only addressing is invalid.
Integers are unsigned 32-bit JSON integers, not hexadecimal strings or floats.
The optional `kind` defaults to `dds.replace` for API 1.0 compatibility.

### DDS

`record_type` is `0x5c369069` / `1547079785`. `target` must exactly match
`assets/<catalog-bank>.iff/<catalog-record>.txtr/texture.dds`. `file` is a DDS
under package `assets/`. The imported template SHA256, live DDS SHA256 and
`source_sha256` must agree. The bank's decoded component digests must still match
its original metadata. Native preparation enforces supported 2D BC1–BC5 formats,
aspect, integer power-of-two upscales, bounds, mip payload and original pixel
identity rules. D3D12 is required. Existing fence/cache ownership is unchanged.

Priority resolves only multiple DDS replacements for the same owner target.
Different bytes for one canonical original pixel identity across different owners
still reject, including collisions with untouched templates. An owning IFF is
not yet tracked at renderer bind time. Priority never bypasses this restriction.

### Source-compatible cloth SCNE

Set `kind: "cloth.positions"`, `component: 0`, and SCNE `record_type`
`0xe26c9b5d` / `3798768477`. `target` must be the owning record's imported
`...scne/block0.dat`; payload `file` is under `assets/` and ends in `.dat`.
Exactly one CPU block/record extent and one unambiguous owner are required.
The replacement must retain its exact size and source digest binding.

`ch2k8_tools validate-cloth ORIGINAL REPLACEMENT` bounds-checks the source mesh
table, 176-byte mesh records, 24-byte CPU stream descriptors, declarations,
source indices, counts and strides. Only unquantized Xenos format 57 float3
positions are writable, on word-aligned streams. Replacement coordinates must
be finite with absolute value less than one million. Every other byte must be
identical: topology, draw runs, materials, counts, declarations, UVs, normals,
transforms and opaque data. Shared component owners and overlapping component
mods reject; binary edits never use priority merging. This is not a universal
SCNE writer, arbitrary mesh import, GPU-scene editor or topology-changing API.

### Native roster save

Add `roster` with `file`, `sha256`, `header`, `header_sha256`:

```json
{
  "file": "rosters/Roster.ROS",
  "sha256": "<actual lowercase SHA256>",
  "header": "rosters/Roster.ROS.header",
  "header_sha256": "<actual lowercase SHA256>"
}
```

Placeholders above are explanatory and are not valid manifest values. A loose
ROST component cannot merely be renamed as a save. Supply an actual compatible
native save and its own content header; do not fabricate header/profile data.
The observed native payload starts with a big-endian 32-bit byte length equal
to the remaining payload. The remaining body uses the Xbox dynamic ROST table
relationships; there is no ZIP/STFS wrapper inside this observed file.

The pinned SDK header is exactly `sizeof(XCONTENT_AGGREGATE_DATA) == 0x148`
(328) bytes. Native validation requires Dummy HDD device 1, saved-game type 1,
filename `Roster.ROS`, neutral aggregate XUID 0, title `54540818`, correct length
wrapper and bounded Xbox tables/strings. It checks players, teams, coaches,
arenas, conferences, uniform rows, team membership uniqueness, reciprocal
conference membership, uniform slot uniqueness and current variant/shape bounds.
No editing of unrelated bytes is performed. Additional/unknown roster field
semantics, face/model validity and persistent Legacy migration are not inferred.

Roster uniform packing is read from the native rows: owner bits 22..31, artwork
ID bits 12..21 and variant bits 8..10 of the first big-endian word; shape bits
27..29 of the second. Variants 0..4 map to `h,a,x,y,z`; world names are
`u<prefix><artwork at least three digits>.iff` and selection names prepend `sel`.
Hashes use the existing uppercase-ASCII CRC identity. Both referenced bank hashes
must exist uniquely in the active installation. **New uniform registration is
not exposed**; a missing route rejects rather than inventing a bank/ID. A mixed
asset+roster package activates/deactivates together and its dependency set must
be selected completely. Appearance references beyond this uniform contract still
need consumer-level evidence and acceptance testing.

At most one active native roster is allowed. It is exclusive even when two
packages contain identical bytes; user priority does not select a roster.

## Dummy HDD isolation and rollback

The SDK derives paths under the supplied user-data root:
`<XUID:016X>/<title:08X>/<type:08X>/<package>/<inner-file>`, with headers in
`<XUID>/<title>/Headers/<type>/<package>.header`. The current pinned SDK's default
profile is `B13EBABEBABEBABE`; this is read from `UserProfile::UserProfile`, not
author-controlled manifest input. Current roster exposure therefore uses:

```text
<isolated-root>/B13EBABEBABEBABE/54540818/
  00000001/Roster.ROS/Roster.ROS
  Headers/00000001/Roster.ROS.header
```

`New-ChmodRosterProfile` stages these files under `port/userdata/mod-profiles`,
copies only existing Settings/User data and headers, and snapshots any original
roster pair into `baseline-backup`. Original user-data files are never overwritten.
It publishes the profile by rename, then the launcher supplies it through
`--user_data_root`. It does not automatically select the roster in the game's UI.

The entire ordered mod selection and resolved asset/roster hashes determine
the profile key. The same coherent set reuses its persistent profile without
reinstalling over game-created changes. A mod update or changed linked asset set
gets a fresh profile. Older profiles remain for rollback; **no existing Legacy
save is copied, overwritten, migrated or automatically exposed**. New Legacy saves
created by the player in a mod profile remain there. Return to that exact mod
set to access them. Disabling mods returns to baseline saves. Generalized profile
selection and save migration are outside this API.

## Preparation, storage and recovery

The launcher resolves a complete selection before launch. Asset metadata and
generated runtime headers are prepared privately. Native `prepare` and the
existing runtime scatter-map/DDS mechanisms perform loading; no game executable
rebuild is needed for these data mods. `chmod-lock.json` records versions,
resource winners/conflicts, baseline and roster selection.

To reduce duplicate data on D:, only existing decoded `blockN.dat` files in banks
already containing `blocks` metadata may use same-volume hardlinks. Native
`materialize` skips these banks and native `Folder::bank` reads their component
bytes while writing generated headers solely under private `_runtime`. Metadata,
DDS, opaque/possibly migrating payloads and all other preparer inputs are copied.
Before applying any replacement the staged target is deleted and replaced by an
independent file; source component bytes must never be written through a link.
Cross-volume or denied links fall back to copies. Do not edit installation files
or prepare caches while the game runs. This optimization is untested in 1.1.

Preparation holds an exclusive `prepare.lock`; a failed stage is removed and no
game starts. Following successful publication, old generated GUID caches with
recognizable receipts are removed on a best-effort basis. Arbitrary folders and
persistent roster profiles are retained. At most the newest successfully prepared
cache is normally retained; failures/denied deletions may leave older caches.
Use `-ModCacheDirectory PATH` to place preparation on another drive. The normal
launcher defaults to `port/userdata/mod-cache`. Baseline files remain intact.

**Launch without mods** / `-Launch -WithoutMods` bypasses package discovery,
selection and mod profiles, including corrupt mod settings. It does not undo
pre-existing manual changes to base assets. A native contract failure blocks the
complete package, not just its failing content class.

## Updates

An optional author `update_source.url` points to
`https://github.com/OWNER/REPO/releases`. Check update reads the latest release;
its tag must be `MAJOR.MINOR.PATCH` or `vMAJOR.MINOR.PATCH`, with exactly one
`.chmod` asset. Its URL must belong to that repository's release-download path.
Ambiguous multi-mod releases require manual installation.

Install update streams at most the declared release size and 512 MiB, with a
120-second transfer budget and network timeouts, then uses the ordinary untrusted
package installer. ID/version must match the selected mod and release tag.
If enabled, the replacement selection is resolved and its asset cache is natively
prepared before settings switch. The game must be closed. An inactive update is
installed with package/integrity checks; its source/native activation checks apply
when enabled. This permits installing an inactive package whose dependencies are
not yet selected without silently enabling those dependencies.
`mods.previous.json` backs up the previous settings; settings publish atomically
with a stale-settings hash check. On failure the newly installed version from
that transaction is removed and the old version/selection is retained. On success
old versions remain selectable; roster profiles are not migrated. Asset
preparation also remains a launch-time validation gate. Manifest hashes detect
corruption, not author authenticity. No code/DLLs are loaded from an update.

## Untrusted input and remaining work

The existing path, duplicate-key, JSON depth, package file declarations, file
count, expansion-ratio, streaming-size and SHA256 protections remain. New roster
payloads are capped at 64 MiB and headers at 328 bytes by the native contract;
cloth inputs are capped at 64 MiB. The package cap is still 512 MiB. Relative
paths never choose an executable, XUID, content type, arbitrary patch address or
destination outside the package/cache. No normal player needs Python or a compiler.

Gameplay/Legacy/menu/scorebug hooks, native DLL extensions, new jersey bank
registration and generalized SCNE overwrites remain blocked by evidence gaps.
See [the current evidence record](../findings/2026-11-08-chmod-backend.md) and
[user acceptance checklist](../CHMOD_ACCEPTANCE.md). No 1.1 feature is in-game
verified or represented as having passed tests.
