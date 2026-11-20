#pragma once
#include "common.h"
#include <cmath>

// Xbox-only contracts. Sources: pinned XCONTENT_AGGREGATE_DATA and Studio's
// Xbox ROST/embedded-cloth readers. These checks do not certify gameplay.
inline uint64_t relative_pointer(std::span<const uint8_t> b, uint64_t field,
                                 int64_t bias = 1) {
  int64_t delta = int32_t(be(b, size_t(field)));
  require(delta != 0 && delta != -1, "Null Xbox relative pointer");
  int64_t target = int64_t(field) + delta - bias;
  require(target >= 0 && uint64_t(target) < b.size(), "Xbox pointer exceeds component");
  return uint64_t(target);
}
inline void xbox_string(std::span<const uint8_t> b, uint64_t field) {
  auto delta = int32_t(be(b, field));
  if (!delta || delta == -1) return;
  auto start = relative_pointer(b, field);
  for (unsigned i = 0; i < 2048; ++i) {
    bounds(b, start + i * 2, 2);
    if (!b[start + i * 2] && !b[start + i * 2 + 1]) return;
  }
  throw std::runtime_error("Unterminated Xbox roster string");
}
inline J validate_roster_save(const fs::path& payload, const fs::path& header, bool named=false) {
  auto save = read(payload, 64ull << 20), h = read(header, 328);
  require(h.size() == 328, "Roster requires the exact 328-byte SDK aggregate header");
  require(be(h, 0) == 1 && be(h, 4) == 1, "Roster requires Dummy HDD saved-game content");
  if(named){
    std::string filename; for(size_t i=264;i<306 && h[i];++i) filename+=char(h[i]);
    require(!filename.empty() && filename.size()<42 && filename==utf8(payload.filename()) &&
            filename.size()>4 && filename.substr(filename.size()-4)==".ROS" &&
            filename.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.- ")==std::string::npos,
            "Native roster header/payload filename differs or is unsafe");
  } else require(std::string(reinterpret_cast<const char*>(h.data()+264), 11) == std::string("Roster.ROS\0", 11),
          "Only the observed Roster.ROS package is supported");
  // The SDK's naturally aligned aggregate stores its XUID at 312
  // and title at 320. Older exports used the packed offsets 308/316.
  const auto title_offset=be(h,320)==0x54540818 ? 320 : 316;
  require((named || (be(h,title_offset-8)==0 && be(h,title_offset-4)==0)) &&
              be(h,title_offset)==0x54540818,
          "Roster header must be profile-neutral and title 54540818");
  require(save.size() >= 4 + 0xb0 && be(save, 0) == save.size()-4,
          "Native roster length wrapper differs");
  auto b = std::span<const uint8_t>(save).subspan(4);
  struct Table { uint64_t start, count, stride; };
  auto table = [&](uint64_t field, int64_t bias, uint64_t stride, uint64_t limit) {
    uint64_t count = be(b, field), start = relative_pointer(b, field+4, bias);
    require(count && count <= limit, "Xbox roster table count exceeds profile");
    bounds(b, start, count*stride);
    return Table{start,count,stride};
  };
  auto players=table(8,17,316,65535), arenas=table(0x20,25,28,8192),
       teams=table(0x28,49,704,8192), coaches=table(0x38,21,44,65535),
       conferences=table(0xa8,1,2964,1024), uniforms=table(0x70,1,8,8192);
  auto strings = [&](Table t, std::initializer_list<uint64_t> fields) {
    for(uint64_t i=0;i<t.count;++i) for(auto f:fields) xbox_string(b,t.start+i*t.stride+f);
  };
  strings(players,{0x10,0x14}); strings(teams,{0x30,0x34,0x38,0x3c,0x40});
  strings(arenas,{0x18,0x1c,0x20}); strings(coaches,{0x14,0x18}); strings(conferences,{0,4});
  auto reference = [&](uint64_t field, Table t, int64_t bias, bool nullable) -> int64_t {
    auto delta=int32_t(be(b,field));
    if(delta==0 || delta==-1) { require(nullable,"Required roster relationship is null"); return -1; }
    auto target=relative_pointer(b,field,bias);
    require(target>=t.start && (target-t.start)%t.stride==0 && (target-t.start)/t.stride<t.count,
            "Roster relationship is not a target row");
    return int64_t((target-t.start)/t.stride);
  };
  std::vector<int64_t> assigned(players.count,-1), conference_of(teams.count,-1), members(teams.count,-1);
  std::set<uint32_t> team_uniform_owners;
  for(uint64_t i=0;i<teams.count;++i) {
    auto row=teams.start+i*teams.stride;
    team_uniform_owners.insert((uint32_t(b[row+0x190])<<8)|b[row+0x191]);
    reference(row+0x44,arenas,25,true);
    conference_of[i]=reference(row+0x48,conferences,1,false);
    for(auto f:{0x4c,0x50,0x54}) reference(row+f,teams,49,true);
    for(auto f:{0x60,0x64,0x68}) reference(row+f,coaches,21,true);
    auto count=(uint32_t(b[row+0x188])<<8)|b[row+0x189];
    require(count<=18,"Roster team membership exceeds 18 slots");
    for(unsigned j=0;j<count;++j) {
      auto player=reference(row+0x6c+j*4,players,17,false);
      require(assigned[player]==-1,"Roster player belongs to multiple team slots"); assigned[player]=int64_t(i);
    }
  }
  for(uint64_t i=0;i<conferences.count;++i) {
    auto row=conferences.start+i*conferences.stride;
    auto count=(uint32_t(b[row+0x870])<<8)|b[row+0x871];
    require(count<=100,"Conference membership exceeds 100 slots");
    for(unsigned j=0;j<count;++j) {
      auto team=reference(row+0x6e0+j*4,teams,49,false);
      require(members[team]==-1 && conference_of[team]==int64_t(i),"Conference membership/backlink differs"); members[team]=int64_t(i);
    }
  }
  for(uint64_t i=0;i<teams.count;++i) require(members[i]==conference_of[i],"Team missing from its conference");
  J routes=J::array(); std::set<std::pair<uint32_t,uint32_t>> slots;
  for(uint64_t i=0;i<uniforms.count;++i) {
    auto row=uniforms.start+i*8; auto a=be(b,row), c=be(b,row+4);
    auto owner=(a>>22)&1023, asset=(a>>12)&1023, variant=(a>>8)&7, shape=(c>>27)&7;
    require(variant<5 && shape<5 && slots.insert({owner,variant}).second,"Unsupported/duplicate uniform routing");
    auto name=std::string("u")+"haxyz"[variant]+decpad(asset,3)+".iff";
    routes.push_back(J{{"owner",owner},{"asset",asset},{"variant",variant},{"world_hash",crc(name)},{"selection_hash",crc("sel"+name)}});
  }
  return J{{"ready",true},{"payload_sha256",sha(save)},{"header_sha256",sha(h)},
           {"players",players.count},{"teams",teams.count},{"conferences",conferences.count},{"uniform_routes",routes},
           {"team_uniform_owners",team_uniform_owners}};
}

