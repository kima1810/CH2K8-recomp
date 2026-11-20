# Archive input validation

Synthetic archive tests confirm that extraction rejects traversal and Windows device names from external name maps. Archive headers enforce the retail 2,048-byte alignment and bounded table counts before allocation. Part names must be one of 0A through 0Z. Output files are opened exclusively to protect existing files.

The development ISO extractor checks directory bounds, directory cycles, filename components and resolved output paths. A synthetic ISO verifies rejection of a traversal name.

Python Xbox component decoders limit zlib output to the declared extent plus one byte to detect an overrun. H7A copies only the match bytes it will use. A synthetic component with a one-byte declared size and a one-MiB payload is rejected.

The standalone native importer uses the upstream miniz 3.1.2 amalgamation with only the required inflate functionality enabled. The release ZIP was verified against GitHub SHA-256 `f0446d863f9c19926ad9483c523fdc42e42b8d4a6a431d27e09d49c79a140d9a`. The same native importer source is used on main, ZMO-beta1, 4kim-beta and the geometry branch. Its Windows x64 standalone build passed all 15 native import and edit protocol tests with synthetic data.

Python regression tests on this branch recorded 30 passed, 2 skipped. Skips require retail data. The checks cover the extraction and import tooling using synthetic fixtures.
