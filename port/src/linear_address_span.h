#pragma once
#include <cstdint>

// Shares address arithmetic only. Permissions, access widths, volatile ordering
// and faults remain those of the original loads. The region cannot cross the
// Windows physical-alias boundary or wrap the guest address space.
class Ch2k8LinearAddressSpan {
  uintptr_t bias_=0;
public:
  bool Prepare(uint8_t* base,uint32_t start,uint64_t bytes) {
    const uint64_t end=uint64_t(start)+bytes;
    if(!bytes || end>0x100000000ull ||
       (start<0xE0000000u && end>0xE0000000ull))return false;
    bias_=reinterpret_cast<uintptr_t>(base)+(start>=0xE0000000u?4096:0);
    return true;
  }
  uint8_t* Address(uint32_t ea) const{return reinterpret_cast<uint8_t*>(bias_+uintptr_t(ea));}
};
