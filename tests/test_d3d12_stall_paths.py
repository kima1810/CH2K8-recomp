"""Execute the changed control flow from the prepared SDK with explicit fakes."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from prepare_native_shader_sdk import patch_pipeline
from prepare_native_sync_sdk import patch_sync


@pytest.fixture
def sdk_source():
    for candidate in (ROOT/'work/third_party/rexglue-vulkan', ROOT/'out/rexglue'):
        if (candidate/'.git').exists():
            return candidate
    pytest.skip('Requires pinned SDK source')


def original(source, name):
    return subprocess.check_output(['git', '-C', str(source), 'show',
        'HEAD:src/graphics/d3d12/'+name+'.cpp'], text=True)


def execute(tmp_path, program):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('Requires Clang')
    source = tmp_path/'check.cpp'
    binary = tmp_path/'check.exe'
    source.write_text(program)
    result = subprocess.run([compiler, '-std=c++23', str(source), '-o', str(binary)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)


def test_sparse_pool_keeps_small_mappings_disjoint_across_large_allocations(sdk_source, tmp_path):
    from prepare_native_assets_sdk import patch_d3d12_sparse_memory

    source = patch_d3d12_sparse_memory(original(sdk_source, 'shared_memory'))
    start = source.index('  // Physical heap offsets are independent')
    end = source.index('  D3D12_TILED_RESOURCE_COORDINATE', start)
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
#include <utility>
#include <vector>
#define REXCVAR_GET(flag) (flag)
#define FAILED(status) ((status) != 0)
#define IID_PPV_ARGS(ptr) ptr
#define REXGPU_ERROR(...)
#define REXGPU_INFO(...)
enum { D3D12_HEAP_TYPE_DEFAULT, D3D12_HEAP_FLAG_ALLOW_ONLY_BUFFERS };
struct D3D12_HEAP_DESC { uint32_t SizeInBytes; struct { int Type; } Properties; int Flags; };
struct ID3D12Heap { uint32_t bytes; };
int main() {
  constexpr uint32_t mib = 1 << 20;
  constexpr bool ch2k8_pool_sparse_heaps = true, ch2k8_gpu_stats = false;
  struct { int GetHeapFlagCreateNotZeroed() { return 0; } } provider;
  struct Device {
    bool fail = false;
    int CreateHeap(const D3D12_HEAP_DESC* desc, ID3D12Heap** heap) {
      if (fail) return 1;
      *heap = new ID3D12Heap{desc->SizeInBytes};
      return 0;
    }
  } gpu;
  auto* device = &gpu;
  std::vector<ID3D12Heap*> buffer_tiled_heaps_;
  ID3D12Heap* sparse_pool_heap_ = nullptr;
  uint32_t sparse_heap_remaining_bytes_ = 0;
  std::pair<ID3D12Heap*, uint32_t> mapping;
  auto allocate = [&](uint32_t length_bytes) {
'''+source[start:end]+r'''
    assert(heap_offset_bytes + length_bytes <= heap->bytes);
    mapping = {heap, heap_offset_bytes};
    return true;
  };
  assert(allocate(mib));
  auto* pool = mapping.first;
  assert(mapping.second == 0 && pool->bytes == 4 * mib);
  gpu.fail = true;
  assert(!allocate(7 * mib));
  gpu.fail = false;
  assert(allocate(7 * mib) && mapping.first != pool && mapping.second == 0);
  assert(allocate(2 * mib) && mapping.first == pool && mapping.second == mib);
  assert(allocate(mib) && mapping.first == pool && mapping.second == 3 * mib);
  assert(allocate(mib) && mapping.first != pool && mapping.second == 0);
  assert(buffer_tiled_heaps_.size() == 3);
  for (auto* heap : buffer_tiled_heaps_) delete heap;
}
''')


def test_cache_pressure_keeps_readback_slots_until_gpu_completion(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('void D3D12CommandProcessor::EvictOldReadbackBuffers(')
    body = source[start:source.index('\n}\n', start)+2]
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
#include <unordered_map>
struct Resource {
  int releases = 0, unmaps = 0;
  void Release() { ++releases; }
  void Unmap(int, void*) { ++unmaps; }
};
struct ReadbackBuffer {
  Resource* buffers[2]{};
  void* mapped_data[2]{};
  uint32_t sizes[2]{}, written_size[2]{};
  uint64_t last_used_frame = 0, submission_written[2]{};
};
struct D3D12CommandProcessor {
  static constexpr uint32_t kMaxReadbackBuffers = 1, kReadbackBufferEvictionAgeFrames = 10;
  uint64_t frame_current_ = 5, submission_completed_ = 7;
  void EvictOldReadbackBuffers(std::unordered_map<uint64_t, ReadbackBuffer>&);
};
'''+body+r'''
int main() {
  D3D12CommandProcessor processor;
  Resource busy, complete;
  std::unordered_map<uint64_t, ReadbackBuffer> buffers;
  buffers[1].buffers[1] = &busy;
  buffers[1].mapped_data[1] = &busy;
  buffers[1].submission_written[1] = 8;
  buffers[2].buffers[0] = &complete;
  buffers[2].mapped_data[0] = &complete;
  buffers[2].submission_written[0] = 7;
  processor.EvictOldReadbackBuffers(buffers);
  assert(buffers.size() == 1 && buffers.count(1));
  assert(busy.releases == 0 && busy.unmaps == 0);
  assert(complete.releases == 1 && complete.unmaps == 1);
  processor.frame_current_ = 100;
  processor.EvictOldReadbackBuffers(buffers);
  assert(buffers.count(1) && busy.releases == 0);
  processor.submission_completed_ = 8;
  processor.EvictOldReadbackBuffers(buffers);
  assert(buffers.empty() && busy.releases == 1 && busy.unmaps == 1);
}
''')


def test_scratch_vram_buckets_and_fence_safe_idle_trim(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('  // CH2K8 right-size scratch allocations.')
    end = source.index('\n\n  const ui::d3d12::D3D12Provider& provider', start)
    trim = source.index('    // Trim a large transient buffer')
    trim_end = source.index('    EvictOldReadbackBuffers(readback_buffers_);', trim)
    execute(tmp_path, r'''
#include <algorithm>
#include <bit>
#include <cassert>
#include <cstdint>
#define REXCVAR_GET(...) false
#define REXGPU_INFO(...) ((void)0)
constexpr uint32_t MiB = 1u << 20, kScratchBufferSizeIncrement = 16 * MiB;
namespace rex {uint32_t align(uint32_t value, uint32_t step) {return (value + step - 1) & ~(step - 1);}}
const uint32_t* AllocationSize(uint32_t size) {
'''+source[start:end]+r'''
  static uint32_t result;
  result = size;
  return &result;
}
namespace ui::d3d12::util {void ReleaseAndNull(int*& resource) {assert(resource); resource = nullptr;}}
int main() {
  assert(*AllocationSize(4) == MiB);
  assert(*AllocationSize(MiB + 1) == 2 * MiB);
  assert(*AllocationSize(16 * MiB) == 16 * MiB);
  assert(*AllocationSize(16 * MiB + 1) == 32 * MiB);
  assert(AllocationSize(UINT32_MAX) == nullptr);
  for (unsigned mode = 0; mode < 5; ++mode) {
    int resource = 1;
    int* scratch_buffer_ = &resource;
    uint32_t scratch_buffer_size_ = mode == 1 ? 16 * MiB : 32 * MiB;
    bool scratch_buffer_used_ = mode == 2;
    uint64_t scratch_buffer_last_submission_ = 7;
    uint64_t submission_completed_ = mode == 3 ? 6 : 7;
    uint64_t scratch_buffer_last_frame_ = 20, frame_current_ = mode == 4 ? 139 : 140;
'''+source[trim:trim_end]+r'''
    assert((scratch_buffer_ == nullptr) == (mode == 0));
    assert((scratch_buffer_size_ == 0) == (mode == 0));
  }
}
''')


def test_render_target_trim_runs_only_at_an_idle_frame_boundary(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('    // CH2K8 trim render targets without stalling.')
    end = source.index('    // Update the completed frame index', start)
    execute(tmp_path, r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#define REXCVAR_GET(...) false
#define REXGPU_INFO(...) ((void)0)
int main() {
  for (unsigned mode = 0; mode < 6; ++mode) {
    struct Cache {
      size_t count = 16;
      bool reset_bindings = false;
      unsigned trims = 0;
      size_t GetCachedRenderTargetCount() {return count;}
      void BeginFrame() {reset_bindings = true;}
      void ClearCache() {assert(reset_bindings); ++trims; count = 4;}
    } cache;
    if (mode == 5) cache.count = 15;
    auto* render_target_cache_ = &cache;
    const bool submission_open_ = mode == 1;
    const bool queue_operations_done_since_submission_signal_ = mode == 2;
    const uint64_t submission_current_ = 8;
    const uint64_t submission_completed_ = mode == 3 ? 6 : 7;
    const uint64_t frame_current_ = mode == 4 ? 299 : 300;
    uint64_t next_render_target_trim_frame_ = 300;
'''+source[start:end]+r'''
    assert(cache.trims == (mode == 0));
    assert(next_render_target_trim_frame_ == (mode == 0 || mode == 5 ? 600 : 300));
  }
}
''')


def test_storage_writer_runs_pending_flush_before_waiting(sdk_source, tmp_path):
    source = patch_pipeline(original(sdk_source, 'pipeline_cache'))
    start = source.index('      if (!shader && !write_pipeline')
    end = source.index('\n    }', start)
    execute(tmp_path, r'''
#include <cassert>
int main() {
  for (unsigned mode = 0; mode < 16; ++mode) {
    const bool shader = mode & 1, write_pipeline = mode & 2;
    const bool flush_shaders = mode & 4, flush_pipelines = mode & 8;
    struct Condition {
      unsigned calls = 0;
      void wait(int) { ++calls; }
    } storage_write_request_cond_;
    constexpr int lock = 0;
    for (unsigned iteration = 0; iteration < 1; ++iteration) {
'''+source[start:end]+r'''
    }
    assert(storage_write_request_cond_.calls == (mode == 0));
  }
}
''')


def test_memexport_consumes_only_completed_copies(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('  uint32_t completed_index = read_index;')
    end = source.index('\n}\n', start)
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
namespace ch2k8 {
enum class SyncKind {MemexportFallback};
struct SyncScope {explicit SyncScope(SyncKind) {}};
}
namespace draw_util {struct MemExportRange {uint32_t base_address_dwords, size_bytes;};}
struct Memory {
  uint8_t bytes[16]{};
  uint8_t* TranslatePhysical(uint32_t address) {return bytes + address;}
};
struct Fixture {
  Memory memory;
  Memory* memory_ = &memory;
  const std::vector<draw_util::MemExportRange> memexport_ranges_{{1, 4}, {3, 4}};
  const uint8_t current[8]{1,2,3,4,5,6,7,8}, previous[8]{11,12,13,14,15,16,17,18};
  struct Readback {
    uint64_t submission_written[2]{7, 6};
    const void* mapped_data[2];
    uint32_t current_index = 0;
  } readback{{7, 6}, {current, previous}};
  uint64_t submission_completed_ = 6;
  int waits = 0;
  bool await_success = true, submitted = true;
  bool AwaitAllQueueOperationsCompletion() {
    ++waits;
    if (submitted && await_success) submission_completed_ = 7;
    return await_success;
  }
  bool Run(bool previous_slot_ready) {
    constexpr uint32_t write_index = 0, read_index = 1;
'''+source[start:end]+r'''
  }
};
int main() {
  for (int mode = 0; mode < 4; ++mode) {
    Fixture fixture;
    fixture.await_success = mode != 2;
    fixture.submitted = mode != 3;
    assert(fixture.Run(mode == 0));
    assert(fixture.waits == (mode == 0 ? 0 : 1));
    assert(fixture.readback.current_index == 1);
    const auto* result = fixture.memory.bytes;
    for (unsigned i = 0; i < 16; ++i) {
      const unsigned expected = i >= 4 && i < 8 ? i-3 : i >= 12 ? i-7 : 0;
      assert(result[i] == (mode >= 2 || !expected ? 0 : expected+(mode == 0 ? 10 : 0)));
    }
  }
}
''')


def test_memexport_cache_never_reuses_multi_range_layouts(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('  if (memexport_ranges_.size() != 1)')
    end = source.index('  const uint64_t readback_key', start)
    execute(tmp_path, r'''
#include <cassert>
#include <vector>
bool UsesDelayedCopy(unsigned ranges) {
  const std::vector<int> memexport_ranges_(ranges);
  constexpr unsigned total_size = 12;
  auto IssueDraw_MemexportReadbackFullPath = [](unsigned size) {
    assert(size == 12);
    return false;
  };
'''+source[start:end]+r'''
  return true;
}
int main() {
  assert(UsesDelayedCopy(1));
  assert(!UsesDelayedCopy(2));
  assert(!UsesDelayedCopy(3));
}
''')


def test_delayed_resolve_uses_completed_slot_or_waits_for_current_copy(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('  uint32_t read_index = write_index;')
    end = source.index('  bool should_copy =', start)
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
int main() {
  for (unsigned mode = 0; mode < 5; ++mode) {
    struct {
      unsigned sizes[2]{16,16};
      bool buffers[2]{true,true}, mapped_data[2]{true,true};
      uint64_t submission_written[2]{8,7};
    } rb;
    if (mode == 4) rb.submission_written[1] = 0;
    uint64_t submission_completed_ = mode == 0 ? 7 : 6;
    unsigned polls = 0, waits = 0, consumed = 2;
    bool use_delayed_sync = mode != 2;
    constexpr unsigned write_index = 0, written_length = 16;
    auto CheckSubmissionFence = [&](int) { ++polls; return true; };
    auto AwaitAllQueueOperationsCompletion = [&] {
      ++waits;
      if (mode != 3) submission_completed_ = 8;
      return true;
    };
    const auto run = [&]() -> bool {
'''+source[start:end]+r'''
      consumed = read_index;
      assert(is_cache_miss == (use_delayed_sync && read_index == write_index));
      return true;
    };
    assert(run());
    assert(polls == (mode == 1 || mode == 3));
    assert(waits == (mode != 0));
    assert(consumed == (mode == 0 ? 1 : mode == 3 ? 2 : 0));
  }
}
''')


def test_synchronous_draws_queue_only_the_pso_and_wait_before_replay(sdk_source, tmp_path):
    source = patch_pipeline(original(sdk_source, 'pipeline_cache'))
    command = original(sdk_source, 'command_processor')
    submit = command[command.index('bool D3D12CommandProcessor::EndSubmission('):]
    assert (submit.index('pipeline_cache_->EndSubmission();') <
            submit.index('deferred_command_list_.Execute(') <
            submit.index('direct_queue->ExecuteCommandLists('))
    start = source.index('  const bool parallel_creation =')
    end = source.index('\n\n  if (pipeline_storage_file_)', start)
    execute(tmp_path, r'''
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <queue>
#include <vector>
#define REXCVAR_GET(name) name
namespace pipeline_util {
uint32_t GetBoundRTMaskFromNormalizedColorMask(uint32_t value) {return value;}
unsigned CalculatePipelinePriority(uint32_t, uint32_t, bool) {return 1;}
}
struct Shader {
  const Shader& shader() const {return *this;}
  uint32_t writes_color_targets() const {return 1;}
  bool writes_depth() const {return false;}
};
struct Pipeline {
  Shader* pending_vertex_shader = nullptr;
  Shader* pending_pixel_shader = nullptr;
  unsigned priority = 0;
  std::atomic<int> state{0};
};
int CreateD3D12Pipeline(int root_signature) {assert(root_signature == 7); return 1;}
int main() {
  for (int mode = 0; mode < 4; ++mode) {
    bool ch2k8_parallel_pipeline_creation = mode != 1;
    bool async_shader_compilation = mode == 3, use_async = async_shader_compilation;
    std::vector<int> creation_threads_(mode != 2);
    Pipeline pipeline;
    auto* new_pipeline = &pipeline;
    Shader vs, ps;
    auto* vertex_shader = &vs;
    auto* pixel_shader = &ps;
    uint32_t normalized_color_mask = 1;
    struct {unsigned z_write_enable = 0;} normalized_depth_control;
    std::mutex creation_request_lock_;
    std::queue<Pipeline*> creation_queue_;
    std::condition_variable creation_request_cond_;
    int runtime_description = 7;
'''+source[start:end]+r'''
    assert(creation_queue_.empty() == (mode == 1 || mode == 2));
    assert(pipeline.state.load() == (mode == 1 || mode == 2));
    assert(pipeline.pending_vertex_shader == (mode == 3 ? &vs : nullptr));
    assert(pipeline.pending_pixel_shader == (mode == 3 ? &ps : nullptr));
  }
}
''')


def test_out_of_submission_fence_arms_event_before_waiting(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('      if (SUCCEEDED(direct_queue->Signal(queue_operations_since_submission_fence_')
    end = source.index('\n    }', start)
    execute(tmp_path, r'''
#include <cassert>
#define SUCCEEDED(result) ((result) >= 0)
#define PROFILE_CMD_BUFFER_STALL()
#define REXGPU_ERROR(...) ++errors
int main() {
  for (int mode = 0; mode < 4; ++mode) {
    int errors = 0, waits = 0;
    struct Queue {
      int status;
      int Signal(void*, int value) {assert(value == 4); return status;}
    } queue{mode == 1 ? -1 : 0};
    struct Fence {
      int status, armed = 0;
      int SetEventOnCompletion(int value, int event) {
        assert(value == 4 && event == 9); ++armed; return status;
      }
    } fence{mode == 2 ? -1 : 0};
    auto* direct_queue = &queue;
    auto* queue_operations_since_submission_fence_ = &fence;
    constexpr int fence_value = 4, fence_completion_event_ = 9, INFINITE = -1, WAIT_OBJECT_0 = 0;
    bool queue_operations_done_since_submission_signal_ = true;
    auto WaitForSingleObject = [&](int event, int timeout) {
      assert(event == 9 && timeout == -1 && fence.armed == 1);
      ++waits;
      return mode == 3 ? -1 : WAIT_OBJECT_0;
    };
    const auto run = [&]() -> bool {
'''+source[start:end]+r'''
      return true;
    };
    assert(run() == (mode == 0));
    assert(waits == (mode == 0 || mode == 3));
    assert(errors == (mode != 0));
    assert(fence.armed == (mode != 1));
    assert(queue_operations_done_since_submission_signal_ == (mode != 0));
  }
}
''')


def test_device_loss_sentinel_never_advances_gpu_completion(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('  uint64_t completed = submission_fence_->GetCompletedValue();')
    end = source.index('  // Reclaim command allocators.', start)
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
#define FAILED(status) ((status) < 0)
#define PROFILE_CMD_BUFFER_STALL()
#define REXGPU_ERROR(...) ((void)0)
using HRESULT = int;
int main() {
  for (int mode = 0; mode < 4; ++mode) {
    constexpr int fence_completion_event_ = 0, INFINITE = -1, WAIT_OBJECT_0 = 0;
    constexpr int DXGI_ERROR_DEVICE_REMOVED = -2;
    const uint64_t await_submission = 8;
    uint64_t submission_completed_ = 6;
    bool device_removed_ = false;
    struct Fence {
      uint64_t completed;
      uint64_t GetCompletedValue() const {return completed;}
      int SetEventOnCompletion(uint64_t, int) {return 0;}
    } fence{mode == 0 ? UINT64_MAX : 7};
    auto* submission_fence_ = &fence;
    auto WaitForSingleObject = [&](int, int) {
      fence.completed = mode == 1 ? UINT64_MAX : 8;
      return mode == 2 ? -1 : WAIT_OBJECT_0;
    };
    struct Device {int GetDeviceRemovedReason() const {return -2;}} device;
    struct Provider {Device* device; Device* GetDevice() const {return device;}};
    auto GetD3D12Provider = [&] {return Provider{&device};};
    auto LogDeviceRemovalDiagnostics = [](Device*, HRESULT reason) {assert(reason == -2);};
    struct Graphics {
      unsigned losses = 0;
      void OnHostGpuLossFromAnyThread(bool) {++losses;}
    } graphics;
    auto* graphics_system_ = &graphics;
    const auto run = [&]() -> bool {
'''+source[start:end]+r'''
      return reached;
    };
    assert(run() == (mode == 3));
    assert(submission_completed_ == (mode == 3 ? 8 : 6));
    assert(device_removed_ == (mode < 2));
    assert(graphics.losses == unsigned(mode < 2));
  }
}
''')


def test_unsignaled_submission_stops_the_queue_without_advancing_fence(sdk_source, tmp_path):
    source = patch_sync(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('    const HRESULT signal = direct_queue->Signal(submission_fence_,')
    end = source.index('    ++submission_current_;', start)+len('    ++submission_current_;')
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
#define FAILED(status) ((status) < 0)
using HRESULT = int;
int main() {
  constexpr HRESULT DXGI_ERROR_DEVICE_REMOVED = -2;
  for (unsigned mode = 0; mode < 2; ++mode) {
    const bool failed = mode != 0;
    uint64_t submission_current_ = 7;
    bool submission_open_ = true, device_removed_ = false;
    struct Queue {
      HRESULT result;
      HRESULT Signal(void*, uint64_t value) {assert(value == 7); return result;}
    } queue{failed ? DXGI_ERROR_DEVICE_REMOVED : 0};
    auto* direct_queue = &queue;
    void* submission_fence_ = nullptr;
    struct Provider {void* GetDevice() {return nullptr;}} provider;
    auto LogDeviceRemovalDiagnostics = [&](void*, HRESULT reason) {assert(reason == -2);};
    struct Graphics {
      unsigned losses = 0;
      void OnHostGpuLossFromAnyThread(bool responsible) {assert(!responsible); ++losses;}
    } graphics;
    auto* graphics_system_ = &graphics;
    const auto run = [&]() -> bool {
'''+source[start:end]+r'''
      return true;
    };
    assert(run() != failed);
    assert(!submission_open_ && device_removed_ == failed);
    assert(submission_current_ == (failed ? 7 : 8));
    assert(graphics.losses == unsigned(failed));
  }
}
''')


def test_invisible_draw_culling_preserves_rendering_queries_and_exports(sdk_source, tmp_path):
    from prepare_native_gpu_sdk import patch_backend

    source = patch_backend(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('  // CH2K8 discard draws without visible effects.')
    end = source.index('  if (!BeginSubmission(true))', start)
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
#define REXCVAR_GET(flag) flag
#define REXGPU_INFO(...)
int main() {
  for (unsigned mode = 0; mode < 9; ++mode) {
    const bool ch2k8_skip_invisible_draws = mode != 0;
    const bool ch2k8_gpu_stats = false;
    const bool memexport_used = mode == 3;
    struct {bool valid;} active_occlusion_query_{mode == 4};
    struct {unsigned extent[2];} scissor{{mode == 2 || mode == 3 ? 0u : 32u, 32u}};
    const unsigned normalized_color_mask = mode == 2 || mode == 5 ? 15u : 0u;
    struct {bool stencil_enable, z_enable, z_write_enable;} normalized_depth_control{
        mode == 6, mode == 7 || mode == 8, mode == 7};
    const auto skips_draw = [&] {
'''+source[start:end]+r'''
      return false;
    };
    assert(skips_draw() == (mode == 1 || mode == 2 || mode == 8));
  }
}
''')


def test_texture_fast_path_checks_invalidation_before_reusing_bindings(sdk_source, tmp_path):
    from prepare_native_assets_sdk import patch_texture_requests

    source = subprocess.check_output([
        'git', '-C', str(sdk_source), 'show', 'HEAD:src/graphics/pipeline/texture/cache.cpp',
    ], text=True)
    source = patch_texture_requests(source)
    start = source.index('  // CH2K8 avoid a write to the invalidation flag')
    end = source.index('  // Update the texture keys', start)
    execute(tmp_path, r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#define COUNT_profile_set(...)
int main() {
  uint32_t texture_bindings_in_sync_ = 1;
  std::atomic<bool> texture_became_outdated_{false};
  uint32_t processed = 0;
  auto ResetTextureBindings = [&] { texture_bindings_in_sync_ = 0; };
  auto request = [&](uint32_t used_texture_mask) {
'''+source[start:end]+r'''
    processed = textures_remaining;
  };
  request(1);
  assert(processed == 0);
  request(3);
  assert(processed == 2);
  texture_became_outdated_.store(true, std::memory_order_release);
  request(0);
  assert(texture_bindings_in_sync_ == 0 && !texture_became_outdated_);
  request(3);
  assert(processed == 3);
}
''')


def test_fetch_packets_preserve_unchanged_texture_and_vertex_slots(sdk_source, tmp_path):
    from prepare_native_gpu_sdk import patch_backend

    source = patch_backend(original(sdk_source, 'command_processor'), 'd3d12')
    start = source.index('    if (REXCVAR_GET(ch2k8_native_constants)) {\n'
                         '      // Only invalidate fetch slots')
    end = source.index('    memory::copy_and_swap(', start)
    execute(tmp_path, r'''
#include <bit>
#include <cassert>
#include <cstdint>
#define REXCVAR_GET(flag) true
namespace rex { using std::byteswap; uint32_t byte_swap(uint32_t value) {return byteswap(value);} }
int main() {
  constexpr uint32_t XE_GPU_REG_SHADER_CONSTANT_FETCH_00_0 = 1;
  struct { uint32_t values[193]{}; } registers;
  auto* register_file_ = &registers;
  constexpr uint32_t start_index = 121, num_registers = 24;
  uint32_t base[num_registers]{};
  struct { bool up_to_date = true; } cbuffer_binding_fetch_;
  struct Cache {
    uint32_t invalidated = 0;
    void InvalidateTextureFetchMask(uint32_t mask) {invalidated |= mask;}
  } cache;
  auto* texture_cache_ = &cache;
  uint64_t vertex_buffers_in_sync_[2]{UINT64_MAX, UINT64_MAX};
  auto write = [&] {
'''+source[start:end]+r'''
    assert(false);
  };
  write();
  assert(cbuffer_binding_fetch_.up_to_date && !cache.invalidated);
  base[1] = rex::byte_swap(0x12345678u);
  base[8] = rex::byte_swap(0x87654321u);
  write();
  assert(!cbuffer_binding_fetch_.up_to_date);
  assert(cache.invalidated == ((1u << 20) | (1u << 21)));
  assert(vertex_buffers_in_sync_[0] == ~(uint64_t(1) << 60));
  assert(vertex_buffers_in_sync_[1] == ~uint64_t(1));
  assert(registers.values[122] == 0x12345678u && registers.values[129] == 0x87654321u);
}
''')


def test_shared_memory_fast_path_keeps_range_validation_and_merging(sdk_source, tmp_path):
    from prepare_native_assets_sdk import patch_shared_memory_requests

    source = subprocess.check_output([
        'git', '-C', str(sdk_source), 'show', 'HEAD:src/graphics/shared_memory.cpp',
    ], text=True)
    source = patch_shared_memory_requests(source)
    start = source.index('  // CH2K8 keep single-range requests off the heap.')
    end = source.index('  SCOPE_profile_cpu_f("gpu");', start)
    execute(tmp_path, r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <span>
#include <utility>
#include <vector>
int main() {
  constexpr uint32_t kBufferSize = 1024;
  using Range = std::pair<uint32_t, uint32_t>;
  std::vector<Range> result;
  auto run = [&](std::span<const Range> input) {
    const auto* ranges = input.data();
    auto count = input.size();
'''+source[start:end]+r'''
    assert(count != 1 || merged_ranges.data() == ranges);
    result.assign(merged_ranges.begin(), merged_ranges.end());
    return true;
  };
  assert(run(std::vector<Range>{{1025, 0}}) && result.empty());
  assert(!run(std::vector<Range>{{1025, 1}}));
  assert(!run(std::vector<Range>{{1023, 2}}));
  assert(run(std::vector<Range>{{1023, 1}}));
  assert((result == std::vector<Range>{{1023, 1}}));
  assert(run(std::vector<Range>{{12, 4}, {50, 3}, {10, 4}, {16, 2}}));
  assert((result == std::vector<Range>{{10, 8}, {50, 3}}));
}
''')


def test_short_gpu_waits_fall_back_on_timer_failure(sdk_source, tmp_path):
    from prepare_native_gpu_sdk import patch_common

    original_source = subprocess.check_output([
        'git', '-C', str(sdk_source), 'show', 'HEAD:src/graphics/command_processor.cpp',
    ], text=True)
    source = patch_sync(patch_common(original_source), 'common')
    start = source.index('void SleepForGpuPacket(')
    end = source.index('}  // namespace', start)
    execute(tmp_path, r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#define REXCVAR_GET(flag) enabled
using HANDLE = void*;
struct LARGE_INTEGER { int64_t QuadPart; };
constexpr unsigned CREATE_WAITABLE_TIMER_HIGH_RESOLUTION = 2, TIMER_MODIFY_STATE = 2,
                   SYNCHRONIZE = 0x100000, FALSE = 0, WAIT_OBJECT_0 = 0;
unsigned armed = 0, slept = 0, waits = 0;
bool enabled = true, arm_success = true, wait_success = true;
int handle;
HANDLE CreateWaitableTimerExW(void*, void*, unsigned, unsigned) {return &handle;}
void CloseHandle(HANDLE) {}
bool SetWaitableTimer(HANDLE, LARGE_INTEGER* due, unsigned, void*, void*, unsigned) {
  assert(due->QuadPart == -10000);
  ++armed;
  return arm_success;
}
unsigned WaitForSingleObject(HANDLE, unsigned timeout) {
  assert(timeout == 16);
  ++waits;
  return wait_success ? WAIT_OBJECT_0 : 258;
}
namespace rex::thread {
void Sleep(std::chrono::milliseconds duration) {slept += unsigned(duration.count());}
}
'''+source[start:end]+r'''
int main() {
  SleepForGpuPacket(1);
  assert(armed == 1 && waits == 1 && slept == 0);
  SleepForGpuPacket(5);
  assert(armed == 1 && slept == 5);
  enabled = false;
  SleepForGpuPacket(1);
  assert(armed == 1 && slept == 6);
  enabled = true;
  arm_success = false;
  SleepForGpuPacket(1);
  assert(armed == 2 && waits == 1 && slept == 7);
  arm_success = true;
  wait_success = false;
  SleepForGpuPacket(1);
  assert(armed == 3 && waits == 2 && slept == 8);
}
''')


def test_shader_translation_fast_path_survives_variant_removal(sdk_source, tmp_path):
    from prepare_native_shader_sdk import patch_translation_cache

    source = subprocess.check_output([
        'git', '-C', str(sdk_source), 'show', 'HEAD:src/graphics/pipeline/shader/shader.cpp',
    ], text=True)
    source = patch_translation_cache(source)
    start = source.index('Shader::Translation* Shader::GetOrCreateTranslation(')
    end = source.index('std::pair<std::filesystem::path', start)
    execute(tmp_path, r'''
#include <cassert>
#include <cstdint>
#include <unordered_map>
struct Shader {
  struct Translation {
    uint64_t key;
    uint64_t modification() const { return key; }
  };
  Translation* CreateTranslationInstance(uint64_t key) { return new Translation{key}; }
  Translation* GetOrCreateTranslation(uint64_t key, bool* is_new);
  void DestroyTranslation(uint64_t key);
  std::unordered_map<uint64_t, Translation*> translations_;
  Translation* last_translation_ = nullptr;
};
'''+source[start:end]+r'''
int main() {
  Shader shader;
  bool created = false;
  auto* first = shader.GetOrCreateTranslation(0, &created);
  assert(created && first->modification() == 0);
  assert(shader.GetOrCreateTranslation(0, &created) == first && !created);
  assert(shader.GetOrCreateTranslation(2, &created)->modification() == 2 && created);
  shader.DestroyTranslation(0);
  assert(shader.GetOrCreateTranslation(2, &created)->modification() == 2 && !created);
  shader.DestroyTranslation(2);
  assert(shader.GetOrCreateTranslation(2, &created)->modification() == 2 && created);
  shader.DestroyTranslation(2);
}
''')
