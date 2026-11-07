#include "packed_vector_optimized.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <mutex>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#endif

namespace {
std::atomic<int> batch_mode{1};
thread_local bool selected_batch[3]{};
thread_local uint32_t batch_selection[3]{0x91E10DA5,0x7F4A7C15,0x6E624EB7};
std::atomic<int> mode{0}; // baseline, optimized, interleaved comparison
std::atomic<int> unpack_mode{0};
std::atomic<int> store_mode{0};
std::atomic<int> ram_mode{0};
std::atomic<bool> guarded_store_enabled{true};
std::atomic<bool> profiling{false};
std::mutex output_mutex;
std::FILE *output = nullptr;
uint64_t origin = 0;
constexpr uint32_t addresses[] = {0x84723778, 0x84723CC0, 0x84724930};
struct Bin {
  uint64_t calls = 0, units = 0, nanoseconds = 0;
  uint64_t wide_stores = 0, byte_stores = 0;
};
thread_local Bin bins[3][6];
thread_local uint32_t selection[3]{0x91E10DA5, 0x7F4A7C15, 0x6E624EB7};
thread_local uint32_t unpack_selection[3]{0xA24BAED5, 0x9FB21C65, 0xC13FA9A9};
thread_local uint32_t store_selection[3]{0xB5297A4D, 0x68E31DA4, 0x1B56C4E9};
thread_local uint32_t ram_selection[3]{0x94D049BB,0x369DEA0F,0xF1357AEA};
thread_local uint64_t previous_flush = 0;
uint64_t now_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}
void flush(uint64_t now) {
  std::lock_guard lock(output_mutex);
  if (!output)
    return;
#ifdef _WIN32
  const auto thread = uint64_t(GetCurrentThreadId());
#else
  const auto thread =
      uint64_t(std::hash<std::thread::id>{}(std::this_thread::get_id()));
#endif
  for (unsigned id = 0; id < 3; ++id)
    for (unsigned variant = 0; variant < 6; ++variant) {
      auto &bin = bins[id][variant];
      if (!bin.calls)
        continue;
      std::fprintf(output, "%.3f,%llu,0x%08X,%u,%u,%u,%u,%llu,%llu,%llu,%llu,%llu,%u\n",
                   double(now - origin) / 1000000.0, (unsigned long long)thread,
                   addresses[id], unsigned(variant != 0),
                   unsigned(variant >= 2), unsigned(variant >= 3), unsigned(variant >= 4),
                   (unsigned long long)bin.calls, (unsigned long long)bin.units,
                   (unsigned long long)bin.nanoseconds, (unsigned long long)bin.wide_stores, (unsigned long long)bin.byte_stores, unsigned(variant == 5));
      bin = {};
    }
  std::fflush(output);
  previous_flush = now;
}
} // namespace

