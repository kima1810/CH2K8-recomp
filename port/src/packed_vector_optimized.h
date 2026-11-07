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
  const uint64_t wz = uint64_t(simde_mm_cvtsi128_si64(clamped));
  const uint64_t yx =
      uint64_t(simde_mm_cvtsi128_si64(simde_mm_srli_si128(clamped, 8)));
  scratch.u64[0] = ((yx >> 32) & 0xFFFFF) | ((yx & 0xFFFFF) << 20) |
                   (((wz >> 32) & 0xFFFFF) << 40) | ((wz & 0xF) << 60);
  scratch.u32[2] = 0x4040000F;
  temporary.u32 = uint32_t(wz);
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
