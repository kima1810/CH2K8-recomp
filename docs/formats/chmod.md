Historical profile; see [current API 1.2](chmod-1.2.md).

# CHMOD 1: source-bound Xbox DDS packages

**Historical API 1.0 notes.** Current authoring and launcher behavior is specified
in [CHMOD API 1.1](chmod-1.1.md). The shared JSON schema now describes 1.0/1.1.
The 1.1 work adds bounded cloth edits, isolated native roster exposure, bounded
update installation and revised cache handling. Those additions are **Researched,
implemented, verification pending**, not covered by the test results below.
The user requested that no further tests or game launches be performed.

This is the first functioning subset of the modloader, **Validated** with
synthetic data, not **In-game verified**. The evidence and deferred work are in
[the implementation status](../findings/2026-11-07-chmod.md). Studio should export
only the capabilities in the [schema](chmod.schema.json). There is one container
format; future roster/hook support must extend its versioned capability contract.
API 1.0.0 accepts assets only and rejects unsupported or mixed content as a whole.
It does not silently activate just the asset portion of a roster/hook package.

## Container and manifest

A `.chmod` is a ZIP with `mod.json` at its root and the exact declared DDS payload
files under `assets/`. No outer enclosing directory. Empty directories are
permitted. A development folder has the same layout, either imported through
Mods or placed at `mods/<id>/mod.json`. Installed packages use immutable
`mods/<id>/<version>/mod.json` directories. Installing an already installed version
fails; publish a new semantic version. Only one version of an ID may be active.

Manifest keys are case-sensitive. Unknown fields reject. Versions use the
SemVer numeric release subset `MAJOR.MINOR.PATCH`, with no leading zeroes,
prerelease/build suffixes, or version ranges. Dependencies pin exact versions,
must be explicitly enabled, and must form an acyclic graph. No implicit enabling.
Incompatibilities are symmetric in effect even if declared by only one mod.

Required metadata: schema version 1, ID, name, author, semantic version,
`requires` (XEX SHA256, recomp `ZMO-beta1`, mod API `1.0.0`), content `['assets']`,
capabilities `['dds.replace']`, dependencies, incompatible IDs, and assets.
The JSON schema describes structural validation; the checks below are mandatory
in addition to schema validation. UTF-8 JSON; metadata maximum 1 MiB.
Duplicate keys (including escaped aliases), trailing commas and nesting deeper
than 32 containers reject. Selected banks' decoded component SHA256 values
must still match their imported metadata as well as the original DDS template.

An asset identifies its **existing** bank hash, record index, record ID, and
record type as unsigned 32-bit JSON integers. TXTR type is `0x5c369069`
(`1547079785`). Obtain these from the imported Xbox installation's `assets.json`
entry and that bank's `asset.json` records. The index disambiguates repeated IDs;
the ID/type also have to match. Do not derive an ID from replacement filenames.

`target` must exactly equal the catalog bank folder + record folder +
`/texture.dds`. A corresponding `textures` entry must exist.
`source_sha256` must match both its exported-template SHA256 and the live baseline
DDS file. `file` addresses the replacement inside the package; `sha256` checks
its exact bytes. Metadata and filenames are never copied from a package into the
game installation. Shared TXTR owners are not independently addressable at GPU
upload time: the native preparer rejects differing DDS bytes for one original
width/height/format/pixel identity, including collisions with untouched templates.
Priority cannot override this rejection. Identical artwork for every shared
owner is the existing loader's supported policy.

Supported retail XEX SHA256:
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
There is no production launcher switch to bypass this check. The backend's
`ExpectedXex` argument exists for isolated synthetic tests, not package metadata.

## Resolution and activation

Open **Mods...** in the existing launcher to install a package, import a folder,
enable/disable a version, and move it higher/lower in priority. The numeric
priority shown in the list is authoritative; larger numbers win. Settings live
in `port/userdata/mods.json`, never in packages:

```json
{"version":1,"enabled":[{"id":"author.art","version":"1.0.0"}]}
```

The enabled list is ordered low to high priority. Multiple replacements of the
same exact resource produce a conflict report with the higher-priority winner.
Missing dependencies, wrong versions/revisions, unsupported content, ambiguous
identities and declared incompatibilities block launch. Missing/invalid installed
packages fail closed; **Launch without mods**, or `-Launch -WithoutMods`, bypasses
discovery and mod settings entirely, including corrupt settings.