// Reuse Xbox table packing and append/relative-pointer semantics from Studio's
// uniforms.append. Never infer a team index from a filename's artwork number.
inline J activate_roster_uniforms(const fs::path& payload,const fs::path& header,
                                  const fs::path& request,const fs::path& output) {
  auto proof=validate_roster_save(payload,header,true);
  auto config=json(request);
  bool unlock_existing=config.is_object() && config.value("unlock_existing",false);
  auto plan=config.is_object()?config.at("alternates"):config;
  require(plan.is_array() && plan.size()<=4096,"Invalid uniform activation plan");
  auto save=read(payload,64ull<<20); auto body=std::span<const uint8_t>(save).subspan(4);
  constexpr std::string_view dormant="XRUFv001";
  require(std::search(body.begin(),body.end(),dormant.begin(),dormant.end())==body.end(),
          "Editor dormant uniform metadata requires explicit restoration in Studio");
  auto start=relative_pointer(body,0x74); auto count=be(body,0x70);
  std::vector<std::pair<uint32_t,uint32_t>> rows;
  for(uint32_t i=0;i<count;++i)rows.emplace_back(be(body,start+i*8),be(body,start+i*8+4));
  J changes=J::array(); std::set<std::pair<uint32_t,uint32_t>> requested;
  if(unlock_existing)for(auto& [a,c]:rows)if(a&127){
    changes.push_back(J{{"owner",(a>>22)&1023},{"artwork",(a>>12)&1023},{"variant",(a>>8)&7},{"unlock_only",true}});a&=~127u;
  }
  for(const auto& item:plan){
    require(item.is_object() && item.size()==2+item.contains("required")+item.contains("neck_shape") &&
            item.contains("artwork") && item.contains("variant"),"Unknown activation field");
    std::optional<uint32_t> neck_shape;
    if(item.contains("neck_shape")){
      auto shape=num(item["neck_shape"]);
      require(shape<=4,"Invalid Xbox alternate neckline");
      neck_shape=uint32_t(shape);
    }
    bool required=item.value("required",true);
    auto art=num(item["artwork"]),variant=num(item["variant"]);
    require(art<=1023 && variant>=2 && variant<=4 && requested.insert({art,variant}).second,"Invalid/duplicate alternate activation");
    std::set<uint32_t> owners;
    for(auto [a,c]:rows)if(((a>>12)&1023)==art && ((a>>8)&7)<2 &&
        proof["team_uniform_owners"].end()!=std::find(proof["team_uniform_owners"].begin(),proof["team_uniform_owners"].end(),J((a>>22)&1023))) owners.insert((a>>22)&1023);
    if(owners.empty())for(auto [a,c]:rows)if(((a>>12)&1023)==art && ((a>>8)&7)==variant &&
        proof["team_uniform_owners"].end()!=std::find(proof["team_uniform_owners"].begin(),proof["team_uniform_owners"].end(),J((a>>22)&1023)))owners.insert((a>>22)&1023);
    if(!required && owners.size()!=1)continue;
    require(owners.size()==1,"New alternate artwork has no unique Home/Away or existing explicit route owner in this roster");
    auto owner=*owners.begin(); auto existing=rows.end(),home=rows.end();
    for(auto it=rows.begin();it!=rows.end();++it)if(((it->first>>22)&1023)==owner){
      if(((it->first>>8)&7)==variant)existing=it;
      if(((it->first>>8)&7)==0)home=it;
    }
    if(existing!=rows.end()){
      if(((existing->first>>12)&1023)!=art && !required)continue;
      require(((existing->first>>12)&1023)==art,"Existing alternate routes to different artwork; refusing overwrite");
      auto word1=existing->second;
      if(neck_shape)word1=(word1&~(7u<<27))|(*neck_shape<<27);
      if((existing->first&127)==0 && word1==existing->second)continue;
      existing->first&=~127u;
      existing->second=word1;
    }else{
      if(home==rows.end() && !required)continue;
      require(home!=rows.end() && rows.size()<8192,"Missing Home template or uniform table full");
      auto a=(home->first&~((1023u<<12)|(7u<<8)|127u))|(art<<12)|(variant<<8);
      auto word1=home->second;
      if(neck_shape)word1=(word1&~(7u<<27))|(*neck_shape<<27);
      rows.emplace_back(a,word1);
    }
    changes.push_back(J{{"owner",owner},{"artwork",art},{"variant",variant}});
  }
  auto put=[&](size_t at,uint32_t v){bounds(save,at,4);for(unsigned i=0;i<4;++i)save[at+i]=uint8_t(v>>(24-i*8));};
  if(!changes.empty()){
    while((save.size()-4)%4)save.push_back(0);
    auto target=save.size()-4;
    require(target>=0x74 && target-0x74+1<=INT32_MAX && save.size()+rows.size()*8<=(64ull<<20),"Uniform append exceeds native limits");
    for(auto [a,c]:rows)for(auto v:{a,c})for(unsigned i=0;i<4;++i)save.push_back(uint8_t(v>>(24-i*8)));
    put(4+0x70,uint32_t(rows.size()));put(4+0x74,uint32_t(target-0x74+1));put(0,uint32_t(save.size()-4));
  }
  require(!fs::exists(output) && output.filename()==payload.filename(),"Activation output must be a new file retaining native filename");
  write(output,save);
  try{validate_roster_save(output,header,true);}catch(...){fs::remove(output);throw;}
  return J{{"ready",true},{"changes",changes},{"source_sha256",proof["payload_sha256"]},{"output_sha256",sha(save)}};
}

