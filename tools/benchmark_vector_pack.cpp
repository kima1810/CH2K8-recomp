// Local correctness and timing comparison; no game bytes are required.
#include "packed_vector_optimized.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

void scalar(PPCVRegister &destination, const PPCVRegister &source,
            PPCRegister &temporary, PPCVRegister &scratch, unsigned half) {
  scratch.u64[0] = 0;
  for (unsigned component = 0; component < 4; ++component) {
    temporary.u32 = source.u32[3 - component];
    scratch.u32[2] = component < 3 ? 0x40380001u : 0x40400000u;
    if (!(temporary.f32 >= scratch.f32[2]))
      temporary.u32 = scratch.u32[2];
    scratch.u32[2] = component < 3 ? 0x4047FFFFu : 0x4040000Fu;
    if (temporary.f32 > scratch.f32[2])
      temporary.u32 = scratch.u32[2];
    scratch.u64[0] |=
        uint64_t(temporary.u32 & (component < 3 ? 0xFFFFFu : 0xFu))
        << (component * 20);
  }
  destination.u64[half] = scratch.u64[0];
}
void check(PPCVRegister input) {
  for (unsigned half = 0; half < 2; ++half) {
    for (bool alias : {false, true}) {
      PPCVRegister a = input, b = input, sa{}, sb{};
      PPCRegister ta{}, tb{};
      std::memset(&sa, 0x5A, sizeof(sa));
      sb = sa;
      std::memset(&ta, 0xA5, sizeof(ta));
      tb = ta;
      scalar(a, alias ? a : input, ta, sa, half);
      Ch2k8PackBiased64(b, alias ? b : input, tb, sb, half);
      if (std::memcmp(&a, &b, sizeof(a)) || std::memcmp(&sa, &sb, sizeof(sa)) ||
          std::memcmp(&ta, &tb, sizeof(ta))) {
        puts("Bit mismatch");
        std::exit(2);
      }
    }
  }
}
uint32_t random_word(uint32_t &state) {
  state ^= state << 13;
  state ^= state >> 17;
  state ^= state << 5;
  return state;
}
volatile uint64_t checksum;
template <bool Fast> double measure(const std::vector<PPCVRegister> &inputs) {
  PPCVRegister result{}, scratch{};
  PPCRegister temporary{};
  uint64_t sum = 0;
  const auto begin = std::chrono::steady_clock::now();
  for (unsigned repeat = 0; repeat < 64; ++repeat)
    for (const auto &value : inputs) {
      if constexpr (Fast)
        Ch2k8PackBiased64(result, value, temporary, scratch, 0);
      else
        scalar(result, value, temporary, scratch, 0);
      sum += result.u64[0];
    }
  const auto end = std::chrono::steady_clock::now();
  checksum = sum;
  return std::chrono::duration<double, std::nano>(end - begin).count() /
         (64 * inputs.size());
}
int main() {
  const uint32_t special[] = {
      0,          0x80000000, 0x3F800000, 0x40380000, 0x40380001, 0x40400000,
      0x4040000F, 0x4047FFFF, 0x40480000, 0x7F800000, 0xFF800000, 0x7FC00000,
      0x7F800001, 0xFFC00000, 0xFF800001, 1,          0x80000001};
  uint64_t cases = 0;
  const auto original_csr = simde_mm_getcsr();
  for (unsigned rounding = 0; rounding < 4; ++rounding) {
    for (bool flush : {false, true}) {
      simde_mm_setcsr(0x1F80 | (rounding << 13) | (flush ? 0x8040 : 0));
      for (auto a : special)
        for (auto b : special) {
          PPCVRegister value{};
          value.u32[0] = a;
          value.u32[1] = b;
          value.u32[2] = a;
          value.u32[3] = b;
          check(value);
          ++cases;
        }
    }
  }
  simde_mm_setcsr(original_csr);
  uint32_t state = 0x6E624EB7;
  for (unsigned i = 0; i < 250000; ++i) {
    PPCVRegister value{};
    for (auto &lane : value.u32)
      lane = random_word(state);
    check(value);
    ++cases;
  }
  std::vector<PPCVRegister> inputs(65536);
  for (auto &value : inputs) {
    for (unsigned lane = 1; lane < 4; ++lane)
      value.u32[lane] = 0x40380000 + random_word(state) % 0x100001;
    value.u32[0] = 0x40400000 + random_word(state) % 16;
    check(value);
    ++cases;
  }
  printf("validated_vectors,%llu\ntrial,baseline_ns,optimized_ns\n",
         (unsigned long long)cases);
  measure<false>(inputs);
  measure<true>(inputs);
  for (unsigned trial = 0; trial < 8; ++trial) {
    double baseline, optimized;
    if (trial & 1) {
      optimized = measure<true>(inputs);
      baseline = measure<false>(inputs);
    } else {
      baseline = measure<false>(inputs);
      optimized = measure<true>(inputs);
    }
    printf("%u,%.6f,%.6f\n", trial, baseline, optimized);
  }
}
