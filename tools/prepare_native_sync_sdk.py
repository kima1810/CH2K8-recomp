"""Apply checked synchronization instrumentation and readback reuse."""
from pathlib import Path
import subprocess
from prepare_native_gpu_sdk import replace_once, patch_common, patch_backend
ROOT=Path(__file__).resolve().parents[1]

def patch_sync_v1(text, kind):
    if '// CH2K8 sync attribution v1' in text: return text
    text=replace_once(text,'#include <rex/graphics/flags.h>',
        '#include <rex/graphics/flags.h>\n#include <rex/graphics/native_sync_stats.h>\n// CH2K8 sync attribution v1')
    if kind=='common':
        site='    if (write_ptr_index == 0xBAADF00D || read_ptr_index_ == write_ptr_index) {\n'
        text=replace_once(text,site,site+'      ch2k8::SyncScope native_sync(ch2k8::SyncKind::RingIdle);\n')
        site='bool CommandProcessor::ExecutePacketType3_WAIT_REG_MEM(memory::RingBuffer* reader, uint32_t packet,\n                                                       uint32_t count) {\n'
        text=replace_once(text,site,site+'  ch2k8::SyncScope native_sync(ch2k8::SyncKind::RegisterWait);\n')
    else:
        site='void D3D12CommandProcessor::CheckSubmissionFence(uint64_t await_submission) {\n'
        text=replace_once(text,site,site+'  ch2k8::SyncScope native_sync(ch2k8::SyncKind::SubmissionFence);\n')
    return text

def patch_sync_attribution(text, kind):
    text=patch_sync_v1(text,kind)
    if kind!='common' or '// CH2K8 wait detail v1' in text:return text
    start=text.index('bool CommandProcessor::ExecutePacketType3_WAIT_REG_MEM(')
    end=text.index('\n}\n',start)
    part=text[start:end]
    site='  bool is_memory = (wait_info & 0x10) != 0;\n'
    part=replace_once(part,site,site+'  // CH2K8 wait detail v1\n  ch2k8::WaitDetail native_wait(wait_info,poll_reg_addr,ref,mask,wait);\n')
    part=replace_once(part,'    if (!matched) {','    if (!matched) {\n      native_wait.Poll(value);')
    return text[:start]+part+text[end:]


def patch_sync_progress(text,kind):
    text=patch_sync_attribution(text,kind)
    if kind == 'd3d12':
        return patch_d3d12_waits(text)
    if kind!='common' or '// CH2K8 GPU progress notification v1' in text:return text
    text=replace_once(text,'#include <rex/graphics/native_sync_stats.h>',
        '#include <rex/graphics/native_sync_stats.h>\n#define CH2K8_GPU_PROGRESS_EXPORTS\n#include <rex/graphics/native_gpu_progress.h>\n// CH2K8 GPU progress notification v1')
    site='      memory::store_and_swap<uint32_t>(memory_->TranslatePhysical(read_ptr_writeback_ptr_),\n                                       read_ptr_index_);\n'
    text=replace_once(text,site,site+'      ch2k8::NativeGpuProgress().Notify();\n')
    site='  memory::store(memory_->TranslatePhysical(address), data_value);\n'
    return replace_once(text,site,site+'  ch2k8::NativeGpuProgress().Notify();\n')