inline J vanilla_uniform_routes(const fs::path& game) {
  auto catalog=json(game/L"assets.json");
  require(catalog.value("platform",std::string())=="xbox360" && catalog.value("storage",std::string())=="loose-resources","Vanilla uniform discovery requires Xbox catalog");
  require(sha(read(game/L"default.xex",64ull<<20))=="71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36","Unsupported vanilla XEX revision");
  std::set<uint32_t> hashes;
  for(const auto& entry:catalog.at("entries"))require(hashes.insert(uint32_t(num(entry.at("hash")))).second,"Ambiguous vanilla bank hash");
  J routes=J::array();
  for(unsigned art=0;art<=1023;++art)for(unsigned variant=2;variant<=4;++variant){
    auto name=std::string("u")+"haxyz"[variant]+decpad(art,3)+".iff";
    if(hashes.contains(crc(name)) && hashes.contains(crc("sel"+name)))routes.push_back(J{{"artwork",art},{"variant",variant},{"required",false}});
  }
  return J{{"ready",true},{"alternates",routes}};
}

inline J validate_cloth_positions(const fs::path& original, const fs::path& replacement) {
  auto b=read(original,64ull<<20), changed=read(replacement,64ull<<20);
  require(b.size()==changed.size(),"SCNE position edits must preserve component size");
  const bool bench_shorts = b.size() == 274176 &&
      sha(b) == "fcec1c9c54dfb0fd122dee18ccab6d2a85a1bb319d842bc29160770e4caf97fd";
  bounds(b,0,0xb0); auto count=be(b,0x44);
  require(count && count<=4096,"Unsupported embedded-cloth mesh count");
  auto table=relative_pointer(b,0x48); bounds(b,table,uint64_t(count)*176);
  std::vector<bool> allowed(b.size(),false); uint64_t vertices_total=0;
  // Structural bytes, draw runs, declarations, indices, UVs and unknown bytes
  // remain byte-identical. This supports only one-component CPU float3 cloth.
  for(uint32_t i=0;i<count;++i) {
    auto part=table+uint64_t(i)*176; auto runs=be(b,part+0x7c);
    require(runs && runs<=10000 && be(b,part+0x84)==1,"Unsupported cloth vertex descriptor/draw count");
    auto desc=relative_pointer(b,part+0x88); auto vertices=be(b,desc+8), streams=be(b,desc+12)>>16;
    require(vertices && vertices<=250000 && streams && streams<=16,"Unsupported cloth stream dimensions");
    bounds(b,desc+24,uint64_t(streams)*24);
    auto n=be(b,part+0x98); require(n && n<=32,"Unsupported cloth declaration count");
    auto decl=relative_pointer(b,part+0x9c); bounds(b,decl,uint64_t(n)*64);
    unsigned matches=0; uint64_t start=0,stride=0;
    for(uint32_t j=0;j<n;++j) {
      auto a=decl+uint64_t(j)*64; auto fmt=be(b,a+12)&63;
      if((b[a+8]!=0x20 && b[a+8]!=0x30) || b[a+9]!=0 || b[a+11]!=0 ||
         (fmt!=57 && fmt!=26 && fmt!=38 && fmt!=7 && fmt!=16 && fmt!=17)) continue;
      ++matches;
      require(b[a+8]==0x20 && fmt==57 && b[a+10]<streams,"Only unquantized Xbox float3 cloth positions are supported");
      auto entry=desc+24+uint64_t(b[a+10])*24; stride=be(b,entry+4);
      require(stride>=12 && stride<=256 && uint64_t(vertices)*stride==be(b,entry+8),"Cloth stride/count mismatch");
      start=relative_pointer(b,entry+12);
      require(start%4==0 && stride%4==0,"Cloth float3 stream is not word aligned");
      bounds(b,start,uint64_t(vertices)*stride);
    }
    require(matches==1,"Ambiguous cloth position declaration");
    require((be(b,part+0xa4)&0xffff)==16 && !(be(b,part+0xa4)&~0x30010010u),"Unsupported cloth index format");
    auto indices=be(b,part+0xa8); require(indices && indices<=2000000,"Cloth index count exceeds limit");
    auto ib=relative_pointer(b,part+0xac); bounds(b,ib,uint64_t(indices)*2);
    for(uint32_t j=0;j<indices;++j){auto index=(unsigned(b[ib+j*2])<<8)|b[ib+j*2+1]; require(index==65535 || index<vertices,"Cloth index outside source vertices");}
    if (bench_shorts) {
      // The inline bench mesh combines shorts, jersey, skin and shoes. The
      // pinned source has no vertices shared between the shorts and other draws.
      const auto shorts = relative_pointer(b, part + 0x80) + 48;
      require(be(b, shorts + 32) == 1, "Expected the bench shorts material");
      const auto first = be(b, shorts + 4), length = be(b, shorts + 8);
      require(first <= indices && length <= indices - first, "Invalid bench shorts draw range");
      for (uint32_t j = first; j < first + length; ++j) {
        const auto vertex = (unsigned(b[ib + 2*j]) << 8) | b[ib + 2*j + 1];
        if (vertex == 65535) continue;
        const auto off = start + uint64_t(vertex) * stride + 4;
        const float old_y = std::bit_cast<float>(be(b, off));
        const float new_y = std::bit_cast<float>(be(changed, off));
        require(std::isfinite(new_y) && new_y >= old_y && new_y <= old_y + 12.0f,
                "Bench shorts hem exceeds the supported range");
        for (unsigned byte = 0; byte < 4; ++byte) allowed[off + byte] = true;
      }
      vertices_total += vertices;
      continue;
    }
    for(uint32_t j=0;j<vertices;++j) for(unsigned k=0;k<3;++k) {
      auto off=start+uint64_t(j)*stride+k*4;
      auto value=std::bit_cast<float>(be(changed,off));
      require(std::isfinite(value) && std::abs(value)<1e6f,"Invalid cloth position");
      for(unsigned byte=0;byte<4;++byte) allowed[off+byte]=true;
    }
    vertices_total+=vertices;
  }
  uint64_t differences=0;
  for(size_t i=0;i<b.size();++i) if(b[i]!=changed[i]){require(allowed[i],"SCNE edit changes topology, metadata or non-position bytes"); ++differences;}
  return J{{"ready",true},{"meshes",count},{"vertices",vertices_total},{"changed_bytes",differences},{"source_sha256",sha(b)},{"sha256",sha(changed)}};
}

