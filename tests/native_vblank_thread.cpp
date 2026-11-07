// Execute the production thread body against deterministic fake DXGI outputs.
#include "native_vblank_pacer.h"
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
bool pacing=true;
std::atomic<unsigned> warnings{0};
#define REXCVAR_GET(name) pacing
#define REXLOG_WARN(...) (++warnings)
#define SUCCEEDED(value) ((value)>=0)
constexpr unsigned ENUM_CURRENT_SETTINGS=0;
struct DXGI_OUTPUT_DESC {wchar_t DeviceName[32]{};};
struct DEVMODEW {unsigned dmSize=0,dmDisplayFrequency=0;};
bool EnumDisplaySettingsW(const wchar_t* name,unsigned,DEVMODEW* mode) {
  mode->dmDisplayFrequency=unsigned(name[0]);return true;
}
struct IDXGIOutput {
  std::atomic<unsigned> calls{0};unsigned delay=0,rate=180;
  std::function<int()> on_wait;
  int GetDesc(DXGI_OUTPUT_DESC* d){d->DeviceName[0]=wchar_t(rate);return 0;}
  int WaitForVBlank(){++calls;if(on_wait)return on_wait();if(delay)std::this_thread::sleep_for(std::chrono::milliseconds(delay));return 0;}
};
namespace Microsoft::WRL {
template<class T>class ComPtr {
  std::shared_ptr<T> p_;
public:
  ComPtr()=default;explicit ComPtr(std::shared_ptr<T> value):p_(std::move(value)){}
  T* Get() const{return p_.get();}T* operator->()const{return p_.get();}
  explicit operator bool()const{return bool(p_);}void Reset(){p_.reset();}
};
}
namespace rex::ui {
namespace ch2k8 {
enum class PresentStage {VBlank};struct PresentScope{explicit PresentScope(PresentStage){}};
}
class Presenter {
public:
  std::mutex dxgi_ui_tick_mutex_;
  std::condition_variable dxgi_ui_tick_control_condition_,dxgi_ui_tick_signal_condition_;
  Microsoft::WRL::ComPtr<IDXGIOutput> dxgi_ui_tick_output_;
  bool dxgi_ui_tick_thread_shutdown_=false,needed=true;
  uint64_t dxgi_ui_tick_last_vblank_=0;
  bool AreDXGIUITicksWaitable(const std::unique_lock<std::mutex>&) {
    return needed && !dxgi_ui_tick_thread_shutdown_ && bool(dxgi_ui_tick_output_);
  }
  void DXGIUITickThread();
};
#include "native_vblank_thread.inl"
}
using Presenter=rex::ui::Presenter;
using Ptr=Microsoft::WRL::ComPtr<IDXGIOutput>;
void WaitTicks(Presenter& p,uint64_t count) {
  std::unique_lock lock(p.dxgi_ui_tick_mutex_);
  assert(p.dxgi_ui_tick_signal_condition_.wait_for(lock,std::chrono::seconds(2),[&]{return p.dxgi_ui_tick_last_vblank_>=count;}));
}
void Stop(Presenter& p,std::thread& thread) {
  {std::lock_guard lock(p.dxgi_ui_tick_mutex_);p.dxgi_ui_tick_thread_shutdown_=true;}
  p.dxgi_ui_tick_control_condition_.notify_all();thread.join();
}
int main() {
  for(bool immediate:{false,true}) {
    warnings=0;pacing=true;Presenter p;auto output=std::make_shared<IDXGIOutput>();
    output->delay=immediate?0:5;p.dxgi_ui_tick_output_=Ptr(output);
    std::thread thread([&]{p.DXGIUITickThread();});WaitTicks(p,6);
    if(immediate) {
      assert(output->calls==3 && warnings==1);
      auto replacement=std::make_shared<IDXGIOutput>();replacement->rate=120;
      uint64_t next;
      {std::lock_guard lock(p.dxgi_ui_tick_mutex_);next=p.dxgi_ui_tick_last_vblank_+6;p.dxgi_ui_tick_output_=Ptr(replacement);}
      p.dxgi_ui_tick_control_condition_.notify_all();WaitTicks(p,next);
      assert(replacement->calls==3 && warnings==2);
    } else assert(warnings==0);
    Stop(p,thread);
  }
  // A failed wait on a replaced output must not reset the new monitor/output.
  warnings=0;Presenter p;auto first=std::make_shared<IDXGIOutput>(),second=std::make_shared<IDXGIOutput>();
  first->on_wait=[&]{std::lock_guard lock(p.dxgi_ui_tick_mutex_);p.dxgi_ui_tick_output_=Ptr(second);return -1;};
  p.dxgi_ui_tick_output_=Ptr(first);std::thread thread([&]{p.DXGIUITickThread();});WaitTicks(p,6);
  assert(first->calls==1 && second->calls==3 && warnings==1);Stop(p,thread);
  // The explicit baseline switch retains native DXGI behavior without detection.
  warnings=0;pacing=false;Presenter baseline;auto raw=std::make_shared<IDXGIOutput>();
  raw->on_wait=[&]{if(raw->calls>=100){std::lock_guard lock(baseline.dxgi_ui_tick_mutex_);baseline.dxgi_ui_tick_thread_shutdown_=true;}return 0;};
  baseline.dxgi_ui_tick_output_=Ptr(raw);std::thread original([&]{baseline.DXGIUITickThread();});original.join();
  assert(raw->calls==100 && warnings==0);
}
