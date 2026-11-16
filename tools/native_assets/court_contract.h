#pragma once
#include "common.h"
#include <cmath>

constexpr size_t GeorgiaGpuSize = 0x214000;
constexpr size_t GeorgiaArtworkBaseSize = 0x100000;
constexpr size_t GeorgiaArtworkMipSize = 0x5a000;
constexpr size_t GeorgiaArtworkSize = GeorgiaArtworkBaseSize + GeorgiaArtworkMipSize;
constexpr uint32_t GeorgiaBank = 4254803563;
constexpr uint32_t GeorgiaBumpRecord = 0x92255783;
constexpr const char *GeorgiaStockGpu =
    "6d388daf7cc94dab8b16039f32adf026ae1b3b4a52724bd6863dec2857c684c9";

inline void georgia_artwork_descriptor(Bytes &cpu) {
  constexpr size_t slot = 0x90;
  put(cpu, slot + 0x60, (2048u << 16) | 1024);
  put(cpu, slot + 0x6c, GeorgiaGpuSize + 1);
  put(cpu, slot + 0x70, GeorgiaArtworkBaseSize);
  put(cpu, slot + 0x74, GeorgiaArtworkMipSize);
  put(cpu, slot + 0x94, (be(cpu, slot + 0x94) & ~(511u << 22)) | (64u << 22));
  put(cpu, slot + 0x9c, (be(cpu, slot + 0x9c) & ~0x3ffffffu) | 2047 | (1023u << 13));
  put(cpu, slot + 0xa4, (be(cpu, slot + 0xa4) & ~(15u << 6)) | (11u << 6));
  put(cpu, slot + 0xa8, (be(cpu, slot + 0xa8) & 0xfffu) | GeorgiaArtworkBaseSize);
}

// Xbox s256 floor.scne. Source hashes pin the exact topology, stream
// declarations, and verified reuse of the disabled center-logo allocation.
inline J validate_court_scene(const fs::path& source_cpu, const fs::path& source_gpu,
                              const fs::path& edited_cpu, const fs::path& edited_gpu) {
  const auto cpu = read(source_cpu, 64ull << 20);
  const auto gpu = read(source_gpu, 64ull << 20);
  require(sha(cpu) == "9858346b2662ff7000dc551c3ea74ead8d64cca2f90c5a4a5854887a5bc2f690" &&
          sha(gpu) == GeorgiaStockGpu,
          "Court SCNE source layout is not supported");
  const auto changed_cpu = read(edited_cpu, 64ull << 20);
  const auto changed_gpu = read(edited_gpu, 64ull << 20);
  const bool full_resolution = gpu.size() == GeorgiaGpuSize &&
                               changed_gpu.size() == GeorgiaGpuSize + GeorgiaArtworkSize;
  require(cpu.size() == changed_cpu.size() &&
          (gpu.size() == changed_gpu.size() || full_resolution),
          "Unsupported court SCNE component size");
  if (full_resolution)
    require(std::equal(gpu.begin(), gpu.end(), changed_gpu.begin()),
            "Full-resolution Georgia artwork must preserve the original GPU region");

  auto expected = cpu;
  const bool full_floor = changed_cpu != cpu;
  constexpr size_t artwork_start = 0x64000, artwork_size = 0x100000;
  bool stock_passes = false;
  if (full_floor || full_resolution) {
    auto word = [&](size_t offset, uint32_t value) {
      for (unsigned i = 0; i < 4; ++i)
        expected[offset + i] = uint8_t(value >> (24 - i * 8));
    };
    for (size_t part : {3456, 3632, 3808}) word(part + 0x7C, 0);
    constexpr size_t texture = 0x90;
    word(texture + 0x6C, artwork_start + 1);
    word(texture + 0x70, artwork_size);
    word(texture + 0x94, (be(cpu, texture + 0x94) & ~(511u << 22)) | (64u << 22) | (1u << 31));
    word(texture + 0x98, (be(cpu, texture + 0x98) & ~63u) | 18);
    word(texture + 0x9C, (be(cpu, texture + 0x9C) & ~0x3FFFFFFu) | 2047 | (1023u << 13));
    word(texture + 0xA4, be(cpu, texture + 0xA4) & ~0x3FFu);
    word(texture + 0xA8, be(cpu, texture + 0xA8) & ~0x800u);
    if (changed_cpu != expected || full_resolution) {
      expected = cpu;
      const auto materials = 0x37 + be(cpu, 0x38);
      auto params = [&](unsigned material) {
        const auto field = materials + 40 * material + 32;
        return field + be(cpu, field) - 1;
      };
      // Georgia's original tiling UVs are affine to the supplied floor art.
      // Only its albedo transform and the decorative-overlay opacity change.
      constexpr uint32_t albedo_transform[]{
          0x3dc72c9f, 0xbe0e63d8, 0x3ee71b17, 0x3f11c962};
      for (unsigned i = 0; i < 4; ++i)
        word(params(0) + 204 + i * 4, albedo_transform[i]);
      for (unsigned i = 1; i < 19; ++i)
        word(params(i) + 180, 0);
      if (full_resolution)
        georgia_artwork_descriptor(expected);
      if (full_resolution && changed_cpu != expected)
        for (size_t part : {3456, 3632, 3808}) word(part + 0x7C, 0);
      require(changed_cpu == expected, "Court SCNE changes unsupported CPU metadata");
      stock_passes = true;
    }
  }

  constexpr size_t stream = 2082072, stride = 36, uv = 28, vertices = 292;
  for (size_t vertex = 0; vertex < vertices; ++vertex) {
    for (size_t axis = 0; axis < 3; ++axis) {
      const float position = std::bit_cast<float>(be(changed_gpu, stream + vertex * stride + axis * 4));
      require(std::isfinite(position) && std::abs(position) < 1e6f, "Invalid court vertex position");
    }
  }
  size_t changed_bytes = 0;
  for (size_t i = 0; i < gpu.size(); ++i) {
    if (gpu[i] == changed_gpu[i]) continue;
    const bool vertex_byte = i >= stream && i < stream + stride * vertices &&
                             ((i - stream) % stride < 12 ||
                              ((i - stream) % stride >= uv && (i - stream) % stride < uv + 4));
    const bool artwork_byte = full_floor && i >= artwork_start && i < artwork_start + artwork_size;
    // The stock 512-square BC1 slot owns 0x20000 bytes of base image and
    // 0x10000 bytes of mip data. All remaining geometry and textures stay stock.
    require(stock_passes ? i < 0x30000 : vertex_byte || artwork_byte,
            "Court SCNE changes GPU data outside the supported floor regions");
    ++changed_bytes;
  }
  return J{{"ready",true},{"vertices",vertices},{"full_floor",full_floor},
           {"stock_passes",stock_passes},
           {"full_resolution",full_resolution},
           {"changed_gpu_bytes",changed_bytes}};
}
