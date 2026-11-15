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
// The loose scene path can restore native pixel formats that the host
// texture replacement catalog cannot upload.
struct SceneRawTexture {
  unsigned width, height, pitch, bytes, endian, faces, packed_x, packed_y;
  uint64_t start, length, stride;
  bool tiled;
  Bytes header;
};

inline SceneRawTexture describe_scene_raw(const Bytes &cpu, const Bytes &gpu) {
  auto a = be(cpu, 0x94), b = be(cpu, 0x98), size = be(cpu, 0x9c),
       dim = be(cpu, 0xa8), format = b & 63, kind = (dim >> 9) & 3;
  auto code = be(cpu, 8);
  bool explicit_header = !format;
  static const std::map<unsigned, unsigned> sizes{{2, 1}, {4, 2}, {6, 4},
                                                  {10, 2}, {31, 4}, {32, 8}};
  if (explicit_header)
    format = code & 63;
  require(sizes.contains(format), "Unsupported Xbox raw texture format");
  require(explicit_header || ((a & 3) == 2 && !(b & 1024) &&
              ((kind == 1 && !(size >> 26)) ||
               (kind == 3 && (size >> 26) == 5))),
          "Unsupported Xbox raw texture dimension");
  unsigned w = (size & 8191) + 1, h = ((size >> 13) & 8191) + 1,
           pitch = ((a >> 22) & 511) * 32, bytes = sizes.at(format),
           faces = kind == 3 ? 6 : 1, endian = (b >> 6) & 3;
  bool tiled = bool(a >> 31);
  auto swizzle = (be(cpu, 0xa0) >> 1) & 4095;
  if (explicit_header) {
    auto extents = be(cpu, 0x60);
    w = extents >> 16;
    h = extents & 65535;
    faces = be(cpu, 0x64) & 65535;
    tiled = bool(code & 256);
    endian = (code >> 6) & 3;
    swizzle = (code >> 18) & 4095;
    pitch = unsigned(tiled ? align(w, 32) : align(w * bytes, 256) / bytes);
  }
  require(w && h && w <= 8192 && h <= 8192 && pitch >= w &&
              (faces == 1 || (faces == 6 && w == h)),
          "Invalid Xbox raw texture size");
  auto offset = be(cpu, 0x6c);
  uint64_t length = be(cpu, 0x70);
  require(offset && uint64_t(offset - 1) <= gpu.size(),
          "Missing Xbox raw texture pixels");
  if (explicit_header && !length)
    length = gpu.size() - (offset - 1);
  require(length, "Missing Xbox raw texture pixels");
  bounds(gpu, offset - 1, length);
  bool packed = !explicit_header && (dim & 2048) && std::min(w, h) <= 16;
  bool packed_left = std::bit_width(w - 1) <= std::bit_width(h - 1);
  bool dx10 = format == 10 || format == 31 || format == 32;
  Bytes header(dx10 ? 148 : 128);
  std::memcpy(header.data(), "DDS ", 4);
  for (auto [pos, value] :
       std::initializer_list<std::pair<unsigned, unsigned>>{
           {4, 124}, {8, 0x100f}, {12, h}, {16, w}, {20, w * bytes}, {28, 1},
           {76, 32}, {108, faces == 6 ? 0x1008u : 0x1000u},
           {112, faces == 6 ? 0xfe00u : 0u}})
    put(header, pos, value, 4, true);
  std::memcpy(header.data() + 32, "XRAW", 4);
  put(header, 36, format, 4, true);
  put(header, 40, swizzle, 4, true);
  if (dx10) {
    put(header, 80, 4, 4, true);
    std::memcpy(header.data() + 84, "DX10", 4);
    put(header, 128, format == 10 ? 49 : format == 31 ? 34 : 10, 4, true);
    put(header, 132, 3, 4, true);
    put(header, 136, faces == 6 ? 4 : 0, 4, true);
    put(header, 140, 1, 4, true);
  } else {
    put(header, 80, format == 2 ? 0x20000 : format == 4 ? 0x40 : 0x41, 4, true);
    put(header, 88, bytes * 8, 4, true);
    std::vector<uint32_t> masks = format == 2 ? std::vector<uint32_t>{255}
        : format == 4 ? std::vector<uint32_t>{31, 2016, 63488}
                      : std::vector<uint32_t>{255, 65280, 16711680, 4278190080u};
    std::set<unsigned> channels;
    for (unsigned j = 0; j < masks.size(); ++j)
      channels.insert((swizzle >> (3 * j)) & 7);
    bool reorder = format != 2 && channels.size() == masks.size() &&
                   *channels.rbegin() < masks.size();
    for (unsigned j = 0; j < masks.size(); ++j)
      put(header, 92 + 4 * j, masks[reorder ? (swizzle >> (3 * j)) & 7 : j], 4, true);
  }
  return {w, h, pitch, bytes, endian, faces, packed && packed_left ? 16u : 0u,
          packed && !packed_left ? 16u : 0u, offset - 1, length,
          faces == 6 ? align(pitch * align(h, 32) * bytes, 4096) : 0,
          tiled, std::move(header)};
}

