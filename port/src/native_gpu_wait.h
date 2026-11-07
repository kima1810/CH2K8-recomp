#pragma once
#include <cstdint>

struct Ch2k8GpuWaitStats {
  uint64_t waits=0,notifications=0,timeouts=0;
  uint32_t counter_address=0;
  double wall_ms=0,window_ms=0,thread_cpu_ms=-1;
};
using Ch2k8GpuWaitStatsSink=void(*)(const Ch2k8GpuWaitStats&);
void Ch2k8ConfigureGpuWait(bool enabled,Ch2k8GpuWaitStatsSink sink=nullptr);

class Ch2k8GpuWait {
  bool enabled_;
  unsigned spins_=0;
  uint32_t address_=0,write_address_=0;
  bool checked_=false,readable_=false;
public:
  Ch2k8GpuWait();
  bool enabled() const{return enabled_;}
  void Poll(uint8_t* base,uint32_t address,uint32_t observed,
            uint32_t write_address,uint32_t observed_write);
};
