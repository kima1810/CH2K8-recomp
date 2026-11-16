#pragma once
#include "codec.h"

inline Bytes inline_texture_descriptor(const Bytes &component) {
  auto header = sub(component, 0, 224);
  int64_t offset = 0x6c + int64_t(int32_t(be(header, 0x6c))) - 1;
  require(offset >= 224 && uint64_t(offset) < component.size(),
          "Invalid inline Xbox texture payload pointer");
  put(header, 0x6c, offset + 1);
  return header;
}

struct IndexedTexture {
  unsigned width, height;
  uint64_t palette, mip_end;
  Bytes header;
};

inline bool is_indexed_texture(const Bytes &cpu) {
  return cpu.size() == 224 && be(cpu, 8) == 0x24820002 &&
         (be(cpu, 0x98) & 63) == 0 && be(cpu, 0x6c) == 1;
}

inline IndexedTexture describe_indexed_texture(const Bytes &cpu,
                                               const Bytes &gpu) {
  auto dimensions = be(cpu, 0x60);
  unsigned w = dimensions >> 16, h = dimensions & 65535;
  auto pointer = be(cpu, 0x68);
  require(std::has_single_bit(w) && std::has_single_bit(h) &&
              w <= 8192 && h <= 8192 && pointer,
          "Invalid Xbox indexed texture dimensions/palette");
  uint64_t end = uint64_t(w) * h;
  for (unsigned x = w, y = h; x > 1 || y > 1;) {
    x = std::max(1u, x / 2);
    y = std::max(1u, y / 2);
    end += uint64_t(x) * y;
  }
  uint64_t palette = pointer - 1;
  require(align(end, 16) == palette && palette + 1024 == gpu.size(),
          "Xbox indexed mip or palette extent differs");
  Bytes header(128);
  std::memcpy(header.data(), "DDS ", 4);
  std::memcpy(header.data() + 32, "XIDX", 4);
  for (auto [pos, value] :
       std::initializer_list<std::pair<unsigned, unsigned>>{
           {4, 124}, {8, 0x100f}, {12, h}, {16, w}, {20, w * 4}, {28, 1},
           {76, 32}, {80, 0x41}, {88, 32}, {92, 255}, {96, 65280},
           {100, 16711680}, {104, 4278190080u}, {108, 0x1000}})
    put(header, pos, value, 4, true);
  return {w, h, palette, end, std::move(header)};
}

inline uint32_t indexed_color(const IndexedTexture &t, const Bytes &gpu,
                              unsigned index) {
  auto at = t.palette + index * 4;
  return uint32_t(gpu[at]) << 24 | uint32_t(gpu[at + 3]) << 16 |
         uint32_t(gpu[at + 2]) << 8 | gpu[at + 1];
}

inline Bytes export_indexed_texture(const Bytes &cpu, const Bytes &gpu) {
  auto t = describe_indexed_texture(cpu, gpu);
  auto result = t.header;
  auto count = uint64_t(t.width) * t.height;
  result.resize(128 + count * 4);
  for (uint64_t i = 0; i < count; ++i)
    put(result, 128 + i * 4, indexed_color(t, gpu, gpu[i]), 4, true);
  return result;
}

inline void replace_indexed_texture(const Bytes &cpu, const Bytes &dds,
                                    Bytes &gpu) {
  auto t = describe_indexed_texture(cpu, gpu);
  auto count = uint64_t(t.width) * t.height;
  require(dds.size() == 128 + count * 4 &&
              std::memcmp(dds.data(), "DDS ", 4) == 0 && le(dds, 4) == 124 &&
              le(dds, 12) == t.height && le(dds, 16) == t.width &&
              le(dds, 24) <= 1 && le(dds, 28) <= 1 && le(dds, 112) == 0 &&
              std::equal(dds.begin() + 76, dds.begin() + 108, t.header.begin() + 76),
          "Indexed DDS must retain dimensions and RGBA8 base-level layout");
  std::array<uint32_t, 256> colors{};
  std::array<bool, 256> used{};
  std::map<uint32_t, uint8_t> entries;
  for (unsigned i = 0; i < colors.size(); ++i)
    colors[i] = indexed_color(t, gpu, i);
  for (auto i = count; i < t.mip_end; ++i)
    used[gpu[i]] = true;
  for (uint64_t i = 0; i < count; ++i) {
    auto desired = le(dds, 128 + i * 4);
    auto index = gpu[i];
    if (desired == colors[index])
      used[index] = true;
  }
  auto reserve = [&](uint32_t desired) {
    if (auto it = entries.find(desired); it != entries.end())
      return it->second;
    auto original = std::find(colors.begin(), colors.end(), desired);
    auto pos = original == colors.end()
                 ? std::find(used.begin(), used.end(), false) - used.begin()
                 : original - colors.begin();
    require(pos < 256, "Indexed DDS exceeds palette capacity with existing mips");
    auto at = t.palette + pos * 4;
    gpu[at] = uint8_t(desired >> 24);
    gpu[at + 1] = uint8_t(desired);
    gpu[at + 2] = uint8_t(desired >> 8);
    gpu[at + 3] = uint8_t(desired >> 16);
    colors[pos] = desired;
    used[pos] = true;
    return entries.emplace(desired, uint8_t(pos)).first->second;
  };
  // Reserve any surviving source colors before consuming spare slots.
  for (uint64_t i = 0; i < count; ++i) {
    auto desired = le(dds, 128 + i * 4);
    if (std::find(colors.begin(), colors.end(), desired) != colors.end())
      reserve(desired);
  }
  for (uint64_t i = 0; i < count; ++i) {
    auto desired = le(dds, 128 + i * 4);
    if (indexed_color(t, gpu, gpu[i]) != desired)
      gpu[i] = reserve(desired);
  }
}