void Ch2k8ConfigureHotFunctions(int selected_mode, int selected_unpack,
                                int selected_store, int selected_ram,
                                bool selected_guarded_store, const char *path) {
  mode.store(selected_mode, std::memory_order_release);
  unpack_mode.store(selected_unpack, std::memory_order_release);
  store_mode.store(selected_store, std::memory_order_release);
  ram_mode.store(selected_ram, std::memory_order_release);
  guarded_store_enabled.store(selected_guarded_store, std::memory_order_release);
  if (!path || !*path)
    return;
  std::lock_guard lock(output_mutex);
#ifdef _WIN32
  fopen_s(&output, path, "w");
#else
  output = std::fopen(path, "w");
#endif
  if (!output)
    return;
  std::fputs("elapsed_ms,thread,function,optimized,unpack_optimized,store_"
             "optimized,ram_optimized,calls,work_units,wall_ns,wide_stores,byte_stores,normalization_batch\n",
             output);
  std::fflush(output);
  origin = now_ns();
  profiling.store(true, std::memory_order_release);
}
bool Ch2k8HotProfilingEnabled() {return profiling.load(std::memory_order_acquire);}
void Ch2k8ConfigureGeometryBatch(int selected) {batch_mode.store(selected,std::memory_order_release);}
bool Ch2k8SelectGeometryBatch(unsigned index) {
  const auto mode=batch_mode.load(std::memory_order_acquire);
  bool enabled=mode==1;
  if(mode==2) {auto& state=batch_selection[index];state^=state<<13;state^=state>>17;state^=state<<5;enabled=bool(state&1);}
  // Reordering independent FP operations retains sticky status flags. Preserve
  // the original instruction order when the host has any unmasked FP traps.
  enabled=enabled && (simde_mm_getcsr()&0x1F80)==0x1F80;
  return selected_batch[index]=enabled;
}
void Ch2k8CloseHotLog() {
  profiling.store(false, std::memory_order_release);
  std::lock_guard lock(output_mutex);
  if (output) {
    std::fclose(output);
    output = nullptr;
  }
}
bool Ch2k8SelectFastVectorPack(unsigned index) {
  const auto selected = mode.load(std::memory_order_acquire);
  if (selected != 2)
    return selected == 1;
  // Randomize within the same run so fixed call-order parity cannot assign
  // every expensive descriptor to the same implementation on every frame.
  auto &state = selection[index];
  state ^= state << 13;
  state ^= state >> 17;
  state ^= state << 5;
  return bool(state & 1);
}
bool Ch2k8SelectFastVectorUnpack(unsigned index) {
  const auto selected = unpack_mode.load(std::memory_order_acquire);
  if (selected != 2)
    return selected == 1;
  auto &state = unpack_selection[index];
  state ^= state << 13;
  state ^= state >> 17;
  state ^= state << 5;
  return bool(state & 1);
}
bool Ch2k8SelectFastVectorStore(unsigned index) {
  const auto selected = store_mode.load(std::memory_order_acquire);
  if (selected != 2)
    return selected == 1;
  auto &state = store_selection[index];
  state ^= state << 13;
  state ^= state >> 17;
  state ^= state << 5;
  return bool(state & 1);
}
bool Ch2k8SelectFastRamStore(unsigned index) {
  if (index == 2 && !guarded_store_enabled.load(std::memory_order_acquire)) return false;
  const auto selected=ram_mode.load(std::memory_order_acquire);
  if(selected!=2) return selected==1;
  auto &state=ram_selection[index];
  state^=state<<13;state^=state>>17;state^=state<<5;
  return bool(state&1);
}
Ch2k8HotScope::Ch2k8HotScope(unsigned index, uint32_t descriptor, uint8_t *base,
                             bool fast, bool unpack, bool store, bool ram, const uint64_t *ram_counts)
    : index_(index), fast_(fast), unpack_(unpack), store_(store), ram_(ram), ram_counts_(ram_counts) {
  if (!profiling.load(std::memory_order_acquire))
    return;
  // [CONFIRMED] Descriptor fields used by the original loop-count instructions.
  // First two derive group counts from descriptor+4; third counts outer groups.
  auto pointer = base + descriptor + (descriptor >= 0xE0000000u ? 0x1000u : 0u);
  if (index == 0) {
    units_ = __builtin_bswap16(
                 *reinterpret_cast<volatile uint16_t *>(pointer + 4)) >>
             3;
  } else if (index == 1) {
    units_ = (__builtin_bswap32(
                  *reinterpret_cast<volatile uint32_t *>(pointer + 4)) >>
              3) &
             0x1FFF;
  } else {
    units_ =
        (__builtin_bswap32(*reinterpret_cast<volatile uint32_t *>(pointer)) >>
         1) &
        0x1F;
  }
  batch_ = ram_ && selected_batch[index];
  started_ = now_ns();
}
Ch2k8HotScope::~Ch2k8HotScope() {
  if (!started_)
    return;
  const auto now = now_ns();
  auto &bin = bins[index_][batch_ ? 5 : ram_ ? 4 : store_ ? 3 : unpack_ ? 2 : fast_ ? 1 : 0];
  ++bin.calls;
  bin.units += units_;
  bin.nanoseconds += now - started_;
  if(ram_counts_) {bin.wide_stores+=ram_counts_[0];bin.byte_stores+=ram_counts_[1];}
  if (now - previous_flush >= 1000000000)
    flush(now);
}
