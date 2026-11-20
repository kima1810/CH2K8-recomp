# Scorebug scene conversion and live elements

The ESPN and USA Sports preview uses converted PS3 scene geometry with native
Xbox texture declarations and shader programs. A separate preview DLL selects
the style through Options / Presentation. ESPN is the initial choice. The
native owner selects its scene during match initialization. Changing the choice
applies on the next match scene construction.

The source XEX SHA-256 is
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
These addresses describe that revision. Research used the existing Xenon
big-endian Ghidra database and read-only headless sessions. Temporary function
definitions were discarded. Game-derived exports and artwork stay local.

The initial converter omitted text styles, bone transforms and material
parameter translation. It also used an incorrect draw-record stride. It now
transfers full 48-byte draw records, mesh transforms and bounds, all bone rest
transforms and instance poses, text placement and styles, and shader uniforms
and samplers using their platform-specific parameter offsets. It retains the
scene-name relative pointer while appending changed font names. Vertex bone
index byte lanes are translated for the Xbox declarations.

| Native entry or field | Verified use |
| --- | --- |
| `84D27690` | Scene lookup and construction boundary |
| `84AEE380`, return site `84AEE40C` | Main bottom-bar scene owner initialization |
| `84BBB558`, `84BBB568` | Current home and away team records |
| `84C6B9E8` | Native school label from team record `+0` |
| `84AEC3B0`, `84AEC418` | Main HUD label path from team record `+4`, with native mode gates |
| `848AEC08`, team statistic 72 | Remaining timeouts from the side's live rule object `+4` |
| `84CCF6F8` | Native foul notice reads the active team-foul counter at rule object `+8` |
| `847F54A0`, team statistic 15 | Separate period-indexed team-foul statistic |
| `84A0F2E0` | Bonus predicate using active threshold `8565CDE8` |
| `84A0F308` | Double-bonus predicate using `8565CDEC` and the native carried counter |
| `84A0B968` | Free-throw consumer checks double bonus before bonus and excludes modes 7/8 |
| `859FDA98` | Next alternating-possession team pointer |
| `849E0C90` | Initializes that pointer from native possession state |
| `84A06BC0`, `84B84F80`, `84B85478` | Consume and switch alternating possession through the opposing-team link `+0x24` |
| `84764FC8` | Native text drawing boundary |
| `84D23B80`, `84D2DC20` | Instance drawing and material state preparation |

The overlay reads the rule objects owned by home `858B67F0` and away
`858B6840`. It displays the beneficiary team's bonus using the opponent's foul
state. The arrow reads `859FDA98` without changing it. It follows native
alternating possession independently of current ball control. Rank fields have
no verified live poll source in this implementation.

New labels render alongside the normal home-score draw and use native font
measurement for school-name width fitting. Three native marker positions
recover the scene transform independently of score-font size. Managed strings
are retained and replaced when values change. Measurement is cached. There is
no filesystem polling in the draw hooks. Active style follows the main scene
owner so an auxiliary lookup cannot move an existing HUD into the newly
selected style's coordinates.

The refinement makes the team-logo quads square at 40 scene units. ESPN's
original quads were 32 units. It reuses an authored hidden four-vertex circle
strip as a possession triangle. Packed bone lanes and index data remain intact.
The draw hook moves and mirrors its existing pose for the entitled side, then
restores the pose after native command construction.

Logos explicitly enable Xbox straight-alpha blending with source-alpha /
inverse-source-alpha and additive blend operation. Transparent texels also use
an alpha test. Xbox comparison `GREATER` is 4, source alpha is 6, and inverse
source alpha is 7. Desktop D3D9 enum values differ. Material words are restored
after command construction. The arrow disables culling for its mirrored draw.

The preview is opt-in through `CH2K8_SCOREBUG_PROVIDER` and an overlay containing
`scorebug-probe.ready`. Its DLL interface remains a preview interface. The
regular CHMOD SDK interface is separate. The provider example, converters,
auditors, bank builder, mounting script and research script are stored with the
runtime source so they can be reviewed and committed together.

The bank adds `scorebug_reborn_espn` (`3AB5EF46`) and `scorebug_reborn_usa`
(`79427BAB`) while preserving all 262 original records. Five artwork overrides
round-trip through native Xbox texture storage. The sixth support texture and
native animation streams are retained. The combined preview mounts the new
bank over a copy of the active mod cache and reuses the normal launch's save
profile and renderer flags.

Verification includes a successful Windows runtime build, both original port
audits with 23 meshes, 348 vertices, 24 draw records, 23 instances, 10 text nodes
and 14 materials, and both refinement audits. Only three bounding radii and the
declared logo/arrow vertex ranges change in the refinement. All other CPU and
GPU bytes compare exactly. Both scenes reparse as 23 meshes with zero preview
warnings. The overlay passes the 24-part native VFS checks. All 3,662 retained
mod-cache files compare exactly.

The updated elements and logo appearance require the owner's manual in-game
check. Visual parity, runtime calibration and all match transitions remain
unverified. Computer-use automation is prohibited for this task.

Use `tools/scorebugs/convert_scorebug_geometry.py` and `audit_scorebug_port.py`
for the initial port, then `refine_scorebug_layout.py` and
`audit_scorebug_layout.py` for the reference layout. The optional artwork step
imports the Studio texture modules. The bank builder imports the existing
`tools/loose_assets.py` module through `PYTHONPATH=tools`. Build the provider
from `examples/scorebug_preview`. Invoke
`tools/scorebugs/Launch-ScorebugPreview.ps1` with `-OverlayRoot` and
`-ProviderDll` pointing at local generated outputs. Use `-Executable` to select
a build, or the installed root executable is used. The launcher reuses the
regular `last-launch.json` profile.
