#pragma once
#include "../../port/third_party/miniz/miniz.h"
#include "common.h"
extern "C" int ch2k8_h7a(const uint8_t *, size_t, uint8_t *, size_t);
inline Bytes decode(Bytes b, uint64_t limit = 128ull << 20,
                    std::optional<uint64_t> logical = {}) {
  if (b.size() >= 4 && (be(b, 0) == 0x0e4837c3 || be(b, 0) == 0x5a4c4942)) {
    auto magic = be(b, 0), size = be(b, 4);
    require(size <= limit && be(b, 8) == b.size(),
            "Invalid compressed component size");
    if (logical)
      require(size == *logical, "Decoded block size mismatch");
    Bytes out(size);
    if (magic == 0x0e4837c3)
      require(ch2k8_h7a(b.data(), b.size(), out.data(), out.size()),
              "Invalid or truncated H7A component");
    else {
      bounds(b, 0, 16);
      auto n = tinfl_decompress_mem_to_mem(out.data(), out.size(),
                                           b.data() + 16, b.size() - 16,
                                           TINFL_FLAG_PARSE_ZLIB_HEADER);
      require(n == size, "Invalid ZLIB component payload");
    }
    return out;
  }
  require(!logical || b.size() == *logical, "Decoded block size mismatch");
  return b;
}
struct Texture {
  unsigned width, height, pitch, format, endian, mips;
  uint64_t start, length;
  bool tiled;
};
inline unsigned bpp(unsigned f) {
  require(f == 18 || f == 19 || f == 20 || f == 49 || f == 59,
          "Unsupported Xbox BC texture format");
  return f == 18 || f == 59 ? 8 : 16;
}
inline std::string fourcc(unsigned f) {
  switch (f) {
  case 18:
    return "DXT1";
  case 19:
    return "DXT3";
  case 20:
    return "DXT5";
  case 49:
    return "ATI2";
  case 59:
    return "ATI1";
  }
  throw std::runtime_error("Unsupported BC format");
}
inline Texture describe(const Bytes &cpu, const Bytes *gpu = nullptr) {
  require(cpu.size() >= 0xac, "Short Xbox TXTR descriptor");
  auto a = be(cpu, 0x94), b = be(cpu, 0x98), size = be(cpu, 0x9c),
       lod = be(cpu, 0xa4), dim = be(cpu, 0xa8), format = b & 63;
  bpp(format);
  require((a & 3) == 2 && ((dim >> 9) & 3) == 1 && !(b & (1 << 10)) &&
              !(size >> 26),
          "Unsupported Xbox texture format/dimension");
  unsigned w = (size & 8191) + 1, h = ((size >> 13) & 8191) + 1,
           pitch = ((a >> 22) & 511) * 32;
  require(!(w % 4) && !(h % 4), "Non-block-aligned BC texture");
  int64_t start = gpu ? int64_t(be(cpu, 0x6c)) - 1
                      : 0x6c + int64_t(int32_t(be(cpu, 0x6c))) - 1;
  auto length = be(cpu, 0x70);
  require(!(dim & 0x800) || std::min(w, h) > 16,
          "Base texture level is in a packed mip tail");
  require(start >= 0 && (gpu || start >= 0xac) &&
              uint64_t(start) <= ((gpu ? *gpu : cpu).size()) &&
              length <= ((gpu ? *gpu : cpu).size()) - uint64_t(start) &&
              pitch >= w,
          "Unsupported split or out-of-bounds Xbox texture payload");
  return {w,
          h,
          pitch,
          format,
          (b >> 6) & 3,
          ((lod >> 6) & 15) + 1,
          uint64_t(start),
          length,
          bool(a >> 31)};
}
inline uint64_t tiled_offset(uint64_t x, uint64_t y, uint64_t pitch,
                             unsigned log) {
  pitch = align(pitch, 32);
  auto macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (log + 7),
       micro = ((x & 7) + ((y & 14) << 2)) << log;
  auto off = macro + ((micro & ~15ull) << 1) + (micro & 15) + ((y & 1) << 4);
  return ((off & ~511ull) << 3) + ((y & 16) << 7) + ((off & 448) << 2) +
         (((((y & 8) >> 2) + (x >> 3)) & 3) << 6) + (off & 63);
}
inline Bytes export_dds(const Bytes &cpu, const Bytes *gpu = nullptr) {
  auto t = describe(cpu, gpu);
  const auto &src = gpu ? *gpu : cpu;
  unsigned bytes = bpp(t.format), w = t.width / 4, h = t.height / 4;
  Bytes d(128 + uint64_t(w) * h * bytes);
  std::memcpy(d.data(), "DDS ", 4);
  for (auto [o, v] :
       std::vector<std::pair<unsigned, uint32_t>>{{4, 124},
                                                  {8, 0x81007},
                                                  {12, t.height},
                                                  {16, t.width},
                                                  {20, w * h * bytes},
                                                  {28, 1},
                                                  {76, 32},
                                                  {80, 4},
                                                  {108, 0x1000}})
    put(d, o, v, 4, true);
  std::memcpy(d.data() + 84, fourcc(t.format).data(), 4);
  for (unsigned y = 0; y < h; ++y)
    for (unsigned x = 0; x < w; ++x) {
      uint64_t off = t.tiled
                         ? tiled_offset(x, y, t.pitch / 4, bytes == 8 ? 3 : 4)
                         : (uint64_t(y) * (t.pitch / 4) + x) * bytes;
      require(off + bytes <= t.length, "Texture address exceeds payload");
      for (unsigned k = 0; k < bytes; ++k) {
        unsigned j = t.endian == 1   ? (k ^ 1)
                     : t.endian == 2 ? (k ^ 3)
                     : t.endian == 3 ? (k ^ 2)
                                     : k;
        d[128 + (uint64_t(y) * w + x) * bytes + k] = src[t.start + off + j];
      }
    }
  return d;
}
inline J tex_json(const Texture &t) {
  return J{{"width", t.width},   {"height", t.height}, {"pitch", t.pitch},
           {"format", t.format}, {"endian", t.endian}, {"mips", t.mips},
           {"start", t.start},   {"length", t.length}, {"tiled", t.tiled}};
}
inline void validate_dds(const Bytes &d, unsigned ow, unsigned oh,
                         unsigned format) {
  require(d.size() >= 128 && std::memcmp(d.data(), "DDS ", 4) == 0 &&
              le(d, 4) == 124,
          "Invalid DDS header");
  auto h = le(d, 12), w = le(d, 16), depth = le(d, 24),
       mips = std::max(1u, le(d, 28));
  require(w >= 1 && h >= 1 && w <= 8192 && h <= 8192 && !(w % 4) && !(h % 4) &&
              depth <= 1 && !le(d, 112) && le(d, 76) == 32 && le(d, 80) == 4 &&
              std::string(d.begin() + 84, d.begin() + 88) == fourcc(format),
          "DDS must retain the original BC format and be a single 2D texture");
  require(ow && oh && uint64_t(w) * oh == uint64_t(h) * ow && w >= ow &&
              w % ow == 0 && std::has_single_bit(w / ow),
          "DDS dimensions must preserve aspect ratio and power-of-two upscale");
  require(mips <= std::bit_width(std::max(w, h)), "Too many DDS mip levels");
  uint64_t expected = 128;
  for (unsigned i = 0; i < mips; ++i)
    expected += uint64_t((std::max(1u, w >> i) + 3) / 4) *
                ((std::max(1u, h >> i) + 3) / 4) * bpp(format);
  require(d.size() == expected, "DDS mip payload length mismatch");
}
inline J wave_info(const Bytes &w) {
  require(w.size() >= 12 && !std::memcmp(w.data(), "RIFF", 4) &&
              !std::memcmp(w.data() + 8, "WAVE", 4),
          "Invalid PCM WAV header");
  J out;
  uint64_t size = 0;
  bool found = false;
  for (size_t p = 12; p + 8 <= w.size();) {
    auto n = le(w, p + 4);
    bounds(w, p + 8, n);
    auto name = std::string(w.begin() + p, w.begin() + p + 4);
    if (name == "fmt ") {
      require(n >= 16, "Invalid WAV format");
      auto fmt = le16(w, p + 8);
      if (fmt == 65534)
        require(n >= 40 && le(w, p + 32) == 1, "WAV must use PCM16");
      else
        require(fmt == 1, "WAV must use PCM16");
      require(le16(w, p + 22) == 16, "WAV must use PCM16");
      out = {{"channels", le16(w, p + 10)}, {"rate", le(w, p + 12)}};
    }
    if (name == "data") {
      size = n;
      found = true;
    }
    p += 8 + n + (n & 1);
  }
  require(found && !out.empty() && num(out["channels"]) > 0 &&
              size % (num(out["channels"]) * 2) == 0,
          "Invalid PCM WAV data");
  out["samples"] = size / (num(out["channels"]) * 2);
  return out;
}