def patch_sync(text, kind):
    text = patch_sync_progress(text, kind)
    marker = '// CH2K8 precise GPU packet waits.'
    if kind != 'common' or marker in text:
        return text
    text = replace_once(text, 'REXCVAR_DEFINE_BOOL(vsync,', f'''{marker}
#if REX_PLATFORM_WIN32
#include <Windows.h>

REXCVAR_DEFINE_BOOL(ch2k8_precise_packet_waits, false, "GPU/CH2K8",
                    "Use a high-resolution timer for short GPU packet waits")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

namespace {{
void SleepForGpuPacket(uint32_t milliseconds) {{
  if (milliseconds <= 4 && REXCVAR_GET(ch2k8_precise_packet_waits)) {{
    struct ThreadTimer {{
      HANDLE handle = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION,
                                             TIMER_MODIFY_STATE | SYNCHRONIZE);
      ~ThreadTimer() {{
        if (handle) CloseHandle(handle);
      }}
    }};
    thread_local ThreadTimer timer;
    LARGE_INTEGER due_time;
    due_time.QuadPart = -int64_t(milliseconds) * 10000;
    if (timer.handle && SetWaitableTimer(timer.handle, &due_time, 0, nullptr, nullptr, FALSE) &&
        WaitForSingleObject(timer.handle, 16) == WAIT_OBJECT_0) {{
      return;
    }}
  }}
  rex::thread::Sleep(std::chrono::milliseconds(milliseconds));
}}
}}  // namespace
#endif

REXCVAR_DEFINE_BOOL(vsync,''')
    start = text.index('bool CommandProcessor::ExecutePacketType3_WAIT_REG_MEM(')
    end = text.index('\n}\n', start)
    wait = text[start:end]
    wait = replace_once(wait, '  bool matched = false;', '''  // The physical mapping is stable for the lifetime of the packet. Reload its
  // contents on each poll because the guest can update them on another thread.
  const volatile uint32_t* poll_memory = is_memory
      ? reinterpret_cast<const volatile uint32_t*>(
            memory_->TranslatePhysical(poll_reg_addr & ~uint32_t(0x3)))
      : nullptr;
  bool matched = false;''')
    wait = replace_once(wait, '''      value =
          *reinterpret_cast<uint32_t*>(memory_->TranslatePhysical(poll_reg_addr & ~uint32_t(0x3)));''',
        '      value = *poll_memory;')
    wait = replace_once(wait, '          rex::thread::Sleep(std::chrono::milliseconds(wait / 0x100));', '''#if REX_PLATFORM_WIN32
          SleepForGpuPacket(wait / 0x100);
#else
          rex::thread::Sleep(std::chrono::milliseconds(wait / 0x100));
#endif''')
    wait = replace_once(wait, '''
        if (!worker_running_) {
          // Short-circuited exit.
          return false;
        }
      } else {
        rex::thread::MaybeYield();
      }''', '''
      } else {
        rex::thread::MaybeYield();
      }
      if (!worker_running_) {
        return false;
      }''')
    return text[:start] + wait + text[end:]


def patch_d3d12_waits_v1(text):
    marker = '// CH2K8 reuse the already-recorded memexport copy.'
    if marker in text:
        return text
    text = replace_once(text, '''  if (!previous_slot_ready) {
    IssueDraw_MemexportReadbackFullPath(total_size);
    readback.current_index = read_index;
    return true;
  }

  const uint8_t* readback_bytes = static_cast<const uint8_t*>(readback.mapped_data[read_index]);''',
        '''  uint32_t completed_index = read_index;
  if (!previous_slot_ready) {
    // CH2K8 reuse the already-recorded memexport copy.
    // Keep the synchronous fallback, but consume the current mapped slot
    // instead of allocating another buffer and recording the same copy again.
    ch2k8::SyncScope readback_wait(ch2k8::SyncKind::MemexportFallback);
    const uint64_t copy_submission = readback.submission_written[write_index];
    if (!AwaitAllQueueOperationsCompletion() || copy_submission > submission_completed_) {
      readback.current_index = read_index;
      return true;
    }
    completed_index = write_index;
  }

  const uint8_t* readback_bytes =
      static_cast<const uint8_t*>(readback.mapped_data[completed_index]);''')
    # Signal returns S_OK (zero). Combining it with && before SUCCEEDED
    # short-circuits event registration, then waits on the unarmed event.
    return replace_once(text, '''      if (SUCCEEDED(direct_queue->Signal(queue_operations_since_submission_fence_, fence_value) &&
                    SUCCEEDED(queue_operations_since_submission_fence_->SetEventOnCompletion(
                        fence_value, fence_completion_event_)))) {''',
        '''      if (SUCCEEDED(direct_queue->Signal(queue_operations_since_submission_fence_, fence_value)) &&
          SUCCEEDED(queue_operations_since_submission_fence_->SetEventOnCompletion(
              fence_value, fence_completion_event_))) {''')


