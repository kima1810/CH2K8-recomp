# Archive input validation

Synthetic archive tests confirm that extraction rejects traversal and Windows device names from external name maps. Archive headers enforce the retail 2,048-byte alignment and bounded table counts before allocation. Part names must be one of 0A through 0Z. Output files are opened exclusively to protect existing files.

Python regression tests on this branch recorded 9 passed, 1 skipped. Skips require retail data. The checks cover the extraction and import tooling using synthetic fixtures.
