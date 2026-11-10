# Archive input validation

Synthetic archive tests confirm that extraction rejects traversal and Windows device names from external name maps. Archive headers enforce the retail 2,048-byte alignment and bounded table counts before allocation. Part names must be one of 0A through 0Z. Output files are opened exclusively to protect existing files.

The development ISO extractor checks directory bounds, directory cycles, filename components and resolved output paths. A synthetic ISO verifies rejection of a traversal name.

Python regression tests on this branch recorded 15 passed, 2 skipped. Skips require retail data. The checks cover the extraction and import tooling using synthetic fixtures.
