// Byte-preserving aligned-store candidate. No guest assets required.
#include "ch2k8_pch.h"
#include "vector_store_optimized.h"
#include <chrono>
#include <cstdio>
#include <cstring>

__declspec(noinline) void baseline(uint8_t *base, uint32_t ea,
                                   const PPCVRegister &source) {
  for (size_t i = 0; i < (16 - (ea & 15)); ++i)
    REX_STORE_U8(ea + i, source.u8[15 - i]);
}
__declspec(noinline) void candidate(uint8_t *base, uint32_t ea,
                                    const PPCVRegister &source) {
  Ch2k8StoreVectorLeft(base, ea, source);
}
template <bool Fast> double measure(unsigned alignment) {
  alignas(16) uint8_t memory[8192]{};
  PPCVRegister source{};
  for (unsigned i = 0; i < 16; ++i)
    source.u8[i] = uint8_t(i * 17);
  constexpr unsigned count = 4000000;
  auto started = std::chrono::steady_clock::now();
  for (unsigned i = 0; i < count; ++i) {
    const unsigned ea = ((i * 16) & 4095) + alignment;
    if constexpr (Fast)
      candidate(memory, ea, source);
    else
      baseline(memory, ea, source);
  }
  return std::chrono::duration<double, std::nano>(
             std::chrono::steady_clock::now() - started)
             .count() /
         count;
}
int main() {
  for (unsigned offset = 0; offset < 4096; ++offset) {
    uint8_t a[8192], b[8192];
    std::memset(a, 0xA5, sizeof(a));
    std::memcpy(b, a, sizeof(a));
    PPCVRegister source{};
    for (unsigned i = 0; i < 16; ++i)
      source.u8[i] = uint8_t(offset + i * 17);
    baseline(a, offset, source);
    candidate(b, offset, source);
    if (std::memcmp(a, b, sizeof(a)))
      return 2;
  }
  puts("validated_offsets,4096");
  puts("alignment,trial,baseline_ns,candidate_ns");
  for (unsigned alignment : {0u, 4u, 8u, 12u, 1u, 15u})
    for (unsigned trial = 0; trial < 7; ++trial) {
      double old_time, new_time;
      if (trial & 1) {
        new_time = measure<true>(alignment);
        old_time = measure<false>(alignment);
      } else {
        old_time = measure<false>(alignment);
        new_time = measure<true>(alignment);
      }
      printf("%u,%u,%.6f,%.6f\n", alignment, trial, old_time, new_time);
    }
}