def patch_d3d12_waits_v2(text):
    text = patch_d3d12_waits_v1(text)
    marker = '// CH2K8 retain readback buffers until their GPU writes complete.'
    if marker in text:
        return text
    text = replace_once(text, '  const uint64_t readback_key =\n      MakeMemexportReadbackKey',
        '''  // The cache key describes a single contiguous range. Multiple ranges
  // can have the same first address and total size but different destinations.
  if (memexport_ranges_.size() != 1) {
    return IssueDraw_MemexportReadbackFullPath(total_size);
  }
  const uint64_t readback_key =
      MakeMemexportReadbackKey''')
    text = replace_once(text, '  CheckSubmissionFence(0);\n  bool previous_slot_ready =',
        '''  // A cold slot goes directly to the synchronous fallback below.
  if (readback.submission_written[read_index] > submission_completed_) {
    CheckSubmissionFence(0);
  }
  bool previous_slot_ready =''')
    text = replace_once(text,
        '  ReadbackResolveMode readback_mode = GetReadbackResolveMode(REXCVAR_GET(d3d12_readback_resolve));\n'
        '  bool use_delayed_sync =',
        '  rb.submission_written[write_index] = submission_current_;\n\n'
        '  ReadbackResolveMode readback_mode = GetReadbackResolveMode(REXCVAR_GET(d3d12_readback_resolve));\n'
        '  bool use_delayed_sync =')
    text = replace_once(text, '    if (rb.buffers[write_index]) {\n      if (rb.mapped_data[write_index]) {',
        '''    if (rb.buffers[write_index]) {
      const uint64_t previous_submission = rb.submission_written[write_index];
      if (previous_submission > submission_completed_ &&
          (!AwaitAllQueueOperationsCompletion() || previous_submission > submission_completed_)) {
        buffer->Release();
        return true;
      }
      if (rb.mapped_data[write_index]) {''')
    text = replace_once(text, '    rb.buffers[write_index] = buffer;\n    rb.sizes[write_index] = size;',
        '    rb.buffers[write_index] = buffer;\n    rb.sizes[write_index] = size;\n'
        '    rb.submission_written[write_index] = 0;')
    text = replace_once(text, '''  } else if (!AwaitAllQueueOperationsCompletion()) {
    return true;
  }

  bool is_cache_miss = false;''', '''  }

  if (use_delayed_sync && rb.submission_written[read_index] > submission_completed_) {
    CheckSubmissionFence(0);
  }
  bool is_cache_miss = false;''')
    text = replace_once(text, '''  if (use_delayed_sync && (!rb.buffers[read_index] || written_length > rb.sizes[read_index] ||
                           !rb.mapped_data[read_index])) {
    is_cache_miss = true;
    read_index = write_index;
    if (!AwaitAllQueueOperationsCompletion()) {
      return true;
    }
  }''', '''  if (use_delayed_sync && (!rb.buffers[read_index] || written_length > rb.sizes[read_index] ||
                           !rb.mapped_data[read_index] || !rb.submission_written[read_index] ||
                           rb.submission_written[read_index] > submission_completed_)) {
    is_cache_miss = true;
    read_index = write_index;
  }
  if (read_index == write_index &&
      (!AwaitAllQueueOperationsCompletion() ||
       rb.submission_written[write_index] > submission_completed_)) {
    return true;
  }''')
    return replace_once(text, '    if (!evict) {\n      ++it;',
        f'''    {marker}
    if (!evict || readback.submission_written[0] > submission_completed_ ||
        readback.submission_written[1] > submission_completed_) {{
      ++it;''')


