# Direct paired resource components

Fresh direct imports now materialize F0985030 paired CPU/GPU records into
individual decoded component files. The runtime maps those files directly and
generates descriptor compatibility metadata; it does not assemble an IFF body
or rebuild archive chunks. Fresh imports omit obsolete combined paired payloads.
Explicit migration retains originals as backups by default.

Exact shared extents retain one file. Partial overlaps reject before writes.
Unclaimed gaps and tails are preserved. The owner descriptor metadata is the
atomic pair commit point: until publication, the mapper keeps the original data
mapping. Interrupted conversion can be retried from unchanged originals. The
current migration limit is 256 MiB per paired data bank; the largest observed
bank is approximately 27 MiB.

Both the editor and the standard-library runtime reader understand extracted
records. Component sizes are checked; arbitrary resizing is not supported by
this paired compatibility interface. DDS and PCM replacements still use their
own direct native files, without modifying the original texture/XMA components.

## Evidence

- All 40 paired banks / 2,361 records pass private source-removal checks: editor
  and runtime reader hashes match after copied original metadata/data payloads
  are removed. Direct mapper extents also validate.
- Synthetic tests cover decompression, unknown-gap preservation, descriptor
  relocation, partial-overlap rejection, interrupted commit/retry and fresh
  imports that contain no obsolete paired payloads or packed blocks.
- Fourteen loose-assets tests pass, including an end-to-end synthetic disc
  import, direct mapping and repeat-start test.
- Recomp Studio independently reports 77 passing tests. Its cloth OBJ workflow
  passes private byte-preservation checks on all 33 identified Xbox cloth records.

The supplied installation has not been migrated to extracted paired components.
No game was launched. These offline checks do not certify acceptance of relocated,
decoded paired records by guest code during gameplay.

Editor implementation and parity tracking:
[CHoops Extractor Reborn Recomp PR #1](https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp/pull/1).
