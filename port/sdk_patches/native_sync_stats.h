#pragma once
#include <rex/cvar.h>
#include <rex/logging.h>
#include <array>
#include <chrono>
REXCVAR_DECLARE(bool, ch2k8_gpu_stats);
namespace rex::graphics::ch2k8 {
enum class SyncKind {
  RingIdle, RegisterWait, SubmissionFence, PipelineWait, PipelineCreation, MemexportFallback, Count
};
struct SyncStats { uint64_t calls=0, ns=0, maximum=0; std::chrono::steady_clock::time_point origin=std::chrono::steady_clock::now(); };
class SyncScope {
  using Clock = std::chrono::steady_clock;
  SyncKind kind_; bool enabled_; Clock::time_point start_{};
  inline static thread_local std::array<SyncStats, size_t(SyncKind::Count)> stats_{};
public:
  explicit SyncScope(SyncKind kind):kind_(kind),enabled_(REXCVAR_GET(ch2k8_gpu_stats)) {
    if(enabled_) start_=Clock::now();
  }
  ~SyncScope() {
    if(!enabled_) return;
    auto now=Clock::now();
    auto ns=uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(now-start_).count());
    auto &s=stats_[size_t(kind_)]; ++s.calls; s.ns+=ns; if(ns>s.maximum) s.maximum=ns;
    auto window=std::chrono::duration<double>(now-s.origin).count();
    if(window<1.0) return;
    constexpr const char* names[]={"ring_idle","register_wait","submission_fence","pipeline_wait",
                                   "pipeline_creation", "memexport_fallback"};
    REXLOG_INFO("CH2K8 sync kind={} calls={} wall_ms={} max_ms={} window_ms={}",
      names[size_t(kind_)],s.calls,double(s.ns)/1e6,double(s.maximum)/1e6,window*1000);
    s=SyncStats{};
  }
};
class WaitDetail {
  using Clock=std::chrono::steady_clock;
  bool enabled_; Clock::time_point start_{};
  uint32_t info_,address_,reference_,mask_,interval_,polls_=0,value_=0;
public:
  WaitDetail(uint32_t info,uint32_t address,uint32_t reference,uint32_t mask,uint32_t interval)
    :enabled_(REXCVAR_GET(ch2k8_gpu_stats)),info_(info),address_(address),reference_(reference),mask_(mask),interval_(interval) {
    if(enabled_) start_=Clock::now();
  }
  void Poll(uint32_t value) {if(enabled_) {++polls_;value_=value;}}
  ~WaitDetail() {
    if(!enabled_ || !polls_) return;
    auto now=Clock::now(); auto ms=std::chrono::duration<double,std::milli>(now-start_).count();
    static thread_local auto previous=Clock::time_point{};
    if(ms<1 || now-previous<std::chrono::seconds(1)) return;
    previous=now;
    REXLOG_INFO("CH2K8 wait detail info={:X} address={:X} ref={:X} mask={:X} interval={:X} polls={} last={:X} wall_ms={}",
      info_,address_,reference_,mask_,interval_,polls_,value_,ms);
  }
};
} // namespace rex::graphics::ch2k8