struct SceneBlockTexture {
  unsigned w, h, pitch, bytes, endian, faces, packed_x, packed_y;
  uint64_t start, length, face_stride;
  bool tiled;
  Bytes header;
};

inline SceneBlockTexture describe_scene_blocks(const Bytes &cpu, const Bytes &gpu) {
  auto a = be(cpu, 0x94), b = be(cpu, 0x98), size = be(cpu, 0x9c),
       dim = be(cpu, 0xa8), format = b & 63, kind = (dim >> 9) & 3;
  require((a & 3) == 2 && !(b & 1024) &&
              ((kind == 1 && !(size >> 26)) ||
               (kind == 3 && (size >> 26) == 5)),
          "Unsupported Xbox block texture dimension");
  unsigned width = (size & 8191) + 1, height = ((size >> 13) & 8191) + 1,
           pitch = ((a >> 22) & 511) * 8, faces = kind == 3 ? 6 : 1,
           w = (width + 3) / 4, h = (height + 3) / 4;
  require(pitch >= w && (faces == 1 || width == height),
          "Invalid Xbox block texture size");
  auto code = format == 60 ? "CTX1" : fourcc(format);
  unsigned bytes = format == 60 ? 8 : bpp(format);
  auto pointer = be(cpu, 0x6c), length = be(cpu, 0x70);
  require(pointer && length, "Missing Xbox block texture pixels");
  bounds(gpu, pointer - 1, length);
  bool packed = (dim & 2048) && std::min(width, height) <= 16;
  bool left = std::bit_width(width - 1) <= std::bit_width(height - 1);
  // Cube faces with packed tails require independent face-stride evidence.
  require(faces == 1 || !packed, "Unsupported Xbox packed cube layout");
  Bytes header(128);
  std::memcpy(header.data(), "DDS ", 4);
  std::memcpy(header.data() + 84, code.data(), 4);
  if (packed)
    std::memcpy(header.data() + 32, "XPAK", 4);
  for (auto [pos, value] :
       std::initializer_list<std::pair<unsigned, unsigned>>{
           {4, 124}, {8, 0x81007}, {12, height}, {16, width},
           {20, w * h * bytes}, {28, 1}, {76, 32}, {80, 4},
           {108, faces == 6 ? 0x1008u : 0x1000u},
           {112, faces == 6 ? 0xfe00u : 0u}})
    put(header, pos, value, 4, true);
  return {w, h, pitch, bytes, (b >> 6) & 3, faces,
          packed && left ? 4u : 0u, packed && !left ? 4u : 0u,
          pointer - 1, length, faces == 6 ? align(align(pitch, 32) * align(h, 32) * bytes, 4096) : 0,
          bool(a >> 31), std::move(header)};
}

template <typename Copy>
inline void scene_block_bytes(const SceneBlockTexture &t, Copy copy) {
  constexpr unsigned swap[] = {0, 1, 3, 2};
  uint64_t cursor = 128;
  for (unsigned face = 0; face < t.faces; ++face)
    for (unsigned y = 0; y < t.h; ++y)
      for (unsigned x = 0; x < t.w; ++x) {
        auto px = x + t.packed_x, py = y + t.packed_y;
        auto off = face * t.face_stride +
                   (t.tiled ? tiled_offset(px, py, t.pitch, std::countr_zero(t.bytes))
                            : (uint64_t(py) * t.pitch + px) * t.bytes);
        require(off + t.bytes <= t.length, "Xbox texture block exceeds payload");
        for (unsigned i = 0; i < t.bytes; ++i)
          copy(cursor++, t.start + off + (i ^ swap[t.endian]));
      }
}

inline Bytes export_resource_dds(const Bytes &cpu, const Bytes &gpu) {
  if (is_indexed_texture(cpu))
    return export_indexed_texture(cpu, gpu);
  if (scene_is_raw(cpu))
    return export_raw_dds(cpu, gpu);
  auto t = describe_scene_blocks(cpu, gpu);
  auto result = t.header;
  result.resize(128 + uint64_t(t.w) * t.h * t.bytes * t.faces);
  scene_block_bytes(t, [&](auto dest, auto src) { result[dest] = gpu[src]; });
  return result;
}

inline void replace_resource_dds(const Bytes &cpu, const Bytes &dds, Bytes &gpu) {
  if (is_indexed_texture(cpu)) {
    replace_indexed_texture(cpu, dds, gpu);
    return;
  }
  if (scene_is_raw(cpu)) {
    replace_raw_dds(cpu, dds, gpu);
    return;
  }
  auto t = describe_scene_blocks(cpu, gpu);
  require(dds.size() == 128 + uint64_t(t.w) * t.h * t.bytes * t.faces &&
              std::memcmp(dds.data(), "DDS ", 4) == 0 && le(dds, 4) == 124 &&
              le(dds, 12) == le(t.header, 12) && le(dds, 16) == le(t.header, 16) &&
              le(dds, 24) <= 1 && le(dds, 28) <= 1 &&
              le(dds, 76) == 32 && le(dds, 80) == 4 &&
              le(dds, 84) == le(t.header, 84) && le(dds, 112) == le(t.header, 112),
          "DDS must retain Xbox dimensions, block encoding and face count");
  scene_block_bytes(t, [&](auto src, auto dest) { gpu[dest] = dds[src]; });
}
