#pragma once
#include "common.h"
#include <cmath>

constexpr size_t GeorgiaGpuSize = 0x214000;
constexpr size_t GeorgiaArtworkBaseSize = 0x100000;
constexpr size_t GeorgiaArtworkMipSize = 0x5a000;
constexpr size_t GeorgiaArtworkSize = GeorgiaArtworkBaseSize + GeorgiaArtworkMipSize;
constexpr const char *GeorgiaStockGpu =
    "6d388daf7cc94dab8b16039f32adf026ae1b3b4a52724bd6863dec2857c684c9";

inline void full_floor_artwork_descriptor(Bytes &cpu, size_t slot, size_t gpu_size) {
  put(cpu, slot + 0x60, (2048u << 16) | 1024);
  put(cpu, slot + 0x6c, uint32_t(gpu_size + 1));
  put(cpu, slot + 0x70, GeorgiaArtworkBaseSize);
  put(cpu, slot + 0x74, GeorgiaArtworkMipSize);
  put(cpu, slot + 0x94, (be(cpu, slot + 0x94) & ~(511u << 22)) | (64u << 22) | (1u << 31));
  put(cpu, slot + 0x9c, (be(cpu, slot + 0x9c) & ~0x3ffffffu) | 2047 | (1023u << 13));
  put(cpu, slot + 0xa4, (be(cpu, slot + 0xa4) & ~(15u << 6)) | (11u << 6));
  put(cpu, slot + 0xa8, (be(cpu, slot + 0xa8) & 0xfffu) | GeorgiaArtworkBaseSize);
}

inline size_t court_pointer(const Bytes &cpu, size_t field) {
  const int64_t target = int64_t(field) + int32_t(be(cpu, field)) - 1;
  require(target >= 0 && uint64_t(target) < cpu.size(), "Invalid floor SCNE pointer");
  return size_t(target);
}

inline double floor_half(unsigned value) {
  const unsigned exponent = (value >> 10) & 31;
  require(exponent != 31, "Nonfinite floor UV coordinate");
  const double mantissa = (value & 1023) / 1024.0;
  return std::ldexp((value & 0x8000 ? -1.0 : 1.0) *
                    (exponent ? 1.0 + mantissa : mantissa),
                    exponent ? int(exponent) - 15 : -14);
}

