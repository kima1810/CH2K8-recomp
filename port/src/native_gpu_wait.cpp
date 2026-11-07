#include "native_gpu_wait.h"
#include <atomic>
#include <chrono>
#include <windows.h>

namespace {
std::atomic<bool> gpu_wait_enabled{true};
std::atomic<Ch2k8GpuWaitStatsSink> stats_sink{nullptr};
struct Api {
  HMODULE module=nullptr;
  using Serial=uint64_t(*)();
  using Wait=bool(*)(uint64_t,uint32_t);
  Serial serial=nullptr;Wait wait=nullptr;
  Api() {
    // Retain the DLL while callbacks can be used, including renderer shutdown.
    if(!GetModuleHandleExW(0,L"rexgpu-xenos.dll",&module))return;
    serial=reinterpret_cast<Serial>(GetProcAddress(module,"Ch2k8GpuProgressSerialV1"));
    wait=reinterpret_cast<Wait>(GetProcAddress(module,"Ch2k8WaitGpuProgressV1"));
    if(!serial||!wait){FreeLibrary(module);module=nullptr;serial=nullptr;wait=nullptr;}
  }
  ~Api(){if(module)FreeLibrary(module);}
};
const Api& GetApi(){static const Api api;return api;}
uint8_t* Address(uint8_t* base,uint32_t ea) {
  return reinterpret_cast<uint8_t*>(reinterpret_cast<uintptr_t>(base)+ea+(ea>=0xE0000000u?4096:0));
}
bool Readable(uint8_t* base,uint32_t ea) {
  if(ea&3)return false;
  if(!(ea<0x7F000000u||(ea>=0x80000000u&&ea<0xFFD00000u)))return false;
  MEMORY_BASIC_INFORMATION info{};
  const auto host=Address(base,ea);
  return VirtualQuery(host,&info,sizeof(info))==sizeof(info)&&info.State==MEM_COMMIT&&
      (info.Type==MEM_PRIVATE||info.Type==MEM_MAPPED)&&
      (info.Protect==PAGE_READONLY||info.Protect==PAGE_READWRITE||info.Protect==PAGE_WRITECOPY)&&
      uintptr_t(host)+4<=uintptr_t(info.BaseAddress)+info.RegionSize;
}
uint32_t Read(uint8_t* base,uint32_t ea) {
  return __builtin_bswap32(*reinterpret_cast<volatile uint32_t*>(Address(base,ea)));
}
void Record(bool notified,uint32_t address,double ms) {
  auto sink=stats_sink.load(std::memory_order_acquire);if(!sink)return;
  using Clock=std::chrono::steady_clock;
  thread_local Ch2k8GpuWaitStats stats;
  thread_local auto origin=Clock::now();
  const auto cpu_ticks=[](uint64_t& ticks) -> bool {
    FILETIME creation,exit,kernel,user;
    if(!GetThreadTimes(GetCurrentThread(),&creation,&exit,&kernel,&user))return false;
    ticks=(uint64_t(kernel.dwHighDateTime)<<32|kernel.dwLowDateTime)+
           (uint64_t(user.dwHighDateTime)<<32|user.dwLowDateTime);
    return true;
  };
  thread_local uint64_t cpu_origin=0;
  thread_local bool cpu_origin_valid=cpu_ticks(cpu_origin);
  ++stats.waits;stats.notifications+=notified;stats.timeouts+=!notified;
  stats.counter_address=address;stats.wall_ms+=ms;
  const auto now=Clock::now();
  if(now-origin>=std::chrono::seconds(1)) {
    uint64_t cpu_now=0;const bool cpu_valid=cpu_ticks(cpu_now);
    stats.window_ms=std::chrono::duration<double,std::milli>(now-origin).count();
    if(cpu_origin_valid&&cpu_valid&&cpu_now>=cpu_origin)stats.thread_cpu_ms=double(cpu_now-cpu_origin)/10000;
    sink(stats);stats={};origin=now;cpu_origin=cpu_now;cpu_origin_valid=cpu_valid;
  }
}
}

void Ch2k8ConfigureGpuWait(bool selected,Ch2k8GpuWaitStatsSink sink) {
  stats_sink.store(sink,std::memory_order_release);
  gpu_wait_enabled.store(selected,std::memory_order_release);
}
Ch2k8GpuWait::Ch2k8GpuWait():enabled_(gpu_wait_enabled.load(std::memory_order_acquire)){}
void Ch2k8GpuWait::Poll(uint8_t* base,uint32_t address,uint32_t observed,
                       uint32_t write_address,uint32_t observed_write) {
  if(!enabled_||++spins_<64)return;
  spins_=0;
  const auto& api=GetApi();if(!api.wait){enabled_=false;return;}
  if(address_!=address||write_address_!=write_address){checked_=false;address_=address;write_address_=write_address;}
  if(!checked_){readable_=Readable(base,address)&&Readable(base,write_address);checked_=true;}
  if(!readable_)return;
  // Observe the notification generation before rechecking both original words.
  // A producer racing this check either changes a word or changes the generation.
  const auto serial=api.serial();
  if(Read(base,address)!=observed||Read(base,write_address)!=observed_write)return;
  const auto sink=stats_sink.load(std::memory_order_acquire);
  const auto before=sink?std::chrono::steady_clock::now():std::chrono::steady_clock::time_point{};
  const bool notified=api.wait(serial,1);
  if(sink)Record(notified,address,std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-before).count());
}