inline bool scene_is_raw(const Bytes &cpu) {
  auto format = be(cpu, 0x98) & 63;
  switch (format ? format : be(cpu, 8) & 63) {
    case 2: case 4: case 6: case 10: case 31: case 32:
      return true;
    default:
      return false;
  }
}

template <typename Copy>
inline void scene_raw_bytes(const SceneRawTexture &t, Copy copy) {
  constexpr unsigned swaps[] = {0, 1, 3, 2};
  auto cursor = t.header.size();
  for (unsigned face = 0; face < t.faces; ++face)
    for (unsigned y = 0; y < t.height; ++y)
      for (unsigned x = 0; x < t.width; ++x) {
        auto px = x + t.packed_x, py = y + t.packed_y;
        auto offset = face * t.stride +
                      (t.tiled ? tiled_offset(px, py, t.pitch, std::countr_zero(t.bytes))
                               : (uint64_t(py) * t.pitch + px) * t.bytes);
        for (unsigned j = 0; j < t.bytes; ++j) {
          auto address = (offset + j) ^ swaps[t.endian];
          require(address < t.length, "Xbox raw texel exceeds payload");
          copy(cursor++, t.start + address);
        }
      }
}

inline Bytes export_raw_dds(const Bytes &cpu, const Bytes &gpu) {
  auto t = describe_scene_raw(cpu, gpu);
  auto dds = t.header;
  dds.resize(dds.size() + uint64_t(t.width) * t.height * t.bytes * t.faces);
  scene_raw_bytes(t, [&](auto dest, auto source) { dds[dest] = gpu[source]; });
  return dds;
}

inline void replace_raw_dds(const Bytes &cpu, const Bytes &dds, Bytes &gpu) {
  auto t = describe_scene_raw(cpu, gpu);
  require(dds.size() == t.header.size() +
              uint64_t(t.width) * t.height * t.bytes * t.faces &&
              std::memcmp(dds.data(), "DDS ", 4) == 0 && le(dds, 4) == 124 &&
              le(dds, 12) == t.height && le(dds, 16) == t.width &&
              le(dds, 24) <= 1 && le(dds, 28) <= 1 &&
              std::equal(dds.begin() + 76, dds.begin() + 108, t.header.begin() + 76) &&
              le(dds, 112) == le(t.header, 112) &&
              std::equal(dds.begin() + 128, dds.begin() + t.header.size(),
                         t.header.begin() + 128),
          "Raw scene DDS must retain dimensions, format and faces");
  scene_raw_bytes(t, [&](auto source, auto dest) { gpu[dest] = dds[source]; });
}

inline uint64_t scene_texture_table(const Bytes &cpu, uint64_t count) {
  require(count <= 4096, "Scene texture table exceeds limit");
  auto table = 0x24ull + be(cpu, 0x24) - 1;
  bounds(cpu, table, count * 224);
  return table;
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
