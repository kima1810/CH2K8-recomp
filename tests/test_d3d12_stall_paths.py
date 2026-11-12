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
    auto CheckSubmissionFence = [&](int) { ++polls; };
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
  for (int mode = 0; mode < 3; ++mode) {
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
    constexpr int fence_value = 4, fence_completion_event_ = 9, INFINITE = -1;
    bool queue_operations_done_since_submission_signal_ = true;
    auto WaitForSingleObject = [&](int event, int timeout) {
      assert(event == 9 && timeout == -1 && fence.armed == 1);
      ++waits;
    };
'''+source[start:end]+r'''
    assert(waits == (mode == 0));
    assert(errors == (mode != 0));
    assert(fence.armed == (mode != 1));
    assert(queue_operations_done_since_submission_signal_ == (mode != 0));
  }
}
''')
