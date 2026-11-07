# Native texture memory retention

Native D3D12 DDS replacements previously held the full compressed file in RAM
for the GPU texture's lifetime. Each replacement also accumulated superseded
GPU textures and descriptors until normal cache eviction. A frequently reused
guest texture address could therefore retain many obsolete allocations.

The runtime now stores only `NativeDDSInfo` after upload. The upload staging
resource remains alive through its submission fence. Matching resident
identities return metadata without reading or parsing the DDS again; changed
identities still go through normal file validation and upload.

Retired GPU textures carry their last possible submission, allocation size and
descriptor ownership. A pending-texture set is drained on texture requests,
releasing only entries whose submission has completed. Collection subtracts
the allocation from the texture cache's aggregate memory usage exactly once.
Texture destruction removes pending pointers and releases any remaining
descriptors through the existing fence-safe cache destruction path. The pump
examines only textures with pending retirements, rather than the whole cache.
When rendering stops, normal cache teardown still owns the remaining resources.

Validation includes the pinned SDK patch/idempotence check, existing loose-asset
tests, and a compiled C++ harness using the generated retirement methods. It
checks 1,000 replacement cycles, incomplete-fence retention, completed-fence
release, descriptor release counts, repeated collection and exact allocation
accounting. A synthetic DDS catalog verifies that metadata does not keep its
CPU payload alive and that resident lookup succeeds after the source file is
removed; nonresident lookup still rejects the missing file.

Validation result: 16 focused tests passed. The patched dual-backend SDK and
game built successfully, and the updated GPU DLL was staged beside the game.
The standalone D3D12 upload/readback check passed all 20 exact round trips:
BC1 through BC5, 64x64 with seven mip levels and 2048x2048 with one mip level,
on both the Radeon RX 6650 XT and WARP software adapter. This checks upload
integrity; retirement behavior is covered by the compiled harness rather than
a live-game capture.

This applies to native DDS replacements on D3D12. It does not change guest RAM
allocation or Vulkan texture handling. No displayed-FPS improvement, measured
process working-set reduction, or long gameplay stability result is claimed.
