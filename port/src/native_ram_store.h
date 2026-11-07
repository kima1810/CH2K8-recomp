#pragma once
#include <cstdint>
#ifdef _WIN32
#include <windows.h>
#endif

// [CONFIRMED] Scope is local to one guest call. Only ordinary writable guest RAM
// is eligible; device windows and protected/uncommitted pages retain byte stores.
class Ch2k8RamStoreScope {
  bool enabled_;
  uintptr_t prepared_bias_ = 0;
  uintptr_t begin_ = 0, end_ = 0, blocked_page_ = ~uintptr_t(0);
#ifdef _WIN32
  __declspec(noinline) bool QueryWritable(uint8_t *host, unsigned bytes) {
    const auto address=reinterpret_cast<uintptr_t>(host);
    if ((address & ~uintptr_t(4095)) == blocked_page_) return false;
    MEMORY_BASIC_INFORMATION info{};
    if (VirtualQuery(host,&info,sizeof(info))==sizeof(info) && info.State==MEM_COMMIT &&
        (info.Type==MEM_PRIVATE || info.Type==MEM_MAPPED) &&
        (info.Protect==PAGE_READWRITE || info.Protect==PAGE_WRITECOPY)) {
      begin_=reinterpret_cast<uintptr_t>(info.BaseAddress);end_=begin_+info.RegionSize;
      if(address>=begin_ && address+bytes<=end_) return true;
    }
    blocked_page_=address & ~uintptr_t(4095);
    return false;
  }
#endif
public:
  uint64_t counts[2]{}; // Native instructions, byte-path instructions.
  explicit Ch2k8RamStoreScope(bool enabled) : enabled_(enabled) {}
  bool enabled() const { return enabled_; }
  static bool IsOrdinaryRam(uint32_t ea) {
    return ea < 0x7F000000u || (ea >= 0x80000000u && ea < 0xFFD00000u);
  }
  bool PrepareSpan(uint8_t *base, uint32_t ea, uint32_t bytes,
                   const void *context, size_t context_bytes) {
#if defined(_WIN32) && defined(SIMDE_X86_SSE2_NATIVE)
    const uint64_t end=uint64_t(ea)+bytes;
    if (!enabled_ || (ea&3) || !bytes || end>0x100000000ull ||
        !IsOrdinaryRam(ea) || !IsOrdinaryRam(uint32_t(end-1))) return false;
    // Neither a device hole nor a physical-alias boundary may lie in the span.
    if ((ea<0x7F000000u && end>0x7F000000ull) ||
        (ea<0xE0000000u && end>0xE0000000ull)) return false;
    auto *host=REX_RAW_ADDR(ea);
    const auto address=reinterpret_cast<uintptr_t>(host);
    const auto source=reinterpret_cast<uintptr_t>(context);
    const auto scope=reinterpret_cast<uintptr_t>(this);
    if ((address&3) || !(address+bytes<=source || source+context_bytes<=address) ||
        !(address+bytes<=scope || scope+sizeof(*this)<=address)) return false;
    if (!QueryWritable(host,bytes)) return false;
    prepared_bias_ = address - uintptr_t(ea);
    return true;
#else
    return false;
#endif
  }
#ifdef _WIN32
  __forceinline
#endif
  void StorePrepared(uint8_t *base, uint32_t ea, const PPCVRegister &source) {
    // Contract: codegen proved all offsets/alignment; PrepareSpan validated the
    // entire output range and excluded context/scope aliasing before this call.
#if defined(_WIN32) && defined(SIMDE_X86_SSE2_NATIVE)
    auto *host=REX_RAW_ADDR(ea);
    const unsigned bytes=16-(ea&15);
    if(bytes==16) {
      const auto reversed=simde_mm_shuffle_epi8(
        simde_mm_loadu_si128(reinterpret_cast<const simde__m128i*>(source.u8)),
        simde_mm_set_epi8(0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15));
      *reinterpret_cast<volatile simde__m128i*>(host)=reversed;
    } else if(bytes==8) {
      *reinterpret_cast<volatile uint64_t*>(host)=__builtin_bswap64(source.u64[1]);
    } else {
      for(unsigned offset=0;offset<bytes;offset+=4)
        *reinterpret_cast<volatile uint32_t*>(host+offset)=__builtin_bswap32(source.u32[3-offset/4]);
    }
    ++counts[0];
#endif
  }
  uint8_t* PreparedAddress(uint32_t ea) const {
    return reinterpret_cast<uint8_t*>(prepared_bias_+uintptr_t(ea));
  }
  template<bool Count = true>
#ifdef _WIN32
  __forceinline
#endif
  void StorePreparedDirect(uint8_t *base, uint32_t ea, const PPCVRegister &source) {
    // Contract: codegen proved all offsets/alignment; PrepareSpan validated the
    // entire output range and excluded context/scope aliasing before this call.
#if defined(_WIN32) && defined(SIMDE_X86_SSE2_NATIVE)
    auto *host=PreparedAddress(ea);
    const unsigned bytes=16-(ea&15);
    if(bytes==16) {
      const auto reversed=simde_mm_shuffle_epi8(
        simde_mm_loadu_si128(reinterpret_cast<const simde__m128i*>(source.u8)),
        simde_mm_set_epi8(0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15));
      *reinterpret_cast<volatile simde__m128i*>(host)=reversed;
    } else if(bytes==8) {
      *reinterpret_cast<volatile uint64_t*>(host)=__builtin_bswap64(source.u64[1]);
    } else {
      for(unsigned offset=0;offset<bytes;offset+=4)
        *reinterpret_cast<volatile uint32_t*>(host+offset)=__builtin_bswap32(source.u32[3-offset/4]);
    }
    if constexpr(Count) ++counts[0];
#endif
  }
#ifdef _WIN32
  __forceinline
#endif
  bool TryStore(uint8_t *base, uint32_t ea, const PPCVRegister &source) {
#if defined(_WIN32) && defined(SIMDE_X86_SSE2_NATIVE)
    if (enabled_ && !(ea & 3) && IsOrdinaryRam(ea)) {
      const unsigned bytes = 16 - (ea & 15);
      auto *host = REX_RAW_ADDR(ea);
      const auto address = reinterpret_cast<uintptr_t>(host);
      const auto src = reinterpret_cast<uintptr_t>(&source);
      // Preserve overlapping-source read/write ordering via the original path.
      if (!(address & 3) && (address + bytes <= src || src + 16 <= address)) {
        bool writable = address >= begin_ && address + bytes <= end_;
        if (!writable) [[unlikely]] writable=QueryWritable(host,bytes);
        if (writable) {
          if (bytes == 16) {
            const auto reversed = simde_mm_shuffle_epi8(
                simde_mm_loadu_si128(reinterpret_cast<const simde__m128i *>(source.u8)),
                simde_mm_set_epi8(0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15));
            *reinterpret_cast<volatile simde__m128i *>(host) = reversed;
          } else if (bytes == 8) {
            *reinterpret_cast<volatile uint64_t *>(host) = __builtin_bswap64(source.u64[1]);
          } else {
            for (unsigned offset = 0; offset < bytes; offset += 4)
              *reinterpret_cast<volatile uint32_t *>(host + offset) =
                  __builtin_bswap32(source.u32[3 - offset / 4]);
          }
          ++counts[0];
          return true;
        }
      }
    }
#endif
    ++counts[1];
    return false;
  }
};
