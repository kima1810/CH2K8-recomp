// No game data: validate widened RAM stores, device exclusions and page watches.
#include "ch2k8_pch.h"
#include "vector_store_optimized.h"
#include "linear_address_span.h"
#include <chrono>
#include <cstdio>
#include <cstring>
#include <vector>

uint8_t *watched = nullptr;
unsigned watch_faults = 0;
LONG CALLBACK Watch(EXCEPTION_POINTERS *info) {
  const auto *record = info->ExceptionRecord;
  if (record->ExceptionCode == EXCEPTION_ACCESS_VIOLATION &&
      record->NumberParameters >= 2 && record->ExceptionInformation[0] == 1 &&
      record->ExceptionInformation[1] >= uintptr_t(watched) &&
      record->ExceptionInformation[1] < uintptr_t(watched) + 4096) {
    DWORD previous;
    if (VirtualProtect(watched,4096,PAGE_READWRITE,&previous)) {
      ++watch_faults;
      return EXCEPTION_CONTINUE_EXECUTION;
    }
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

int check() {
  constexpr size_t reserve_size=(1ull<<32)+8192;
  auto *a=static_cast<uint8_t*>(VirtualAlloc(nullptr,reserve_size,MEM_RESERVE,PAGE_NOACCESS));
  auto *b=static_cast<uint8_t*>(VirtualAlloc(nullptr,reserve_size,MEM_RESERVE,PAGE_NOACCESS));
  if(!a || !b) return 2;
  for(uint32_t start : {0u,4u,0xDFFFFFF0u,0xDFFFFFF4u,0xE0000000u,0xFFFFFFF0u}) {
    Ch2k8LinearAddressSpan linear;
    for(uint64_t bytes : {0ull,1ull,16ull,48ull,0x100000000ull}) {
      const uint64_t end=uint64_t(start)+bytes;
      const bool expected=bytes && end<=0x100000000ull && !(start<0xE0000000u && end>0xE0000000ull);
      if(linear.Prepare(b,start,bytes)!=expected)return 22;
      if(expected)for(uint32_t ea : {start,uint32_t(end-1),start&~15u}) {
        auto* base=b;
        if(linear.Address(ea)!=REX_RAW_ADDR(ea))return 23;
      }
    }
  }
  PPCVRegister source{};
  for(unsigned i=0;i<16;++i) source.u8[i]=uint8_t(17*i+3);
  unsigned comparisons=0;
  for(uint32_t page : {0u,0x7EFFF000u,0x7F000000u,0x7FC80000u,0x7FEA0000u,
                       0x7FFFF000u,0x80000000u,0xDFFFF000u,0xE0000000u,
                       0xFFCFF000u,0xFFD00000u,0xFFFFF000u}) {
    const size_t host_offset=size_t(page)+(page>=0xE0000000u?4096:0);
    if(!VirtualAlloc(a+host_offset,4096,MEM_COMMIT,PAGE_READWRITE) ||
       !VirtualAlloc(b+host_offset,4096,MEM_COMMIT,PAGE_READWRITE)) return 3;
    for(unsigned offset=0;offset<4096;++offset) {
      std::memset(a+host_offset,0xA5,4096);std::memset(b+host_offset,0xA5,4096);
      Ch2k8RamStoreScope native(true);
      Ch2k8StoreVectorLeft(a,page+offset,source);
      Ch2k8StoreVectorLeft(b,page+offset,source,&native);
      if(std::memcmp(a+host_offset,b+host_offset,4096)) return 4;
      const bool expected=!(offset&3)&&Ch2k8RamStoreScope::IsOrdinaryRam(page+offset);
      if(native.counts[0]!=unsigned(expected)) return 5;
      if(!(offset&3)) {
        Ch2k8RamStoreScope prepared(true);
        if(prepared.PrepareSpan(b,page+offset,16,&source,sizeof(source))) {
          std::memset(b+host_offset,0xA5,4096);
          auto* base=b;
          if(prepared.PreparedAddress(page+offset)!=REX_RAW_ADDR(page+offset))return 20;
          prepared.StorePreparedDirect(b,page+offset,source);
          if(std::memcmp(a+host_offset,b+host_offset,4096))return 21;
        }
      }
      ++comparisons;
    }
  }
  // Overlapping source/destination must fall back, preserving sequential reads.
  for(unsigned offset=0;offset<32;++offset) {
    for(unsigned i=0;i<64;++i) a[i]=b[i]=uint8_t(i*11);
    Ch2k8RamStoreScope native(true);
    Ch2k8StoreVectorLeft(a,offset,*reinterpret_cast<PPCVRegister*>(a+16));
    Ch2k8StoreVectorLeft(b,offset,*reinterpret_cast<PPCVRegister*>(b+16),&native);
    if(std::memcmp(a,b,64)) return 6;
  }
  // Fresh scopes reject readonly, guard and executable pages without touching them.
  for(DWORD protection : {PAGE_READONLY,PAGE_READWRITE|PAGE_GUARD,PAGE_EXECUTE_READWRITE}) {
    DWORD previous;
    VirtualProtect(b,4096,protection,&previous);
    Ch2k8RamStoreScope native(true);
    if(native.TryStore(b,0,source)) return 7;
    VirtualProtect(b,4096,PAGE_READWRITE,&previous);
  }
  // A page may become write-watched after the region was checked. Like native
  // stvx, the widened store faults on that same page and retries after the watch.
  if(!VirtualAlloc(b+4096,4096,MEM_COMMIT,PAGE_READWRITE)) return 8;
  Ch2k8RamStoreScope cached(true);
  if(!cached.TryStore(b,0,source)) return 9;
  watched=b;auto handler=AddVectoredExceptionHandler(1,Watch);
  DWORD previous;
  VirtualProtect(watched,4096,PAGE_READONLY,&previous);
  if(!cached.TryStore(b,16,source) || watch_faults!=1) return 10;
  RemoveVectoredExceptionHandler(handler);watched=nullptr;
  for(unsigned i=0;i<16;++i) if(b[16+i]!=source.u8[15-i]) return 11;
  // The actual guest arena is mapped RAM rather than private allocations.
  HANDLE section=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,8192,nullptr);
  auto *mapped=static_cast<uint8_t*>(MapViewOfFile(section,FILE_MAP_ALL_ACCESS,0,0,8192));
  if(!mapped) return 12;
  Ch2k8RamStoreScope mapped_scope(true);
  for(unsigned offset : {0u,4u,8u,12u})
    if(!mapped_scope.TryStore(mapped,offset,source)) return 13;
  Ch2k8RamStoreScope prepared(true);
  if(!prepared.PrepareSpan(mapped,0,8192,&source,sizeof(source))) return 14;
  for(unsigned offset=0;offset<8192;offset+=4) {
    prepared.StorePrepared(mapped,offset,source);
    for(unsigned i=0;i<16-(offset&15);++i)
      if(mapped[offset+i]!=source.u8[15-i]) return 15;
  }
  for(unsigned offset : {1u,0x7EFFFFF0u,0xDFFFFFF0u,0xFFFFFFF0u}) {
    Ch2k8RamStoreScope rejected(true);
    if(rejected.PrepareSpan(mapped,offset,64,&source,sizeof(source))) return 16;
  }
  Ch2k8RamStoreScope overlap(true);
  if(overlap.PrepareSpan(mapped,0,16,mapped,16)) return 17;
  Ch2k8RamStoreScope too_large(true);
  if(too_large.PrepareSpan(mapped,0,16384,&source,sizeof(source))) return 18;
  watched=mapped;handler=AddVectoredExceptionHandler(1,Watch);
  VirtualProtect(watched,4096,PAGE_READONLY,&previous);
  prepared.StorePrepared(mapped,0,source);
  if(watch_faults!=2) return 19;
  RemoveVectoredExceptionHandler(handler);watched=nullptr;
  puts("prepared-span bounds,overlap,write-watch passed");
  UnmapViewOfFile(mapped);CloseHandle(section);
  VirtualFree(a,0,MEM_RELEASE);VirtualFree(b,0,MEM_RELEASE);
  printf("validated_offsets,%u\n",comparisons);
  puts("overlaps,permissions,write-watch-retry,mapped-RAM passed");
  return 0;
}

volatile uint64_t checksum=0;
template<bool Native> double measure(unsigned alignment) {
  auto *memory=static_cast<uint8_t*>(VirtualAlloc(nullptr,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
  std::vector<PPCVRegister> source(256);
  for(unsigned i=0;i<256;++i) for(unsigned lane=0;lane<16;++lane) source[i].u8[lane]=uint8_t(i+17*lane);
  const auto started=std::chrono::steady_clock::now();
  for(unsigned job=0;job<1024;++job) {
    Ch2k8RamStoreScope scope(Native);
    for(unsigned i=0;i<4096;++i)
      Ch2k8StoreVectorLeft(memory,((i*16)&32767)+alignment,source[i&255],&scope);
    checksum=checksum+scope.counts[0]+scope.counts[1];
  }
  const auto elapsed=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-started).count();
  VirtualFree(memory,0,MEM_RELEASE);
  return elapsed/(1024.0*4096);
}
int main() {
  const int result=check();if(result) {printf("Mismatch %d\n",result);return result;}
  puts("alignment,trial,byte_ns,native_ns");
  for(unsigned alignment : {0u,4u,8u,12u}) for(unsigned trial=0;trial<7;++trial) {
    double a,b;
    if(trial&1) {b=measure<true>(alignment);a=measure<false>(alignment);}
    else {a=measure<false>(alignment);b=measure<true>(alignment);}
    printf("%u,%u,%.6f,%.6f\n",alignment,trial,a,b);
  }
}
