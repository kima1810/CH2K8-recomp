#pragma once
#include <rex/cvar.h>
#include <rex/graphics/registers.h>
#include <rex/logging.h>
#include <rex/graphics/native_constant_compare.h>
#include <chrono>

REXCVAR_DECLARE(bool, ch2k8_native_constants);
REXCVAR_DECLARE(bool, ch2k8_gpu_stats);
REXCVAR_DECLARE(bool, ch2k8_native_packets);
REXCVAR_DECLARE(bool, ch2k8_packet_compare);

namespace rex::graphics::ch2k8 {
struct ConstantStats {
  uint64_t single_requests = 0, range_requests = 0, requested_words = 0;
  uint64_t skipped_requests = 0, skipped_words = 0;
  uint64_t float_uploads = 0, system_uploads = 0, bool_uploads = 0;
  uint64_t origin_ms = 0, previous_ms = 0;
  uint64_t bulk_packets = 0, packet_words = 0;
  uint64_t fast_packets = 0, slow_packets = 0, fast_words = 0, slow_words = 0;
  uint64_t fast_ns = 0, slow_ns = 0;
};
inline thread_local ConstantStats constant_stats;
inline bool ChooseNativePacket() {
  if (!REXCVAR_GET(ch2k8_native_packets)) return false;
  if (!REXCVAR_GET(ch2k8_packet_compare)) return true;
  static thread_local uint32_t random=0xC13FA9A9;
  random^=random<<13; random^=random>>17; random^=random<<5;
  return bool(random&1);
}
class PacketScope {
  bool fast_; uint32_t words_; uint64_t started_=0;
  static uint64_t Now() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
  }
public:
  PacketScope(bool eligible, bool fast, uint32_t words):fast_(fast),words_(words) {
    if (eligible && REXCVAR_GET(ch2k8_gpu_stats)) started_=Now();
  }
  ~PacketScope() {
    if (!started_) return;
    auto &s=constant_stats;
    if (fast_) {++s.fast_packets;s.fast_words+=words_;s.fast_ns+=Now()-started_;}
    else {++s.slow_packets;s.slow_words+=words_;s.slow_ns+=Now()-started_;}
  }
};
inline bool IsConstantRange(uint32_t start, uint32_t count) {
  return Ch2k8RangeWithin(start, count, XE_GPU_REG_SHADER_CONSTANT_000_X,
                          XE_GPU_REG_SHADER_CONSTANT_511_W) ||
         Ch2k8RangeWithin(start, count, XE_GPU_REG_SHADER_CONSTANT_BOOL_000_031,
                          XE_GPU_REG_SHADER_CONSTANT_LOOP_31);
}
inline bool SkipConstantWrite(const uint32_t *registers, uint32_t index, uint32_t value) {
  if (!IsConstantRange(index, 1)) return false;
  const bool stats = REXCVAR_GET(ch2k8_gpu_stats);
  if (stats) { ++constant_stats.single_requests; ++constant_stats.requested_words; }
  if (!REXCVAR_GET(ch2k8_native_constants) || registers[index] != value) return false;
  if (stats) { ++constant_stats.skipped_requests; ++constant_stats.skipped_words; }
  return true;
}
inline bool SkipConstantRange(const uint32_t *registers, uint32_t start,
                               const uint32_t *guest, uint32_t count) {
  if (!IsConstantRange(start, count)) return false;
  const bool stats = REXCVAR_GET(ch2k8_gpu_stats);
  if (stats) { ++constant_stats.range_requests; constant_stats.requested_words += count; }
  if (!REXCVAR_GET(ch2k8_native_constants) ||
      !Ch2k8ConstantWordsEqual(registers + start, guest, count)) return false;
  if (stats) { ++constant_stats.skipped_requests; constant_stats.skipped_words += count; }
  return true;
}
enum class Upload { Float, System, Bool };
inline void RecordBulkPacket(uint32_t words) {
  if (!REXCVAR_GET(ch2k8_gpu_stats)) return;
  ++constant_stats.bulk_packets; constant_stats.packet_words += words;
}
inline void RecordConstantUpload(Upload kind) {
  if (!REXCVAR_GET(ch2k8_gpu_stats)) return;
  if (kind == Upload::Float) ++constant_stats.float_uploads;
  else if (kind == Upload::System) ++constant_stats.system_uploads;
  else ++constant_stats.bool_uploads;
}
inline void FlushConstantStats(const char *backend) {
  if (!REXCVAR_GET(ch2k8_gpu_stats)) return;
  const uint64_t now = std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
  auto &s = constant_stats;
  if (!s.origin_ms) { s.origin_ms = now; s.previous_ms = now; }
  if (now - s.previous_ms < 1000) return;
  REXLOG_INFO("CH2K8_GPU_CONSTANTS backend={} elapsed_ms={} native={} single={} ranges={} words={} skipped={} skipped_words={} float_uploads={} system_uploads={} bool_uploads={} bulk_packets={} packet_words={} fast_packets={} slow_packets={} fast_words={} slow_words={} fast_ns={} slow_ns={}",
      backend, now-s.origin_ms, REXCVAR_GET(ch2k8_native_constants), s.single_requests,
      s.range_requests, s.requested_words, s.skipped_requests, s.skipped_words,
      s.float_uploads, s.system_uploads, s.bool_uploads, s.bulk_packets, s.packet_words,
      s.fast_packets,s.slow_packets,s.fast_words,s.slow_words,s.fast_ns,s.slow_ns);
  const auto origin = s.origin_ms;
  s = {}; s.origin_ms = origin; s.previous_ms = now;
}
} // namespace rex::graphics::ch2k8