def patch_d3d12_waits_v3(text):
    text = patch_d3d12_waits_v2(text)
    if '// CH2K8 propagate fence failures.' in text:
        return text
    text = replace_once(text, 'void D3D12CommandProcessor::CheckSubmissionFence(uint64_t await_submission) {',
        '''// CH2K8 propagate fence failures.
bool D3D12CommandProcessor::CheckSubmissionFence(uint64_t await_submission) {
  if (device_removed_) return false;''')
    text = replace_once(text, '''    if (submission_open_) {
      EndSubmission(false);
    }
    // Ending an open submission''', '''    if (submission_open_ && !EndSubmission(false)) {
      return false;
    }
    // Ending an open submission''')
    text = replace_once(text, '''        WaitForSingleObject(fence_completion_event_, INFINITE);
        queue_operations_done_since_submission_signal_ = false;''', '''        if (WaitForSingleObject(fence_completion_event_, INFINITE) != WAIT_OBJECT_0) {
          REXGPU_ERROR("Failed to wait for an out-of-submission fence event");
          return false;
        }
        queue_operations_done_since_submission_signal_ = false;''')
    text = replace_once(text, '            "Direct3D 12 fence");\n      }',
                        '            "Direct3D 12 fence");\n        return false;\n      }')
    start = text.index('  uint64_t submission_completed_before = submission_completed_;')
    end = text.index('  // Reclaim command allocators.', start)
    text = text[:start]+'''  uint64_t completed = submission_fence_->GetCompletedValue();
  if (completed != UINT64_MAX && completed < await_submission) {
    if (FAILED(submission_fence_->SetEventOnCompletion(await_submission, fence_completion_event_))) {
      REXGPU_ERROR("Failed to register a submission fence event");
      return false;
    }
    PROFILE_CMD_BUFFER_STALL();
    if (WaitForSingleObject(fence_completion_event_, INFINITE) != WAIT_OBJECT_0) {
      REXGPU_ERROR("Failed to wait for a submission fence event");
      return false;
    }
    completed = submission_fence_->GetCompletedValue();
  }
  if (completed == UINT64_MAX) {
    auto* device = GetD3D12Provider().GetDevice();
    const HRESULT reason = device->GetDeviceRemovedReason();
    device_removed_ = true;
    LogDeviceRemovalDiagnostics(device, reason);
    if (graphics_system_) {
      graphics_system_->OnHostGpuLossFromAnyThread(reason != DXGI_ERROR_DEVICE_REMOVED);
    }
    return false;
  }
  const bool reached = completed >= await_submission;
  if (!reached) {
    REXGPU_ERROR("Failed to await a submission completion Direct3D 12 fence");
  }
  if (completed <= submission_completed_) {
    return reached;
  }
  submission_completed_ = completed;

'''+text[end:]
    text = replace_once(text, '  texture_cache_->CompletedSubmissionUpdated(submission_completed_);\n}',
                        '  texture_cache_->CompletedSubmissionUpdated(submission_completed_);\n  return reached;\n}')
    text = replace_once(text, '''  CheckSubmissionFence(is_opening_frame ? closed_frame_submissions_[frame_current_ % kQueueFrames]
                                        : 0);
  // TODO(Triang3l): If failed to await (completed submission < awaited frame
  // submission), do something like dropping the draw command that wanted to
  // open the frame.''', '''  if (!CheckSubmissionFence(is_opening_frame ? closed_frame_submissions_[frame_current_ % kQueueFrames]
                                             : 0)) {
    return false;
  }''')
    text = replace_once(text, '''  // Check if the device is still available.
  ID3D12Device* device = GetD3D12Provider().GetDevice();
  HRESULT device_removed_reason = device->GetDeviceRemovedReason();
  if (FAILED(device_removed_reason)) {
    device_removed_ = true;
    LogDeviceRemovalDiagnostics(device, device_removed_reason);
    if (graphics_system_) {
      graphics_system_->OnHostGpuLossFromAnyThread(device_removed_reason !=
                                                   DXGI_ERROR_DEVICE_REMOVED);
    }
    return false;
  }

''', '')
    text = replace_once(text, 'bool D3D12CommandProcessor::EndSubmission(bool is_swap) {\n',
                        'bool D3D12CommandProcessor::EndSubmission(bool is_swap) {\n'
                        '  if (device_removed_) return false;\n\n')
    text = replace_once(text, '  CheckSubmissionFence(query_submission);\n  if (submission_completed_ < query_submission) {',
                        '  if (!CheckSubmissionFence(query_submission)) {')
    for slot in ('readback', 'rb'):
        prefix = 'use_delayed_sync && ' if slot == 'rb' else ''
        condition = f'{prefix}{slot}.submission_written[read_index] > submission_completed_'
        text = replace_once(text, f'  if ({condition}) {{\n    CheckSubmissionFence(0);\n  }}',
                            f'  if ({condition} && !CheckSubmissionFence(0)) {{\n    return true;\n  }}')
    return replace_once(text, '''    direct_queue->Signal(submission_fence_, submission_current_++);

    submission_open_ = false;''', '''    const HRESULT signal = direct_queue->Signal(submission_fence_, submission_current_);
    submission_open_ = false;
    if (FAILED(signal)) {
      // The command list has already been executed. It cannot be retried or
      // tracked by the submission fence, so stop using this device.
      device_removed_ = true;
      LogDeviceRemovalDiagnostics(provider.GetDevice(), signal);
      if (graphics_system_) {
        graphics_system_->OnHostGpuLossFromAnyThread(signal != DXGI_ERROR_DEVICE_REMOVED);
      }
      return false;
    }
    ++submission_current_;''')


