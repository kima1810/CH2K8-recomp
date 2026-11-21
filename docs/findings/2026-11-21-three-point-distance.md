# Three-point scoring boundary

Read-only Ghidra analysis used the USA Xbox XEX with SHA-256
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`.
The generated ReXGlue code confirms the field writes and call sites.

| Address | Role |
| --- | --- |
| `84B84208` | Initializes court dimensions and the shared scoring boundary. |
| `85A8AD40`, `85A8AD44` | Full court width and length in centimeters. The standard fallback is approximately 1,524 by 2,865.12 cm. |
| `85A8AD48`, `85A8AD50` | Straight corner offset from center court and radius of the semicircular arc. Both use the standard stock threshold of approximately 612.14 cm, or 241 inches. |
| `84A0A958` | Tests a court-plane point against the corner or arc with the caller's tolerance. A point exactly on the boundary counts as inside at zero tolerance. |
| `84A0AAF8`, `84A06660` | Transform the shooter's native foot samples and require them to be outside. Shot setup stores the result in bit `0x400` of ball state at `+0x68`. |
| `84A0C548`, `84939000`, `849390B0` | Made-shot dispatch selects the two- or three-point path from that flag. `84A13890` and `84A12360` update the corresponding player and team statistics. |
| `84A0A8C8`, `84951E80` | Native signed-distance and positioning helpers use the same boundary dimensions. |

The local DLL prototype calls the court initializer first and sets the two boundary fields together. It retains native basket mirroring and the arc-to-corner transition. At the standard court's two ends, the transition is approximately 1,272.54 cm from center court along the length axis. The override caps each corner offset at half the full court width minus 60.96 cm to leave a two-foot sideline gap. Special modes 7 and 8 retain their native dimensions.

The configured distance is the game's scoring threshold. For a matching court overlay, draw a semicircle on the midcourt side of each hoop center and continue its endpoints straight to the baseline. Bind the artwork to the effective distance after the court-width cap. Stock paint and existing custom floor assets remain as authored.

Verify both ends in a match. Place both feet inside, on, and outside boundaries at the top, wing, corner, and transition. Check shots with one foot inside, replay classification, score, player and team three-point attempts and makes, and foul-shot awards. Compare stock and converted court artwork and confirm disabling the setting restores the normal boundary.
