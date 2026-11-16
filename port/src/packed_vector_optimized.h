#pragma once
#include <rex/ppc.h>
#include "geometry_batch_optimized.h"
#include <simde/x86/sse4.1.h>

// [CONFIRMED] Bit-equivalent to the corrected type-6 biased-float pack.
// Integer comparisons avoid changing the host FP exception/rounding state.
inline void Ch2k8PackBiased64(PPCVRegister &destination,
                              const PPCVRegister &source,
                              PPCRegister &temporary, PPCVRegister &scratch,
                              unsigned half) {
  // Keep the PPC register layout [w,z,y,x]; clamp constants follow that order.
  // Extracting fields directly avoids a separate lane-reversal instruction.
  auto value = simde_mm_load_si128(
      reinterpret_cast<const simde__m128i *>(source.u32));
  const auto minimum =
      simde_mm_set_epi32(0x40380001, 0x40380001, 0x40380001, 0x40400000);
  const auto maximum =
      simde_mm_set_epi32(0x4047FFFF, 0x4047FFFF, 0x4047FFFF, 0x4040000F);
  // Negative bit patterns clamp to minimum under signed comparison. Positive
  // NaNs must also select minimum, while positive infinity clamps to maximum.
  auto nan = simde_mm_cmpgt_epi32(value, simde_mm_set1_epi32(0x7F800000));
  auto clamped =
      simde_mm_min_epi32(simde_mm_max_epi32(value, minimum), maximum);
  clamped = simde_mm_blendv_epi8(clamped, minimum, nan);
  // Form x/y and z/w pairs in separate 64-bit lanes, then join them.
  // This keeps the bit packing in SIMD registers until the final write.
  const auto ordered = simde_mm_shuffle_epi32(clamped, 0x1B);
  const auto even = simde_mm_and_si128(ordered, simde_mm_set_epi32(0, 0xFFFFF, 0, 0xFFFFF));
  const auto odd = simde_mm_and_si128(ordered, simde_mm_set_epi32(0xF, 0, 0xFFFFF, 0));
  const auto pairs = simde_mm_or_si128(even, simde_mm_srli_epi64(odd, 12));
  const auto upper = simde_mm_slli_epi64(simde_mm_srli_si128(pairs, 8), 40);
  scratch.u64[0] = uint64_t(simde_mm_cvtsi128_si64(simde_mm_or_si128(pairs, upper)));
  scratch.u32[2] = 0x4040000F;
  temporary.u32 = uint32_t(simde_mm_cvtsi128_si32(clamped));
  destination.u64[half] = scratch.u64[0];
}

// [CONFIRMED] Type-6 unpack: byte selection aligns the three 20-bit fields and
// the high nibble, then parallel integer arithmetic restores biased float bits.
inline void Ch2k8UnpackBiased64(PPCVRegister &destination,
                                const PPCVRegister &source,
                                PPCRegister &temporary, PPCVRegister &scratch) {
  const uint64_t packed = source.u64[0];
  // Gather directly into destination order [w,z,y,x], including nibble shifts.
  auto fields = simde_mm_shuffle_epi8(
      simde_mm_cvtsi64_si128(int64_t(packed)),
      simde_mm_set_epi32(int(0x80020100u), int(0x80040302u), int(0x80070605u),
                         int(0x80808007u)));
  fields = simde_mm_blend_epi16(fields, simde_mm_srli_epi32(fields, 4), 0x33);
  auto signed_fields = simde_mm_srai_epi32(simde_mm_slli_epi32(fields, 12), 12);
  auto bits = simde_mm_add_epi32(
      signed_fields,
      simde_mm_set_epi32(0x40400000, 0x40400000, 0x40400000, 0x3F800000));
  bits = simde_mm_blendv_epi8(
      bits, simde_mm_set1_epi32(0x7FC00000),
      simde_mm_cmpeq_epi32(signed_fields, simde_mm_set1_epi32(-524288)));
  scratch.u64[0] = packed;
  temporary.s32 = simde_mm_extract_epi32(signed_fields, 1);
  simde_mm_store_si128(reinterpret_cast<simde__m128i *>(destination.u32), bits);
}

inline void Ch2k8UnpackColor(PPCVRegister& destination, const PPCVRegister& source,
                            PPCVRegister& scratch) {
  const auto bytes = simde_mm_cvtsi32_si128(source.s32[0]);
  const auto channels = simde_mm_shuffle_epi8(bytes, simde_mm_set_epi32(
      int(0x80808002u), int(0x80808001u), int(0x80808000u), int(0x80808003u)));
  const auto biased = simde_mm_or_si128(channels, simde_mm_set1_epi32(0x3F800000));
  simde_mm_store_si128(reinterpret_cast<simde__m128i*>(scratch.u32), biased);
  destination = scratch;
}

inline void Ch2k8UnpackBiased32(PPCVRegister& destination, const PPCVRegister& source,
                               PPCRegister& temporary, PPCVRegister& scratch) {
  const uint32_t packed = source.u32[0];
  const auto shifted = simde_mm_mullo_epi32(simde_mm_set1_epi32(int32_t(packed)),
      simde_mm_set_epi32(1 << 22, 1 << 12, 1 << 2, 0));
  const auto fields = simde_mm_srai_epi32(shifted, 22);
  auto biased = simde_mm_add_epi32(fields, simde_mm_set1_epi32(0x40400000));
  // Only the low packed component maps the signed minimum to a NaN.
  const auto sentinel = simde_mm_cmpeq_epi32(fields, simde_mm_set_epi32(-512, 512, 512, 512));
  biased = simde_mm_blendv_epi8(biased, simde_mm_set1_epi32(0x7FC00000), sentinel);
  scratch.u32[0] = (packed >> 30) | 0x3F800000u;
  temporary.s32 = simde_mm_extract_epi32(fields, 1);
  biased = simde_mm_insert_epi32(biased, int32_t(scratch.u32[0]), 0);
  simde_mm_store_si128(reinterpret_cast<simde__m128i*>(destination.u32), biased);
}

// Selected once per guest function call, never per vector instruction.
bool Ch2k8SelectFastVectorPack(unsigned index);
bool Ch2k8SelectFastVectorUnpack(unsigned index);
bool Ch2k8SelectFastVectorStore(unsigned index);
bool Ch2k8SelectFastRamStore(unsigned index);
class Ch2k8HotScope {
public:
  Ch2k8HotScope(unsigned index, uint32_t descriptor, uint8_t *base, bool fast,
                bool unpack = false, bool store = false, bool ram = false,
                const uint64_t *ram_counts = nullptr);
  ~Ch2k8HotScope();

private:
  uint64_t started_ = 0;
  uint32_t units_ = 0;
  unsigned index_ = 0;
  bool fast_ = false;
  bool unpack_ = false;
  bool store_ = false;
  bool ram_ = false;
  bool batch_ = false;
  const uint64_t *ram_counts_ = nullptr;
};