inline Bytes full_floor_scene(const Bytes &cpu, const Bytes &gpu) {
  require(!gpu.empty() && gpu.size() % 4096 == 0, "Floor GPU allocation is not page aligned");
  auto result = cpu;
  const auto mesh = court_pointer(cpu, 0x48), material = court_pointer(cpu, 0x38);
  const auto mesh_count = be(cpu, 0x44), material_count = be(cpu, 0x30);
  require(mesh_count > 0 && mesh_count <= 32 && material_count > 0 && material_count <= 128,
          "Unsupported floor mesh or material count");
  bounds(cpu, mesh, mesh_count * 176);
  bounds(cpu, material, material_count * 40);
  constexpr uint32_t floor = 0xbe45d62e, wood_shader = 0x0b16f952, light_shader = 0xa784c4df;
  require((be(cpu, mesh + 4) == floor || be(cpu, mesh+4)==0xbe56eb5c) &&
          be(cpu, material + 8) == wood_shader,
          "Floor does not use the UGA wood shader layout");
  const auto params = court_pointer(cpu, material + 32);
  require(be(cpu, params + 164) == 0x2701 && be(cpu, params + 204) == 0x3f800000 &&
          be(cpu, params + 208) == 0x3f800000 && !be(cpu, params + 212) && !be(cpu, params + 216),
          "Unknown wood albedo sampler or transform");
  const auto texture = court_pointer(cpu, 0x24);
  const auto format=be(cpu, texture+0x98)&255;
  require(be(cpu, 0x20) && (be(cpu, texture+0x94) >> 31) &&
          format==0x52, "Unknown floor base slot");

  const auto declaration = court_pointer(cpu, mesh + 156);
  require(be(cpu, mesh+152) >= 3 && be(cpu, declaration) == 0x46e6cb71 &&
          be(cpu, declaration+8) == 0x20000000 && be(cpu, declaration+12) == 0x002a23b9 &&
          be(cpu, declaration+128) == 0xf51cd0cf &&
          be(cpu, declaration+136) == 0x201c0000 && be(cpu, declaration+140) == 0x002c235f,
          "Unsupported full-floor vertex declaration");
  const auto streams = court_pointer(cpu, mesh + 136);
  const auto count = be(cpu, streams+8), stride = be(cpu, streams+28);
  const auto start = be(cpu, streams+36) - 1;
  require(count >= 8 && count <= 4096 && stride >= 32 && stride <= 64, "Unsupported floor vertex stream");
  bounds(gpu, start, uint64_t(count) * stride);
  const auto draw=court_pointer(cpu,mesh+128);
  require(be(cpu,mesh+124)==1 && be(cpu,draw)==6 && be(cpu,draw+32)==0 &&
          (be(cpu,mesh+0xa4)&65535)==16,"Unknown principal floor draw");
  const auto first=be(cpu,draw+4), length=be(cpu,draw+8), index_base=be(cpu,mesh+0xac)-1;
  const auto index_count=be(cpu,mesh+0xa8);
  require(first <= index_count && length <= index_count-first,"Invalid principal floor draw range");
  bounds(gpu,index_base,uint64_t(index_count)*2);
  std::set<unsigned> vertices;
  for (size_t i=first;i<size_t(first)+length;++i) {
    const auto off=index_base+i*2;
    const unsigned v=(unsigned(gpu[off])<<8)|gpu[off+1];
    if (v==65535) continue;
    require(v<count,"Floor index outside vertex stream");
    vertices.insert(v);
  }
  require(vertices.size()>=8,"Not enough floor vertices to recover the UGA mapping");
  // Fit the stock UVs to the common UGA artwork coordinates. Only albedo
  // receives this transform, so the original UVs still drive the bump map.
  struct Axis {
    double sum=0, uv_sum=0, uv_square=0, cross=0;
    void add(double uv, double artwork) {
      sum += artwork; uv_sum += uv; uv_square += uv*uv; cross += uv*artwork;
    }
  };
  auto coordinates = [&](size_t i) {
    const auto off = start + i * stride;
    const auto uv = be(gpu, off+28);
    const double x = std::bit_cast<float>(be(gpu, off)), z = std::bit_cast<float>(be(gpu, off+8));
    require(std::isfinite(x) && std::isfinite(z) && std::abs(x)<3000 && std::abs(z)<3000,
            "Unsupported floor world coordinates");
    // UGA's mapped position/UV pairs define this common template.
    return std::array{floor_half(uv >> 16), floor_half(uv & 65535),
                     z * 0.00027335939754 + 0.49997811436,
                     x * 0.00044129545003 + 0.49998535131};
  };
  std::array<Axis,2> axes{};
  for (const auto i:vertices) {
    auto p=coordinates(i);
    for (size_t j=0;j<2;++j) axes[j].add(p[j],p[j+2]);
  }
  std::array<float,2> scale{}, shift{};
  const auto sample_count=vertices.size();
  for (size_t j=0;j<2;++j) {
    const auto &a=axes[j];
    const auto denom=sample_count*a.uv_square-a.uv_sum*a.uv_sum;
    require(denom > 0.001, "Degenerate floor UV axis");
    scale[j]=float((sample_count*a.cross-a.uv_sum*a.sum)/denom);
    shift[j]=float((a.sum-scale[j]*a.uv_sum)/sample_count);
  }
  // Keep the published UGA transform byte-exact for matching UVs.
  const std::array<float,2> uga_scale{std::bit_cast<float>(0x3dc72c9fu),std::bit_cast<float>(0xbe0e63d8u)};
  const std::array<float,2> uga_shift{std::bit_cast<float>(0x3ee71b17u),std::bit_cast<float>(0x3f11c962u)};
  bool uga_uvs=true;
  for (const auto i:vertices) {
    const auto p=coordinates(i);
    for (size_t j=0;j<2;++j) {
      require(std::abs(p[j]*scale[j]+shift[j]-p[j+2])<0.004, "Floor UVs do not fit the UGA template");
      uga_uvs &= std::abs(p[j]*uga_scale[j]+uga_shift[j]-p[j+2])<0.004;
    }
  }
  if (uga_uvs) { scale=uga_scale; shift=uga_shift; }
  for (size_t j=0;j<2;++j) {
    put(result, params+204+j*4, std::bit_cast<uint32_t>(scale[j]));
    put(result, params+212+j*4, std::bit_cast<uint32_t>(shift[j]));
  }
  for (size_t i=1;i<material_count;++i) {
    const auto row=material+i*40;
    if (be(cpu,row+8)==wood_shader)
      put(result,court_pointer(cpu,row+32)+180,0);
  }

  unsigned lighting_runs=0;
  for (size_t i=0;i<mesh_count;++i) {
    const auto part=mesh+i*176, draw=court_pointer(cpu,part+128);
    const auto runs=be(cpu,part+124);
    require(runs>0 && runs<=128, "Unsupported floor draw count");
    bounds(cpu,draw,runs*48);
    size_t first=0, kept=0;
    for (size_t j=0;j<runs;++j) {
      const auto run=draw+j*48;
      const auto mat=be(cpu,run+32);
      require(be(cpu,run)==6 && mat<material_count,"Unsupported floor draw layout");
      const bool lighting=be(cpu,material+mat*40+8)==light_shader;
      lighting_runs+=lighting;
      if (!(lighting || (i==0 && mat==0))) continue;
      if (!kept) first=j;
      require(j==first+kept,"Floor lighting draws are interleaved with artwork");
      ++kept;
    }
    require(i!=0 || kept==1,"Ambiguous principal court floor draw");
    put(result,part+124,uint32_t(kept));
    if (first) put(result,part+128,be(cpu,part+128)+uint32_t(first*48));
  }
  require(lighting_runs>0,"No recognized stock lighting pass");
  full_floor_artwork_descriptor(result, texture, gpu.size());
  return result;
}

