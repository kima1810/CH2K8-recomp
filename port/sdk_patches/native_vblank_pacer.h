#pragma once
#include <algorithm>
#include <chrono>
#include <cstdint>
namespace rex::ui::ch2k8 {
// A successful DXGI wait is not necessarily a real wait (headless, remote or
// driver configurations may return immediately). Never turn that into UI ticks.
class VBlankPacer {
public:
  using Clock=std::chrono::steady_clock;
  using Time=Clock::time_point;
private:
  std::chrono::nanoseconds period_{16666666};
  Time next_{};
  uint32_t fast_=0;
  bool timer_=false;
public:
  void Reset(uint32_t refresh_hz,Time now) {
    if(refresh_hz<24 || refresh_hz>1000)refresh_hz=60;
    period_=std::chrono::nanoseconds(1000000000ull/refresh_hz);
    fast_=0;timer_=false;next_=now+period_;
  }
  bool Observe(Time start,Time finished) {
    const auto threshold=std::min(period_/8,std::chrono::nanoseconds(1000000));
    fast_=finished-start<threshold?fast_+1:0;
    if(fast_<3)return false;
    timer_=true;next_=finished+period_;return true;
  }
  bool timer() const{return timer_;}
  Time Deadline(Time now) {
    if(next_<=now)next_=now+period_;
    return next_;
  }
  void Delivered(Time now) {
    next_+=period_;
    if(next_<=now)next_=now+period_;
  }
};
}
