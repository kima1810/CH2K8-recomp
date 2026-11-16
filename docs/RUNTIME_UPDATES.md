# Launcher runtime updates

The existing launcher has **Update from GitHub** and **Rollback update** buttons.
Players need no Python/compiler. Updates fetch prebuilt public Windows x64 releases
from `kima1810/CH2K8-recomp`, pinned repository ID1411943368. This beta launcher
includes published prereleases. Drafts and source archives are excluded. The most
recent published release is selected, then its most recently updated matching
`CH2K8-...-Windows-x64-....zip` asset (historical builds may share one release).

## Player behavior

Click Update from GitHub while the game is closed. The launcher shows background
worker progress, verifies the ZIP's GitHub SHA256 digest and exact size, safely
extracts it, verifies every SHA256SUMS entry, checks PE32+ x64/import dependency
closure and compares game/update/mod-API/ABI/capabilities before activation.
It does not execute the downloaded verifier, DLLs or game during verification.

A verified complete runtime is installed under
`port/userdata/runtime-updates/releases/<archive-sha256>/`. An atomic `current.json`
pointer selects it. Original installation/source files are not overwritten.
Assets, mods, launcher settings, native saves and isolated profiles remain in the
original installation root. Managed launches use the selected runtime's executable,
helpers and scripts. Shared logs remain under the installation's logs directory.
Saved source-build executable paths do not override an activated managed update;
explicit command-line executable overrides remain available.

The updater reopens the launcher after a successful update/rollback. **It never
launches the game.** It refuses to activate while ch2k8 is running and never closes
processes or dialogs. A launch/update lock prevents normal launcher races.

Rollback swaps the active and previous runtime pointers. The original installation
is the first rollback target. Released runtime directories are retained; no user
files are deleted. Both current and prior release payload hashes are checked before
selection. If startup cannot verify the active release, the stable bootstrap opens
the original launcher with a recovery notice. Use Rollback update there.

Updates preserve every currently advertised native capability/ABI and cannot lower
mod API. An older public ZIP therefore cannot replace a newer local SDK build.
Rollback is explicit and may select an older runtime; mods requiring newer APIs
will then need disabling or a compatible runtime. Existing mod permission and
Launch without mods recovery policies remain in force.

Download/hash/metadata/extraction failures do not commit current.json. Publication
writes previous.json before atomically changing current.json; an interruption
before the final pointer commit leaves the old runtime selected. Runtime files are
never patched in place. Updater jobs retain logs and failed downloads for diagnosis.
This is update rollback, not recovery from arbitrary native crashes or malicious
code. GitHub publisher/TLS trust and SHA256 integrity are not a signing/sandbox claim.

## Publisher contract

`tools/package_beta.ps1` includes the updater, stable bootstrap, static PE reader,
canonical CHMOD schema/inventory, complete matching runtime and CRT, optional SDK
source and legal notices. When a compatible runtime receipt exists it writes:

```json
{"format":1,"bootstrap_protocol":1,"platform":"windows-x64","package_type":"runtime","xex_sha256":"71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36","mod_api":"1.3.0"}
```

File: `runtime-update.json`. The matching `chmod-runtime.json` must bind the actual
exe, game revision and native capabilities/ABIs. `beta-version.json` must identify
a Windows runtime without game data and agree with core binary hashes. Include an
exact SHA256SUMS.txt covering all files except itself. One optional portable wrapper
directory is accepted. GitHub supplies the outer asset digest on upload; assets
without that SHA256 digest are rejected. Generated ZIP names match the selection
pattern. Publish a new release or upload a new complete ZIP; no custom host is used.

Only runtime root binaries/metadata/controller/legal files and tools/docs/sdk/
licenses/examples directories are permitted. Game assets, default.xex, port/, mods/,
settings or save payloads cannot enter the runtime overlay. Paths reject traversal,
ADS, Windows devices, reparse/symlink entries, case collisions and undeclared files.
Limits: 512MiB download, 256MiB/file, 2GiB expanded, 12000 entries, bounded ratios,
HTTPS GitHub/CDN redirects only, bounded network timeouts. Canonical repository
identity is checked before querying releases.

The original root bootstrap remains stable and uses protocol1 / InstallationRoot
handoff; new launcher versions must preserve that protocol. A future incompatible
bootstrap protocol needs an explicit installer/transition rather than silently
executing unknown update formats. Header-only SDK/tooling changes alone do not
require a game runtime update.

## Research and verification boundary — 2026-11-08

GitHub metadata research identified the renamed official repository and release
`ZMO-beta1-20261106` (prerelease), with Windows asset
`CH2K8-ZMO-beta1-Windows-x64-1caa20d.zip`, ID721852621, 20,186,338 bytes,
SHA256 `3d395aed79d5151e361031219f376d7ea3a43ff4c2f16a1f398328792365ab92`.
Multiple historical Windows assets exist under that release; newest asset selection
is deliberate. This published build predates the current updater/SDK1.3 contract,
so it can be downloaded but will not be installed over this checkout. A new
updater-compatible release must be published before automatic activation is usable
with that public release feed. No new GitHub release was published by this task.

Implementation and static source parsing only. No updater, launcher UI, downloaded
binary, game, native verifier or tests were executed by the agent; no saves changed.
Prepared synthetic tests: tests/test_runtime_updater.py. Runtime behavior and
rollback remain for remote user acceptance.

## Remote acceptance checklist (unrun)

- Check release metadata selection: current public beta, multiple historical assets,
  drafts, source-only latest release, rate limits, missing digest and offline errors.
- On a disposable installation with a compatible synthetic/test release, install
  and confirm helper/scripts/exe all come from one runtime, while original source,
  game files, mod selection, native opt-in, profiles, settings and saves stay intact.
- Reach the update button once: progress remains responsive; success reopens only
  the launcher. Current/previous pointers and digest manifests agree.
- Reject digest/size/checksum corruption, missing protocol/receipt/dependency,
  wrong architecture/game, unknown protocol and capability/API/ABI downgrades.
- Reject traversal, ADS/device names, symlinks, case collisions, extra/protected
  files and decompression limits, with no current pointer or user-file changes.
- Interrupt download/extraction and interrupt before/after pointer commit; startup
  must select a complete verified old or new runtime, never partial binary mixes.
- Roll back to the original and then forward to the installed release. Test a bad
  active hash: bootstrap should open original launcher for recovery.
- While a game is running, update/rollback must stop without closing it or a popup.
  Test two updater instances and launch/update contention. Check stale lock files
  are harmless after process exit.
- Verify SDK/mod-enabled and Launch without mods flows after a compatible update.
  Test explicit rollback to an older API reports unsupported mods actionably.

Static inspection additionally read PE import tables from the current runtime,
SDK DLLs, helper and four distributed CRT files. Their CRT imports close over the
existing four-file CRT bundle; no binary was loaded/executed. Changed PowerShell
files passed AST parsing, and prepared Python tests compiled in memory without
execution. No update was downloaded/applied to this installation; the button's
worker and GUI were not run. Source implementation is ready for remote acceptance.