inline J validate_cloth_rest(const fs::path &original, const fs::path &replacement) {
  const auto stock = read(original, 66560);
  const auto edited = read(replacement, 66560);
  const auto digest = sha(stock);
  require(stock.size() == 66560 && edited.size() == stock.size() &&
          (digest == "f99adc97860d13a78bad98aa4474b4fbc8b170d9a3584544ec51e503ff50e670" ||
           digest == "101497361f1c8c6b6b984a786ebf06d000f34d08ed0c180437922287c9879121" ||
           digest == "32ee7e84d666be6b650cd48a79ce78373453971d7720bb0729e62aa96739da4a"),
          "Unsupported Xbox shorts rest-position resource");
  constexpr size_t start = 0xb0, count = 800, stride = 8;
  constexpr uint64_t y_mask = 0xfffffull << 20;
  auto expected = stock;
  size_t changed = 0;
  auto signed_y = [](uint64_t word) {
    return int32_t(((word >> 20) & 0xfffff) ^ 0x80000) - 0x80000;
  };
  for (size_t i = 0; i < count; ++i) {
    const auto offset = start + i * stride;
    const auto old = uint64_t(be(stock, offset)) << 32 | be(stock, offset + 4);
    const auto next = uint64_t(be(edited, offset)) << 32 | be(edited, offset + 4);
    require(((old ^ next) & ~y_mask) == 0 &&
            std::abs(signed_y(old) - signed_y(next)) <= 12 * 2048,
            "Unsupported shorts rest-position change");
    put(expected, offset, uint32_t(next >> 32));
    put(expected, offset + 4, uint32_t(next));
    changed += old != next;
  }

  // Xbox schedules two distance constraints per 12-byte record. Endpoints
  // and flags remain fixed. Each length has nine bits and a separate enable bit.
  const size_t first = 0x1f + be(stock, 0x20);
  const size_t end = 0x17 + be(stock, 0x18);
  size_t constraints = 0;
  for (size_t offset = first; offset + 12 <= end; offset += 12) {
    const auto endpoints = be(stock, offset);
    const auto packed = be(stock, offset + 4);
    auto updated = packed;
    const auto next = be(edited, offset + 4);
    for (unsigned lane = 0; lane < 2; ++lane) {
      const unsigned shift = lane * 10;
      const auto particle = (lane ? packed : endpoints) >> 20;
      const auto delta = (endpoints >> (lane ? 0 : 10)) & 1023u;
      const auto length = (packed >> shift) & 511u;
      const auto new_length = (next >> shift) & 511u;
      if (new_length == length) continue;
      require((packed & (512u << shift)) && length && new_length &&
              delta && particle + delta < count,
              "Unsupported shorts distance constraint change");
      updated = (updated & ~(511u << shift)) | (new_length << shift);
      ++constraints;
    }
    put(expected, offset + 4, updated);
  }
  require(expected == edited, "Shorts simulation changes unsupported data");
  return J{{"ready", true}, {"positions", count}, {"changed", changed},
           {"changed_constraints", constraints}};
}