// Xbox s256 floor.scne. Source hashes pin the exact topology, stream
// declarations, and verified reuse of the disabled center-logo allocation.
inline J validate_court_scene(const fs::path& source_cpu, const fs::path& source_gpu,
                              const fs::path& edited_cpu, const fs::path& edited_gpu) {
  const auto cpu = read(source_cpu, 64ull << 20);
  const auto gpu = read(source_gpu, 64ull << 20);
  const auto changed_cpu = read(edited_cpu, 64ull << 20);
  const auto changed_gpu = read(edited_gpu, 64ull << 20);
  const bool georgia = sha(cpu) == "9858346b2662ff7000dc551c3ea74ead8d64cca2f90c5a4a5854887a5bc2f690" &&
                       sha(gpu) == GeorgiaStockGpu;
  auto is_full_floor = [&] {
    return changed_gpu.size()==gpu.size()+GeorgiaArtworkSize &&
           std::equal(gpu.begin(),gpu.end(),changed_gpu.begin()) &&
           changed_cpu==full_floor_scene(cpu,gpu);
  };
  if (!georgia || is_full_floor()) {
    require(georgia || is_full_floor(), "Court edit differs from the full-floor conversion");
    return J{{"ready",true},{"stock_passes",true},{"full_resolution",true}};
  }
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
        full_floor_artwork_descriptor(expected,0x90,GeorgiaGpuSize);
      if (full_resolution && changed_cpu != expected) {
        for (size_t part : {3456, 3632, 3808}) word(part + 0x7C, 0);
        if (changed_cpu != expected) {
          // The last draw in the lines mesh uses the lighting material.
          // Point the draw list at that run alone, leaving its bytes intact.
          constexpr size_t lines = 3808, draw_pointer = lines + 0x80;
          word(lines + 0x7C, 1);
          word(draw_pointer, be(cpu, draw_pointer) + 6 * 48);
        }
      }
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
