# User-run CHMOD acceptance checklist

The agent must not open the game or run these checks. The user reserved remote
verification. API 1.1 is researched/implemented, not tested or in-game verified.
Use the retained current runtime and one game installation; put temporary test
outputs/cache on C: with `-ModCacheDirectory PATH` to avoid refilling D:.

1. Preserve a private copy of your saves. Confirm Launch without mods shows the
   same baseline assets and saves, including with malformed mod settings.
2. Install the supplied synthetic `.chmod` through Mods. It is an install/schema
   example, not a retail-game cosmetic mod: its synthetic revision must reject
   on retail activation. Import the same unpacked structure separately.
3. Use Studio to export a known existing TXTR's source identities and authored
   DDS. Package those exact identifiers/hashes using the schema. Enable, launch,
   select the known asset, observe `Native DDS upload` and the intended visible
   owner in menus/gameplay/replay. Disable and compare baseline. Verify original
   template/component hashes did not change.
4. Exercise DDS priority with two replacements of one owner. Exercise shared
   original pixel identities in two different owners: differing replacements
   must reject even if one owner is untouched. Check formats, mips and sizes.
5. For `cloth.positions`, use Studio's source-bound embedded-cloth position-only
   writer. Package the exact CPU component. Confirm original topology/UV/material
   bytes remain unchanged and only intended finite positions differ. Changes to
   counts/indices/non-position bytes and overlapping owners must reject. Check
   the model live; do not call an offline preview gameplay verification.
6. For `roster.expose`, use an actual compatible native `Roster.ROS` and its
   actual SDK header, not a renamed IFF component. Confirm native validation and
   existing uniform world/selection identities. Enable alongside linked artwork.
   Launch must use an isolated mod profile. Select/load the roster in the game;
   confirm players, teams, conferences, assignments, appearances and uniforms.
   Existing baseline Legacy saves must remain untouched and unexposed there.
7. Save/reload a disposable roster and a newly created disposable Legacy in the
   isolated profile. Re-enable the same complete mod set to confirm persistence.
   Change a linked asset or version: a fresh profile must appear, with no Legacy
   migration. Return to the previous set/version: the old profile must remain.
   Disable mods: baseline rosters/Legacy saves must be unchanged.
8. Exercise author GitHub release update identification and Install update, then
   select the prior version for rollback. Test wrong IDs/versions, truncated or
   oversized downloads, bad hashes, missing dependencies, exclusive rosters,
   unsupported code/DLL content and failed preparation. Old settings/version/
   profiles must remain accessible; the whole failed package must stay inactive.
9. Confirm old prepared caches are collected only after successful publication.
   For linked `blockN.dat`, compare baseline hashes before/after preparation,
   disable, a failed preparation and update. Cross-volume caches must copy safely.
   Keep the game closed while preparing or editing. Never alter a linked source
   in-place during play.

Optional developer checks (also user-run only): the synthetic tests in
`tests/test_chmod.py`, `tests/test_chmod_contracts.py`, `tests/test_launcher.py`,
and `tests/test_native_asset_tools.py`. Use pytest `--basetemp` on C:. Ordinary
players do not need Python or compilers to install/load supported data mods.

Record the runtime/source/XEX revision, package hashes, GPU/renderer, exact steps,
result, log excerpt and screenshot reference for each acceptance. Promote a
capability to **In-game verified** only after the corresponding observed success.
Do not test guessed new jersey IDs or executable hook addresses: those APIs
remain unsupported pending research.

## API 1.2 user acceptance (not run by agent)

- Register a user-authored world/selection uniform pair with an isolated native
  roster; confirm menu availability, both previews, in-game artwork and save/reload.
  Reject occupied IDs, wrong template hashes, unmatched pairs, missing team owner,
  nontexture edits, shared/private pixel collisions and unsupported formats.
- Install the native-weight example without opting in: launch resolution must
  reject code. After explicitly opting in, use only the isolated profile and check
  the dispatch log and observed getter behavior. No claim of physics changes.
- Reject wrong DLL architecture/hash/ABI, missing runtime receipt, a second
  exclusive registration, and data-only updates that introduce native code.
- Confirm mixed assets/roster/code select together; disabled/recovery launch uses
  baseline assets and profile, including after a native extension failure.
- Confirm existing Legacy saves remain untouched, and code or asset changes select
  a separate profile identity. Preserve user-created saves during update/rollback.

API 1.2 has compiled only. Record actual observations, game revision and failures
before promoting any capability to Validated or In-game verified.

- For automatic activation, use a valid additional `uxNNN.iff`/`seluxNNN.iff`
  pair whose NNN matches a team's Home/Away art in two disposable named rosters.
  Confirm both rosters gain Alternate 1, preserve team/player data, and render it.
  Disable and launch again: confirm byte-identical originals and unchanged headers.
- Add a roster under a second disposable XUID; confirm matching/neutral header
  identity and all-roster discovery. Reject bad header/body, missing pair,
  ambiguous art owner and a conflicting alternate slot without partial activation.
- Interrupt activation between file commits; next launch should restore from the
  journal. After editing a managed roster, switching must stop without overwriting
  the edit. Keep backups before testing this intentionally conservative limit.

- With no jersey mod folders, normal launch should expose existing vanilla jersey
  rows and catalog-backed missing alternates. Confirm Home/Away/Alternate artwork
  falls back to the original game. Recovery launch must restore original save bytes
  and bypass unlocking. Verify actual menu gating and save/reload independently.

ABI 2 framework acceptance is now maintained in [sdk/ACCEPTANCE.md](../sdk/ACCEPTANCE.md).
The prepared tests and neutral DLLs compiled but were not executed. The game and
user saves were not opened/modified. API1.3 inventory is the current capability set.
