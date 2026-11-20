#pragma once
#include "codec.h"
#include "court_contract.h"

inline Bytes tile_full_floor_dds(const Bytes &dds) {
  require(dds.size() >= 128 && le(dds,0)==0x20534444 && le(dds,4)==124 &&
          le(dds,12)==1024 && le(dds,16)==2048 && le(dds,28)==12 &&
          le(dds,76)==32 && le(dds,84)==0x31545844 && !le(dds,112),
          "Use a 2048x1024 BC1/DXT1 DDS with all 12 mip levels");
  constexpr std::array<size_t,6> starts{0,0x100000,0x140000,0x150000,0x154000,0x156000};
  constexpr std::array<unsigned,6> tail_x{0,0,0,4,2,1}, tail_y{4,2,1,0,0,0};
  Bytes tiled(GeorgiaArtworkSize);
  size_t input=128;
  for (unsigned level=0;level<12;++level) {
    const unsigned width=std::max(1u,512u>>level), height=std::max(1u,256u>>level);
    const auto base=level<6?starts[level]:size_t(0x158000);
    const auto dx=level<6?0:tail_x[level-6], dy=level<6?0:tail_y[level-6];
    for (unsigned y=0;y<height;++y) for (unsigned x=0;x<width;++x) {
      const auto target=base+tiled_offset(x+dx,y+dy,std::max(32u,width),3);
      bounds(dds,input,8);
      bounds(tiled,target,8);
      for (unsigned i=0;i<8;++i) tiled[target+i]=dds[input+(i^1)];
      input+=8;
    }
  }
  require(input==dds.size(),"DDS payload has unexpected trailing bytes");
  return tiled;
}

inline J build_full_floor(const fs::path &game, const fs::path &art, const fs::path &mods,
                          const std::string &xex_hash) {
  const auto court=utf8(art.parent_path().filename());
  require(std::regex_match(court,std::regex("s[0-9]{3}")),
          "Put the DDS in a court ID folder such as s272, then drag it onto Build Court.cmd");
  require(sha(read(game/L"default.xex",64ull<<20))==xex_hash,"Unsupported base XEX");
  const std::string bank="assets/"+court+".iff", floor=bank+"/floor.scne";
  const auto record=json(game/path(floor+"/record.json"));
  require(record["id"]==0xbe45d62e && record["type"]==0xe26c9b5d &&
          record["offsets"].size()==2,"Court has no standard two-component floor");
  const std::string cpu_path=floor+"/scene.dat", gpu_path=floor+"/scene_gpu.dat";
  const auto cpu=read(game/path(cpu_path),64ull<<20);
  auto gpu=read(game/path(gpu_path),64ull<<20);
  const auto edited=full_floor_scene(cpu,gpu);
  const auto artwork=tile_full_floor_dds(read(art,4ull<<20));
  const auto original_gpu_sha=sha(gpu);
  gpu.insert(gpu.end(),artwork.begin(),artwork.end());
  const std::string id="full-floor."+court;
  fs::create_directories(mods);
  fs::path out;
  std::string version;
  for (unsigned revision=0;revision<100000;++revision) {
    version="1.0."+std::to_string(revision);
    out=mods/path(id+"-"+version);
    if (fs::create_directory(out)) break;
    require(revision<99999,"No available court mod version");
  }
  J assets=J::array();
  auto save=[&](const std::string &file,const Bytes &payload,const std::string &original,unsigned component) {
    publish(out/path(file),payload);
    assets.push_back(J{{"kind","court.scene"},{"component",component},
      {"bank_hash",crc(court+".iff")},{"record_index",record["index"]},
      {"record_id",record["id"]},{"record_type",record["type"]},
      {"target",file},{"source_sha256",original},{"file",file},{"sha256",sha(payload)}});
  };
  save(cpu_path,edited,sha(cpu),0);
  save(gpu_path,gpu,original_gpu_sha,1);
  jsonwrite(out/L"mod.json",J{{"schema_version",1},{"id",id},{"name","Full Court "+court},
    {"author","Local court artwork"},{"version",version},{"content",J::array({"assets"})},
    {"requires",{{"xex_sha256",xex_hash},{"recomp","ZMO-beta1"},{"mod_api","1.3.0"}}},
    {"capabilities",J::array({"court.scene"})},{"dependencies",J::array()},
    {"incompatible",J::array()},{"assets",assets}});
  return J{{"ready",true},{"court",court},{"version",version},{"mod",utf8(out)}};
}

inline J audit_full_floors(const fs::path &game) {
  const std::regex id("s[0-9]{3}\\.iff");
  J supported=J::array(), unsupported=J::object();
  for (const auto &bank:fs::directory_iterator(game/L"assets")) {
    const auto name=utf8(bank.path().filename());
    if (!bank.is_directory() || !std::regex_match(name,id)) continue;
    const auto floor=bank.path()/L"floor.scne";
    try {
      const auto cpu=read(floor/L"scene.dat",64ull<<20);
      const auto gpu=read(floor/L"scene_gpu.dat",64ull<<20);
      full_floor_scene(cpu,gpu);
      supported.push_back(name);
    } catch (const std::exception &error) {
      unsupported[name]=error.what();
    }
  }
  return J{{"supported",supported},{"unsupported",unsupported}};
}