def patch_d3d12_waits_v4(text):
    text = patch_d3d12_waits_v3(text)
    if '// CH2K8 right-size scratch allocations.' in text:
        return text
    text = replace_once(text, '  size = rex::align(size, kScratchBufferSizeIncrement);',
        '''  // CH2K8 right-size scratch allocations.
  // Keep geometric growth for small buffers and the original step for large ones.
  if (size <= kScratchBufferSizeIncrement) {
    size = std::bit_ceil(std::max(size, UINT32_C(1) << 20));
  } else {
    if (size > UINT32_MAX - (kScratchBufferSizeIncrement - 1)) return nullptr;
    size = rex::align(size, kScratchBufferSizeIncrement);
  }''')
    text = replace_once(text, '''  scratch_buffer_ = buffer;
  scratch_buffer_size_ = size;''', '''  scratch_buffer_ = buffer;
  scratch_buffer_size_ = size;
  if (REXCVAR_GET(ch2k8_gpu_stats)) {
    REXGPU_INFO("CH2K8 scratch GPU allocation: {} MiB", size >> 20);
  }''')
    text = replace_once(text, '''  if (buffer == scratch_buffer_) {
    scratch_buffer_state_ = new_state;
  }''', '''  if (buffer == scratch_buffer_) {
    scratch_buffer_state_ = new_state;
    scratch_buffer_last_frame_ = frame_current_;
    scratch_buffer_last_submission_ = submission_current_;
  }''')
    return replace_once(text, '    EvictOldReadbackBuffers(readback_buffers_);',
        '''    // Trim a large transient buffer only after its last GPU use and 120 idle frames.
    if (scratch_buffer_size_ > kScratchBufferSizeIncrement && !scratch_buffer_used_ &&
        scratch_buffer_last_submission_ <= submission_completed_ &&
        frame_current_ > scratch_buffer_last_frame_ &&
        frame_current_ - scratch_buffer_last_frame_ >= 120) {
      if (REXCVAR_GET(ch2k8_gpu_stats)) {
        REXGPU_INFO("CH2K8 released idle scratch GPU allocation: {} MiB",
                    scratch_buffer_size_ >> 20);
      }
      ui::d3d12::util::ReleaseAndNull(scratch_buffer_);
      scratch_buffer_size_ = 0;
    }
    EvictOldReadbackBuffers(readback_buffers_);''')


def patch_d3d12_waits(text):
    text = patch_d3d12_waits_v4(text)
    if '// CH2K8 trim render targets without stalling.' in text:
        return text
    text = replace_once(text, '  frame_current_ = 1;\n  frame_completed_ = 0;',
        '  frame_current_ = 1;\n  frame_completed_ = 0;\n  next_render_target_trim_frame_ = 300;')
    return replace_once(text, '''  if (is_opening_frame) {
    // Update the completed frame index''', '''  if (is_opening_frame) {
    // CH2K8 trim render targets without stalling. ClearCache preserves targets
    // owning EDRAM data. No recorded or submitted commands may reference the
    // targets it releases, including work issued directly on the queue.
    if (!submission_open_ && !queue_operations_done_since_submission_signal_ &&
        submission_completed_ == submission_current_ - 1 &&
        frame_current_ >= next_render_target_trim_frame_) {
      next_render_target_trim_frame_ = frame_current_ + 300;
      const size_t before = render_target_cache_->GetCachedRenderTargetCount();
      if (before >= 16) {
        render_target_cache_->BeginFrame();
        render_target_cache_->ClearCache();
        const size_t after = render_target_cache_->GetCachedRenderTargetCount();
        if (REXCVAR_GET(ch2k8_gpu_stats) && after < before) {
          REXGPU_INFO("CH2K8 render-target cache trimmed: {} to {} entries", before, after);
        }
      }
    }
    // Update the completed frame index''')


