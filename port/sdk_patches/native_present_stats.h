#pragma once
#include <rex/cvar.h>
#include <rex/logging.h>
#include <array>
#include <chrono>
#include <cstdint>
#ifdef _WIN32
#include <windows.h>
#endif
REXCVAR_DECLARE(bool,ch2k8_present_stats);
namespace rex::ui::ch2k8 {
enum class PresentStage { UITick,VBlank,Paint,Mailbox,Refresh,Publish,Fence,Queue,Present,Count };
class PresentScope {
  using Clock=std::chrono::steady_clock;
  struct Bin {uint64_t calls,wall_ns,cpu_ns,max_ns;};
  inline static thread_local std::array<Bin,size_t(PresentStage::Count)> bins_{};
  inline static thread_local Clock::time_point origin_=Clock::now();
  PresentStage stage_;bool enabled_;Clock::time_point start_{};uint64_t cpu_start_=0;
  static uint64_t CPUTime() {
#ifdef _WIN32
    FILETIME created,exited,kernel,user;
    if(GetThreadTimes(GetCurrentThread(),&created,&exited,&kernel,&user)) {
      ULARGE_INTEGER k{},u{};
      k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;
      u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;
      return (k.QuadPart+u.QuadPart)*100;
    }
#endif
    return 0;
  }
public:
  explicit PresentScope(PresentStage stage):stage_(stage),enabled_(REXCVAR_GET(ch2k8_present_stats)) {
    if(enabled_){start_=Clock::now();cpu_start_=CPUTime();}
  }
  ~PresentScope() {
    if(!enabled_)return;
    const auto now=Clock::now();
    const auto ns=uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(now-start_).count());
    auto& bin=bins_[size_t(stage_)];++bin.calls;bin.wall_ns+=ns;bin.cpu_ns+=CPUTime()-cpu_start_;
    if(ns>bin.max_ns)bin.max_ns=ns;
    const auto window=std::chrono::duration<double,std::milli>(now-origin_).count();
    if(window<1000)return;
    constexpr const char* names[]={"ui_tick","vblank","paint","mailbox","refresh","publish","fence","queue","present"};
    for(size_t i=0;i<bins_.size();++i) {
      const auto& b=bins_[i];if(!b.calls)continue;
      REXLOG_INFO("CH2K8_PRESENT stage={} calls={} wall_ms={} cpu_ms={} max_ms={} window_ms={}",
          names[i],b.calls,double(b.wall_ns)/1e6,double(b.cpu_ns)/1e6,double(b.max_ns)/1e6,window);
    }
    bins_={};origin_=now;
  }
};
}
