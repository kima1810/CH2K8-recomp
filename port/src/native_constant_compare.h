#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <simde/x86/ssse3.h>

// [CONFIRMED] Compare guest big-endian words with the host register snapshot.
// Integer bits preserve NaN payloads and distinguish positive/negative zero.
inline bool Ch2k8ConstantWordsEqual(const uint32_t *host, const uint32_t *guest,
                                    size_t words) {
  size_t i = 0;
  const auto mask = simde_mm_set_epi8(12, 13, 14, 15, 8, 9, 10, 11,
                                     4, 5, 6, 7, 0, 1, 2, 3);
  for (; words - i >= 4; i += 4) {
    const auto expected = simde_mm_shuffle_epi8(
        simde_mm_loadu_si128(reinterpret_cast<const simde__m128i *>(guest + i)), mask);
    const auto current = simde_mm_loadu_si128(reinterpret_cast<const simde__m128i *>(host + i));
    if (simde_mm_movemask_epi8(simde_mm_cmpeq_epi32(expected, current)) != 0xFFFF)
      return false;
  }
  for (; i < words; ++i) {
    uint32_t value;
    std::memcpy(&value, reinterpret_cast<const uint8_t *>(guest) + i * 4, 4);
    if (host[i] != __builtin_bswap32(value)) return false;
  }
  return true;
}

inline bool Ch2k8RangeWithin(uint32_t start, uint32_t count, uint32_t first,
                             uint32_t last) {
  return count && start >= first && start <= last && count <= last - start + 1;
}

// The caller proves [first_word, first_word+words) is inside 512 float vectors.
inline void Ch2k8ChangedConstantVectors(const uint32_t *host, const uint32_t *guest,
                                        uint32_t first_word, uint32_t words,
                                        uint64_t (&changed)[8]) {
  uint32_t i=0;
  const auto check_word=[&](uint32_t index) {
    uint32_t value;
    std::memcpy(&value, reinterpret_cast<const uint8_t *>(guest) + index * 4, 4);
    if (host[index] != __builtin_bswap32(value)) {
      const uint32_t vector = (first_word + index) >> 2;
      changed[vector >> 6] |= uint64_t(1) << (vector & 63);
    }
  };
  // Align to a shader float4, not to a host pointer. Never load beyond the
  // supplied packet; partial vectors at either end retain exact word checks.
  for (;i<words && ((first_word+i)&3);++i) check_word(i);
  const auto mask=simde_mm_set_epi8(12,13,14,15,8,9,10,11,4,5,6,7,0,1,2,3);
  for (;words-i>=4;i+=4) {
    const auto expected=simde_mm_shuffle_epi8(
        simde_mm_loadu_si128(reinterpret_cast<const simde__m128i*>(guest+i)),mask);
    const auto current=simde_mm_loadu_si128(reinterpret_cast<const simde__m128i*>(host+i));
    if(simde_mm_movemask_epi8(simde_mm_cmpeq_epi32(expected,current))!=0xFFFF) {
      const uint32_t vector=(first_word+i)>>2;
      changed[vector>>6]|=uint64_t(1)<<(vector&63);
    }
  }
  for (;i<words;++i) check_word(i);
}

inline bool Ch2k8ChangedConstantsUsed(const uint64_t *usage, const uint64_t *changed,
                                      uint32_t first, uint32_t last) {
  if(first>last)return false;
  const uint32_t first_block=first>>6,last_block=last>>6;
  for(uint32_t block=first_block;block<=last_block;++block) {
    uint64_t mask=~uint64_t(0);
    if(block==first_block)mask&=~uint64_t(0)<<(first&63);
    if(block==last_block)mask&=~uint64_t(0)>>(63-(last&63));
    if(usage[block]&changed[block]&mask)return true;
  }
  return false;
}
