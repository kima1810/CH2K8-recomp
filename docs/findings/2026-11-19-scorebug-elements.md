# Scorebug hook research

Read-only Ghidra research identifies native scene ownership, text drawing,
material state and live match fields for the supported Xbox executable.
The XEX SHA-256 is
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
Addresses below apply to that revision. The reusable headless entry point is
`ghidra/DecompileScorebug.java`. Research does not establish a new public hook ABI.

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

## Rendering boundaries

Native instance draw `84D23B80` and material preparation `84D2DC20` are useful
boundaries for observing scene-specific draw state. Render-state submission is
`84D36C60`. Xbox alpha enable is state 60, source blend 72, destination blend 76,
blend operation 80, alpha test 96, reference 100 and comparison 104. Xbox
source-alpha is 6, inverse-source-alpha 7 and GREATER comparison 4. Desktop D3D9
enumeration values differ. Any adapter changing shared state must preserve its
ownership and restore temporary material/pose edits after command construction.

## Scene-format findings

PS3 and Xbox scenes require more than relabeling data. Draw records have a
48-byte stride with material slot at +32. Mesh transforms/bounds, bone rest
transforms, instance poses, text styles and relative pointers must be preserved.
Vertex bone-index byte lanes and shader uniform/sampler parameter offsets differ
between platform declarations. Scene header field zero is a scene-name relative
pointer. Mesh part +20 is vertex count; it must not be treated as a bounds field.

These findings came from static inspection and structural conversion audits.
They do not establish visual parity, gameplay correctness or a supported general
SCNE writer. Live poll-rank ownership remains unresolved. The mod-specific
implementation, provider, artwork and conversion packaging are outside this PR.

## Performance constraints for future adapters

Read native live fields rather than polling files during drawing. Retain managed
strings and update them on value changes. Cache native width measurements. Bind
state to the main scene owner rather than allowing auxiliary scene lookups to
change an existing owner's layout. These constraints follow the inspected
ownership and drawing paths; no comparative frame-time benchmark is claimed.
