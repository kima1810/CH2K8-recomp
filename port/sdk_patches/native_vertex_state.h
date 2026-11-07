#pragma once
#include <cstdint>

namespace rex::graphics::ch2k8 {
// Zero retains the dynamic path. 1..4 encode the exact common Endian value.
// Inspect only fetch constants actually referenced by this analyzed shader.
template<class FetchEndian>
uint32_t SelectVertexEndian(const uint32_t (&used)[3], FetchEndian&& fetch) {
  uint32_t common=4;
  for(uint32_t block=0;block<3;++block) {
    uint32_t remaining=used[block];
    for(uint32_t bit=0;remaining;++bit,remaining>>=1) {
      if(!(remaining&1))continue;
      const uint32_t endian=fetch(block*32+bit);
      if(endian>3 || (common!=4 && common!=endian))return 0;
      common=endian;
    }
  }
  return common==4?0:common+1;
}
} // namespace rex::graphics::ch2k8
