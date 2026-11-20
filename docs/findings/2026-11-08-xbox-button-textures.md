# Xbox 360 controller-button textures — 2026-11-08

Read-only export from the retained Xbox installation, supported XEX SHA256
71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36.
Visual inspection of frontend/global DDS contact sheets identified these global.iff
TXTR records (type1547079785):

| Index | Record ID | Size | Content |
| --- | --- | --- | --- |
| 270 | 7542283f | 256x256 | A/B/X/Y, Start/Back, shoulders/triggers and stick/D-pad prompts |
| 410 | acc6d118 | 512x512 | Stick-direction prompts |
| 512 | d948c961 | 256x256 | Navigation arrows and button prompts |
| 0 | 001d1bcf | 128x64 | Xbox 360 controller illustration |

Original DDS hashes and native component hashes were matched against imported
asset.json before exporting. Private workspace artifacts are under
`../Research/Xbox360-Button-Textures/`, with a ZIP alongside that directory.
source_manifest.json retains bank/record identities, native descriptors, hashes,
and original component provenance. PNG previews were decoded with Pillow; 16
64x64 crops from the main atlas are visual cell labels, not verified game UVs or
semantic button IDs. No game/source assets, settings or saves were changed.
No game was launched and no automated tests were executed. Offline visual
identification/export is not in-game verification or proof of every usage site.
The original game-owned textures are private exports, not public SDK samples;
no asset files were uploaded to GitHub. Menu toggle/render selection adapters
remain separate future research.
