// Bit-exact comparison and local CPU timing of shader-constant bookkeeping.
#include "native_constant_compare.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <random>
#include <windows.h>

__declspec(noinline) void BaselineChanged(const uint32_t* host,const uint32_t* guest,
    uint32_t first,uint32_t count,uint64_t (&changed)[8]) {
  for(uint32_t i=0;i<count;++i) if(host[i]!=__builtin_bswap32(guest[i])) {
    const auto vector=(first+i)>>2;changed[vector>>6]|=uint64_t(1)<<(vector&63);
  }
}
__declspec(noinline) bool BaselineUsed(const uint64_t* usage,const uint64_t* changed,uint32_t first,uint32_t last) {
  for(uint32_t index=first;index<=last;++index)
    if(usage[index>>6]&changed[index>>6]&(uint64_t(1)<<(index&63)))return true;
  return false;
}
__declspec(noinline) void NativeChanged(const uint32_t* h,const uint32_t* g,uint32_t f,uint32_t n,uint64_t (&c)[8]) {
  Ch2k8ChangedConstantVectors(h,g,f,n,c);
}
__declspec(noinline) bool NativeUsed(const uint64_t* u,const uint64_t* c,uint32_t f,uint32_t l) {
  return Ch2k8ChangedConstantsUsed(u,c,f,l);
}
int main() {
  std::mt19937 random(0x20261103);
  std::array<uint32_t,2048> host{},guest{};
  for(auto& word:host)word=random();
  for(unsigned i=0;i<2048;++i)guest[i]=__builtin_bswap32(host[i]);
  for(unsigned i=0;i<2048;i+=17)guest[i]^=1u<<(i&31);
  for(unsigned first=0;first<2048;++first)for(unsigned n:{0u,1u,3u,4u,7u,16u,97u,256u,1024u,2048u}) {
    const unsigned count=std::min(n,2048-first);
    uint64_t baseline[8]{},native[8]{};
    if(first&1)for(unsigned i=0;i<8;++i)baseline[i]=native[i]=uint64_t(1)<<((first+i)&63);
    BaselineChanged(host.data()+first,guest.data()+first,first,count,baseline);
    NativeChanged(host.data()+first,guest.data()+first,first,count,native);
    if(std::memcmp(baseline,native,sizeof(native)))return 1;
  }
  uint64_t usage[4],changed[4];
  for(unsigned pattern=0;pattern<16;++pattern) {
    for(unsigned i=0;i<4;++i) {usage[i]=uint64_t(random())<<32|random();changed[i]=pattern&1?0:~usage[i];}
    if(pattern&2)changed[pattern%4]|=uint64_t(1)<<(random()%64);
    for(unsigned first=0;first<256;++first)for(unsigned last=0;last<256;++last)
      if(BaselineUsed(usage,changed,first,last)!=NativeUsed(usage,changed,first,last))return 2;
  }
  // Both packet pointers end at inaccessible pages. SIMD must not read tails.
  auto* pages=static_cast<uint8_t*>(VirtualAlloc(nullptr,16384,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
  if(!pages)return 3;
  DWORD old;
  if(!VirtualProtect(pages+4096,4096,PAGE_NOACCESS,&old) || !VirtualProtect(pages+12288,4096,PAGE_NOACCESS,&old))return 4;
  for(unsigned count=0;count<=64;++count)for(unsigned first=0;first<8;++first) {
    auto* h=reinterpret_cast<uint32_t*>(pages+4096-count*4);
    auto* g=reinterpret_cast<uint32_t*>(pages+12288-count*4);
    for(unsigned i=0;i<count;++i){h[i]=random();g[i]=__builtin_bswap32(h[i]^(i%7==0));}
    uint64_t a[8]{},b[8]{};BaselineChanged(h,g,first,count,a);NativeChanged(h,g,first,count,b);
    if(std::memcmp(a,b,sizeof(a)))return 5;
  }
  VirtualFree(pages,0,MEM_RELEASE);
  puts("Exact changed masks, all usage spans, guarded packet tails passed");
  volatile uint64_t checksum=0;
  puts("kind,words,trial,baseline_ns,native_ns");
  for(unsigned count:{16u,64u,256u,1024u})for(unsigned trial=0;trial<3;++trial) {
    double timing[2];
    for(unsigned order=0;order<2;++order) {
      const unsigned native=order^(trial&1);
      auto begin=std::chrono::steady_clock::now();
      for(unsigned iteration=0;iteration<40000;++iteration) {
        uint64_t mask[8]{};
        if(native)NativeChanged(host.data(),guest.data(),0,count,mask);
        else BaselineChanged(host.data(),guest.data(),0,count,mask);
        checksum=checksum^mask[0];
      }
      timing[native]=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-begin).count()/40000;
    }
    printf("changed,%u,%u,%.3f,%.3f\n",count,trial,timing[0],timing[1]);
  }
  std::fill_n(usage,4,~uint64_t(0));std::fill_n(changed,4,0);
  for(unsigned trial=0;trial<3;++trial) {
    double timing[2];
    for(unsigned order=0;order<2;++order) {
      const unsigned native=order^(trial&1);auto begin=std::chrono::steady_clock::now();
      for(unsigned iteration=0;iteration<100000;++iteration)
        checksum=checksum^(native?NativeUsed(usage,changed,0,255):BaselineUsed(usage,changed,0,255));
      timing[native]=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-begin).count()/100000;
    }
    printf("usage,256,%u,%.3f,%.3f\n",trial,timing[0],timing[1]);
  }
  return checksum?6:0;
}