On launch, the launcher resolves again and copies the loose installation's
assets and loader metadata to a unique private staging directory under
`port/userdata/mod-cache`. It copies files independently, never using hardlinks.
Only resolved DDS targets are replaced. Existing `ch2k8_tools.exe prepare` performs
native validation and emits runtime maps/catalogs. It checks BC format, aspect,
power-of-two upscales, bounds, mips, original identities and conflicting shared
textures. D3D12 is required. Existing runtime lifetimes and cache behavior apply;
restart for changes. No runtime binary rebuild is required.

Only successful preparation publishes a cache by directory rename. The runtime
receives its root through existing `--game_data_root`; the GPU catalog uses the
same root via `CH2K8_ASSET_ROOT` from `OnPreSetup`. `chmod-lock.json` records the
ordered active versions, resolved resource winners and conflicts. Its ordering
and resolution are deterministic; the output directory name is unique per run.
The existing Dummy HDD/user-data root is retained.

Disabling every mod launches the original installation. Original assets are
never overwritten by mod activation. Failed preparation discards only its own
stage; published older caches/versions remain. A full copy per modded launch
uses additional disk space and can take time. Cache reuse/automatic collection,
parallel launcher writes, hot reload, and crash-stage cleanup are not implemented.
Delete obsolete mod-cache folders only while the game and launcher are closed.
Use a pristine baseline; the mod layer does not restore pre-existing manual edits.

## Updates and rollback

Optional `update_source: {"url":"https://github.com/OWNER/REPO/releases"}`
identifies an author-controlled release page. **Check update** reads that repo's
latest GitHub release tag, accepting `1.2.3` or `v1.2.3`, and reports it alongside
the installed version. Tags do not prove that a release contains this mod.
Download its `.chmod` and use Install; the same untrusted-data validation applies.
There is no automatic download, custom hosting, or automatic version selection.
Enabling the newly installed version replaces that ID's prior selection only
after dependency/resource validation. The old directory is retained; enable its
version to roll back. Settings writes use atomic file replacement. Runtime DDS
validation still occurs at launch; failure leaves the original installation
intact and recovery launch available. Package SHA256 values detect corruption,
not author authenticity or a malicious author's intent.

## Untrusted-data limits

Packages: at most 8192 entries, 4096 replacements, 512 MiB compressed package and
total expanded payload, 128 MiB per expanded ZIP entry or DDS. ZIP entries over
1 MiB cannot exceed a 200:1 expansion ratio; streamed output is checked against
declared size and the per-file bound. Paths use ASCII letters/digits, `_-.` and
`/`, maximum 220 characters, with no empty/dot/dot-dot segments, trailing dots,
Windows device names, backslashes, ADS, drive/UNC paths or case-colliding entries.
Symlinks, reparse points, special ZIP files, undeclared files and duplicate
resource targets reject. Resolved paths are checked for ancestor reparse points.
Import into a descendant of the source folder rejects. Payload hashes are checked
at import, discovery and immediately before copying. Preparation is completed
before the game is started. Deliberate concurrent mutation by another local
process is not a security boundary; keep imported folders closed during launch.

## Future content and Studio interoperability

No roster/save schema or path is invented here. A loose ROST component is not a
native roster save. No mod writes Dummy HDD or Legacy saves. Base-roster changes
must never be presented as migration of an existing Legacy. Conference alignment
belongs to native roster relationships; scheduling/recruiting/simulation are
executable behavior and persistent-save research, not a fourth content class.

SCNE overwrites, additional jersey registration/roster linkage, native save
installation, gameplay/Legacy/menu/scorebug hooks and DLL extensions are currently
rejected. Existing developer asset tools support more low-level operations than
this package API. Their structural checks do not establish semantic compatibility
or live gameplay. Future versions must add researched identity/ownership rules,
validation and acceptance evidence before exposing those capabilities. Native DLL
support will need explicit unsandboxed-code opt-in and a versioned ABI; no DLL is
loaded by this implementation. Guest PPC addresses are never native patch addresses.


## Mod folders

Place a folder under `mods/` or choose **Install mod folder** in the launcher.
A mod folder has a `mod.json` file at its root. The manifest identifies the mod
and version and records requirements, dependencies, optional description and
asset digests. Store replacement DDS and scene components under `assets/`
using the named paths from the installation. Studio exports this layout.

For a named DDS entry, `texture_slot` identifies the catalog slot together
with the bank hash and record identity. The payload path mirrors the target.
The runtime checks the original digest and applies the DDS during staging.
A named texture and a whole-scene override for the same record conflict.
Legacy archives and installed version folders remain importable.