def patch_fence_header(text):
    text = replace_once(text, '  void CheckSubmissionFence(uint64_t await_submission);',
                        '  bool CheckSubmissionFence(uint64_t await_submission);')
    return replace_once(text, '    CheckSubmissionFence(submission_current_);\n'
                        '    return submission_completed_ + 1 >= submission_current_;',
                        '    return CheckSubmissionFence(submission_current_);')


def patch_scratch_header(text):
    return replace_once(text, '  uint32_t scratch_buffer_size_ = 0;',
                        '  uint32_t scratch_buffer_size_ = 0;\n'
                        '  uint64_t scratch_buffer_last_frame_ = 0;\n'
                        '  uint64_t scratch_buffer_last_submission_ = 0;')


def patch_render_target_header(text):
    return replace_once(text, '  virtual void ClearCache();',
        '  virtual void ClearCache();\n'
        '  size_t GetCachedRenderTargetCount() const { return render_targets_.size(); }')


def prepare_sync(source):
    changes={}
    for relative,kind in [('src/graphics/command_processor.cpp','common'),('src/graphics/d3d12/command_processor.cpp','d3d12')]:
        original=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+relative],text=True)
        previous=patch_common(original) if kind=='common' else patch_backend(original,kind)
        expected=patch_sync(previous,kind); path=source/relative
        attributed = patch_sync_attribution(previous, kind)
        prior_waits = patch_d3d12_waits_v1(attributed) if kind == 'd3d12' else expected
        prior_readbacks = patch_d3d12_waits_v2(attributed) if kind == 'd3d12' else expected
        prior_fences = patch_d3d12_waits_v3(attributed) if kind == 'd3d12' else expected
        prior_scratch = patch_d3d12_waits_v4(attributed) if kind == 'd3d12' else expected
        if path.read_text(encoding='utf-8') not in (previous,patch_sync_v1(previous,kind),attributed,prior_waits,prior_readbacks,prior_fences,prior_scratch,patch_sync_progress(previous,kind),expected):
            raise ValueError('Unreviewed synchronization source: '+relative)
        changes[path]=expected
    relative = 'include/rex/graphics/d3d12/command_processor.h'
    original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:'+relative], text=True)
    path = source/relative
    prior_header = patch_fence_header(original)
    prior_scratch_header = patch_scratch_header(prior_header)
    expected = replace_once(prior_scratch_header, '  uint64_t frame_completed_ = 0;',
        '  uint64_t frame_completed_ = 0;\n  uint64_t next_render_target_trim_frame_ = 300;')
    if path.read_text(encoding='utf-8') not in (original, prior_header, prior_scratch_header, expected):
        raise ValueError('Unreviewed synchronization source: '+relative)
    changes[path] = expected
    relative = 'include/rex/graphics/pipeline/render_target/cache.h'
    original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:'+relative], text=True)
    path = source/relative
    expected = patch_render_target_header(original)
    if path.read_text(encoding='utf-8') not in (original, expected):
        raise ValueError('Unreviewed render-target cache header: '+relative)
    changes[path] = expected
    for path,text in changes.items():
        if path.read_text(encoding='utf-8')!=text:path.write_text(text,encoding='utf-8',newline='\n')
    path=source/'include/rex/graphics/native_sync_stats.h'; data=(ROOT/'port/sdk_patches/native_sync_stats.h').read_bytes()
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or path.read_bytes()!=data:path.write_bytes(data)

    path=source/'include/rex/graphics/native_gpu_progress.h';data=(ROOT/'port/sdk_patches/native_gpu_progress.h').read_bytes()
    if not path.exists() or path.read_bytes()!=data:path.write_bytes(data)
