// Correctness and timing comparison of biased packed-vector unpacking.
#include "packed_vector_optimized.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

void scalar(PPCVRegister &destination, const PPCVRegister &source,
            PPCRegister &temporary, PPCVRegister &scratch) {
  scratch.u64[0] = source.u64[0];
  for (unsigned component = 0; component < 3; ++component) {
    temporary.s32 = int64_t(scratch.u64[0] << (44 - component * 20)) >> 44;
    destination.u32[3 - component] = temporary.s32 == -524288
                                         ? 0x7FC00000u
                                         : uint32_t(temporary.s32 + 0x40400000);
  }
  destination.u32[0] = uint32_t(scratch.u64[0] >> 60) + 0x3F800000u;
}
void check(uint64_t packed, uint64_t other) {
  for (bool alias : {false, true}) {
    PPCVRegister input{}, a{}, b{}, sa{}, sb{};
    input.u64[0] = packed;
    input.u64[1] = other;
    a = input;
    b = input;
    std::memset(&sa, 0x5A, sizeof(sa));
    sb = sa;
    PPCRegister ta{}, tb{};
    std::memset(&ta, 0xA5, sizeof(ta));
    tb = ta;
    scalar(a, alias ? a : input, ta, sa);
    Ch2k8UnpackBiased64(b, alias ? b : input, tb, sb);
    if (std::memcmp(&a, &b, sizeof(a)) || std::memcmp(&sa, &sb, sizeof(sa)) ||
        std::memcmp(&ta, &tb, sizeof(ta)) || input.u64[0] != packed ||
        input.u64[1] != other) {
      puts("Bit mismatch");
      std::exit(2);
    }
  }
}
uint64_t next(uint64_t &state) {
  state ^= state << 13;
  state ^= state >> 7;
  state ^= state << 17;
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
        Ch2k8UnpackBiased64(result, value, temporary, scratch);
      else
        scalar(result, value, temporary, scratch);
      sum += result.u64[0] ^ result.u64[1];
    }
  const auto end = std::chrono::steady_clock::now();
  checksum = sum;
  return std::chrono::duration<double, std::nano>(end - begin).count() /
         (64 * inputs.size());
}
int main() {
  const uint64_t edges[] = {0, 1, 0x7FFFF, 0x80000, 0x80001, 0xFFFFF};
  uint64_t cases = 0, state = 0x123456789ABCDEF1;
  for (auto x : edges)
    for (auto y : edges)
      for (auto z : edges)
        for (uint64_t w = 0; w < 16; ++w) {
          check(x | (y << 20) | (z << 40) | (w << 60), ~state);
          ++cases;
        }
  for (unsigned i = 0; i < 1000000; ++i) {
    auto packed = next(state);
    check(packed, next(state));
    ++cases;
  }
  std::vector<PPCVRegister> inputs(65536);
  for (auto &v : inputs) {
    v.u64[0] = next(state);
    v.u64[1] = next(state);
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
