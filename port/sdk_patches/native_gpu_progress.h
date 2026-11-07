#pragma once
#include <atomic>
#include <chrono>
#include <cstdint>
#ifdef _WIN32
#include <windows.h>
#pragma comment(lib,"Synchronization.lib")
#else
#include <condition_variable>
#include <mutex>
#endif

namespace rex::graphics::ch2k8 {
class GpuProgress {
  std::atomic<uint64_t> serial_{0};
#ifndef _WIN32
  std::mutex mutex_;
  std::condition_variable condition_;
#endif
public:
  uint64_t Serial() const {return serial_.load(std::memory_order_acquire);}
  void Notify() {
#ifdef _WIN32
    static_assert(sizeof(serial_)==sizeof(uint64_t)&&std::atomic<uint64_t>::is_always_lock_free);
    serial_.fetch_add(1,std::memory_order_release);
    WakeByAddressAll(&serial_);
#else
    {
      std::lock_guard lock(mutex_);
      serial_.fetch_add(1,std::memory_order_release);
    }
    condition_.notify_all();
#endif
  }
  bool Wait(uint64_t observed,std::chrono::milliseconds timeout) {
#ifdef _WIN32
    // WaitOnAddress atomically checks the generation while registering the
    // sleeper. No guest thread owns a notification mutex when it blocks.
    const auto deadline=std::chrono::steady_clock::now()+timeout;
    while(Serial()==observed) {
      const auto now=std::chrono::steady_clock::now();
      if(now>=deadline)return false;
      const auto remaining=std::chrono::ceil<std::chrono::milliseconds>(deadline-now).count();
      const auto milliseconds=remaining>0xFFFFFFFEll?0xFFFFFFFEu:DWORD(remaining);
      WaitOnAddress(&serial_,&observed,sizeof(observed),milliseconds);
    }
    return true;
#else
    std::unique_lock lock(mutex_);
    return condition_.wait_for(lock,timeout,[&]{return Serial()!=observed;});
#endif
  }
};
inline GpuProgress& NativeGpuProgress(){static GpuProgress state;return state;}
}

#if defined(CH2K8_GPU_PROGRESS_EXPORTS) && defined(_WIN32)
extern "C" __declspec(dllexport) uint64_t Ch2k8GpuProgressSerialV1() {
  return rex::graphics::ch2k8::NativeGpuProgress().Serial();
}
extern "C" __declspec(dllexport) bool Ch2k8WaitGpuProgressV1(uint64_t serial,uint32_t milliseconds) {
  // Guest waits are always bounded, including when no matching counter moves.
  return rex::graphics::ch2k8::NativeGpuProgress().Wait(
      serial,std::chrono::milliseconds(milliseconds>1?1:milliseconds));
}
#endif
