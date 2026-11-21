# CH2K8 Recomp backlog

This is the target scope for the recompiled game, Modding Studio, and the shared CHMOD DLL. Unchecked items are open, including items with a prototype or partial implementation. The [modding policy](MODDING_POLICY.md) governs packaging, testing, and releases. Recomp editing uses [CHoops Extractor Reborn Recomp](https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp/tags).

## Base decomp

- [ ] **Optimization** (ZMO). Profile and improve the baseline recomp as part of runtime development. Use comparable frame-time and loading measurements and include regression checks with runtime releases.

## UI and visuals

- [ ] **Reborn overrides.** Port supported replacements into source-bound asset overlays. Add a shared DLL feature wherever an override needs live game logic.
- [ ] **Scorebug selector in Presentation.** Verify the existing DLL preview in game, including menu interaction, style persistence, and live HUD values. Move style artwork, geometry, layout, and bindings into data packs.
- [ ] **Full-court SCNE port.** Extend Studio's supported court conversion and validate paired CPU/GPU scene components. Verify lighting, markings, and geometry live.
- [ ] **Shorter shorts model port.** Preserve the corresponding cloth simulation constraints and validate the model in motion.
- [ ] **Soundtrack updates.** Build on the editor's audio work. Map stock music slots, accept compressed source tracks such as MP3, and prepare playback assets in the overlay cache.
- [ ] **Mascot mode** (RavensFan). Research mode selection, eligible teams and characters, and match setup. Implement the mode in the shared DLL and use data packs for its assets and configuration.

## Gameplay

- [ ] **Player heads and faces** (4kim). Research asset identity and player assignment, add Studio export, and verify appearances in menus and gameplay.
- [ ] **Roster and alternate assignment port.** Extend the tool to convert roster fields and alternate uniform assignments to native Xbox equivalents. Verify named players, team and uniform assignments, and edit/save/reload in the selected save profile.
- [ ] **Updated shot clock and three-point distance.** Provide configurable rules through the shared DLL. Verify the shot-clock HUD and reset behavior against game state. Verify scoring logic and court artwork together when changing the three-point line.

## Legacy

All Legacy additions are independently toggleable where dependencies allow. Give save-affecting features explicit compatibility rules and test them in an isolated profile before release.

- [ ] **Program menu and NIL** (RavensFan). Add a Program menu with NIL, stadium and fanbase information, and room for later program features.
- [ ] **Transfer portal** (RavensFan). Add transferring players to recruiting instead of randomly reassigning them. Preserve statistics, eligibility and redshirt status. Show transfer class labels such as `TR SO (RS)`.
- [ ] **Simulation engine** (RavensFan). Update user-team and CPU-versus-CPU simulation and validate season stat totals.
- [ ] **Conference swapping** (RavensFan). Verify conference membership, scheduling and postseason qualification across season transitions.
- [ ] **Player and coach archetypes** (RavensFan). Expand and update archetypes with data definitions and DLL support where behavior changes.
- [ ] **Legacy Home** (RavensFan). Update the home screen to surface the enabled Legacy features.
- [ ] **ABL refresh** (RavensFan). Add jerseys, courts, and crowds. Evaluate an AAU presentation as a design option.
- [ ] **76-team tournament** (RavensFan). Verify selection, seeding, bracket progression, UI, and save/reload.

RavensFan's proposed Legacy sequence is Program and NIL, then the recruiting portal, simulation, conference swapping, archetypes, and Legacy Home. Schedule the ABL and tournament work around their asset and season-flow dependencies.

## Shared DLL responsibilities

Use one project-maintained CHMOD DLL with separate feature modules for presentation, match rules and modes, and Legacy. It owns hooks, live game state, and behavior changes. Loose packs own assets, layouts, and validated feature settings. Studio owns authoring and conversion. The launcher owns compatibility checks, dependency resolution, overlay preparation, native-code opt-in, and recovery.

Start with a verified scorebug and its data contract. Establish the reusable feature lifecycle and compatibility checks there, then validate match-rule toggles before expanding to persistent Legacy systems. For each Legacy module, document the save state it owns, the supported enable and disable points, what happens when a save is reopened with a different feature selection, and how a player returns to a known working profile. Keep executable and vanilla asset files unchanged throughout mod activation and rollback.
