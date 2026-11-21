# Native shot-clock initialization

Read-only Ghidra analysis used the USA retail Xbox XEX with SHA-256
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
The entry point and field offsets also match the generated ReXGlue code.

| Address | Observed behavior |
| --- | --- |
| `84A06F98` | Initializes native match timers. In the standard branch, it initializes the shot clock and all three reset values from the 35-second float at `820056B0`. Other branches can use 40 or 1000 seconds. |
| `859FD7A8` | Live shot clock, in floating-point seconds. |
| `859FD9E0`, `84A07288` | Full reset source and consumer. The consumer uses native rounding and near-game-clock adjustment. |
| `859FD9E4`, `84A06790` | First conditional reset floor and consumer. It raises the live clock only when it is below the floor. |
| `859FD9E8`, `84A06830` | Second conditional reset floor and consumer. Its stock behavior also raises the clock only when below the floor. |
| `84AECD38` | Native shot-clock text reads the live timer and respects the game's shot-clock setting. |
| `84A0EE58`, `84A0FB88` | Expiration consumers read and clamp the same timer and gate the stock violation path. |

The local CHMOD DLL prototype calls the native initializer first. For ordinary 35-second matches, it replaces the live value and all three reset fields with the configured duration. It excludes native modes 7 and 8 and leaves any other timer preset intact. This retains stock reset policy and changes its duration. The implementation does not establish a distinct offensive-rebound reset rule.

## Next research boundaries

- **Three-point distance.** See the follow-up [scoring boundary research and DLL implementation](2026-11-21-three-point-distance.md). Matching artwork and gameplay acceptance remain open.
- **Conference changes and transfer portal.** The [Legacy research](2026-11-10-legacy-mode-internals.md) identifies the native conference swap at `84C48C98`, the recruit serializer at `84BF28B8`, and the school-interest insert routine at `84BF0580`. Before adding a portal, trace the outgoing transfer decision and native assignment path, then map full player identity, eligibility, stats and the links that survive a recruiting save/load. Test conference changes through the schedule and postseason transitions.
- **Live versus persisted behavior.** Scorebug and clock settings can be evaluated at match initialization. Legacy systems require separate enable points, save ownership and recovery evidence. Treat existing roster validation, asset conversion and menu research as inputs to that work.

## In-game acceptance

Compare stock 35 and a configured 30 on the same match setup. Check the opening possession, a change of possession, a rim attempt and rebound for each team, a stoppage, the end of a half, and an actual expiration. Compare the native and converted scorebugs and the arena display. Confirm the rule does not activate in modes 7 or 8 or on a nonstandard stock preset. Test with the stock shot-clock option disabled and after removing the profile setting.
