# Court and shorts SCNE overlays

The existing local conversion uses Xbox `s256.iff`, record index 9,
SCNE ID `be45d62e`, type `e26c9b5d`. The CPU component contains four mesh
records and the texture table. The main floor has 292 vertices in the GPU
component at offset 2082072, stride 36, with float3 position at offset 0 and
four packed UV bytes at offset 28. The conversion suppresses the paint,
center-logo and lines draws and redirects the main floor texture to a
1 MiB allocation at `0x64000`, with a 2048×1024 tiled BC1 base level.
The original component pair is pinned by SHA-256 in `court_contract.h`.
Evidence comes from the local conversion, original and converted Xbox
bytes, and the previous Studio offline rendering of the converted floor.

The `court.scene` validator allows same-topology position/UV changes and
the exact researched CPU descriptor and draw changes for the full-floor
conversion. The full-floor form additionally allows BC1 bytes in the
known allocation. The loader checks both component owners and source
digests and stages the pair in its private asset cache. Conflicts on either
component reject the selection. The shorts continue to use `cloth.positions`.

The Windows validator compiled and accepted the existing court conversion.
The launcher's resolver accepted Georgia Full Floor together with all three
shorts variants. The previous direct court overlay was restored to the
verified original components using its existing rollback script. The
court package is installed separately and can be enabled in Mods. Verification
covered the production validator and resolver. Cache preparation and gameplay
acceptance remain pending.
