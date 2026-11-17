#pragma once
#include "folder.h"

// Imports Studio's existing Xbox template layout, never a new IFF dialect.
// Registration is deliberately limited to native roster-linked uniform names.
inline J validate_uniform_bank(const fs::path& game, const fs::path& package,
                               uint32_t template_hash, const std::string& name,
                               const std::string& template_layout_sha256) {
  std::smatch match;
  require(std::regex_match(name,match,std::regex("(sel)?u([haxyz])([0-9]{3,4})\\.iff")),
          "Unsupported Xbox uniform registration name");
  auto artwork=std::stoul(match[3]);
  require(artwork<=1023 && match[3]==decpad(artwork,3),"Uniform artwork ID/name is not canonical");
  auto root=longpath(fs::canonical(longpath(game))), bank=longpath(fs::canonical(longpath(package)));
  auto catalog=json(root/L"assets.json");
  require(catalog.value("platform",std::string())=="xbox360" && catalog.value("storage",std::string())=="loose-resources",
          "Uniform registration requires direct Xbox assets");
  J entry; std::set<std::string> occupied_pixels;
  const auto target_hash=crc(name);
  for(const auto& e:catalog.at("entries")) {
    require(num(e["hash"])!=target_hash,"Uniform bank identity already exists");
    if(num(e["hash"])==template_hash){require(entry.is_null(),"Ambiguous uniform template hash");entry=e;}
    const auto layout=json(contained(root,e["folder"].get<std::string>()+"/asset.json"));
    for(const auto& t:layout.value("textures",J::array())) {
      const auto& d=t.at("descriptor");
      occupied_pixels.insert(std::to_string(num(d["width"]))+":"+std::to_string(num(d["height"]))+":"+
                             std::to_string(num(d["format"]))+":"+t.at("identity").get<std::string>());
    }
  }
  require(!entry.is_null(),"Missing original Xbox uniform template");
  auto source=contained(root,entry["folder"]), source_meta=source/L"asset.json";
  std::smatch source_match;auto source_name=utf8(source.filename());
  require(std::regex_match(source_name,source_match,std::regex("(sel)?u([haxyz])([0-9]{3,4})\\.iff")) &&
          source_match[1].matched==match[1].matched,"Uniform template must be an original matching world/selection bank");
  auto layout=json(source_meta), supplied=json(bank/L"asset.json");
  bool legacy_layout = file_sha(source_meta) != template_layout_sha256;
  require(!legacy_layout ||
              layout.value("legacy_layout_sha256", std::string()) == template_layout_sha256,
          "Uniform template metadata revision differs");
  require(layout.contains("blocks") && layout.contains("records") && !layout.contains("identity"),
          "Uniform template must be an original standard Xbox bank");
  std::map<std::string, std::string> source_paths;
  if (legacy_layout) {
    layout.erase("legacy_layout_sha256");
    layout.erase("named_resources");
    for (auto &r : layout["records"]) {
      auto legacy = r.at("legacy_folder").get<std::string>();
      source_paths[legacy + "/record.json"] = r["folder"].get<std::string>() + "/record.json";
      r["folder"] = legacy;
      r.erase("legacy_folder");
      r.erase("name");
    }
    for (auto &block : layout["blocks"])
      for (auto &component : block["components"])
        if (component.contains("legacy_path")) {
          auto legacy = component["legacy_path"].get<std::string>();
          source_paths[legacy] = component.at("path").get<std::string>();
          component["path"] = legacy;
          component.erase("legacy_path");
        }
    for (auto &piece : layout["pieces"])
      if (piece["path"] == "archive_header.dat") {
        source_paths["gap_00000000.dat"] = "archive_header.dat";
        piece["path"] = "gap_00000000.dat";
      }
  }
  auto source_file = [&](const std::string &relative) {
    auto mapped = source_paths.find(relative);
    return contained(source, mapped == source_paths.end() ? relative : mapped->second);
  };
  auto base=layout, candidate=supplied;
  base.erase("textures");candidate.erase("textures");candidate.erase("identity");
  require(base==candidate,"Uniform clone changes source layout, offsets, identities or opaque metadata");
  const auto flags=catalog.at("loader_metadata").at("toc_flags").at(std::to_string(template_hash));
  J identity{{"name",name},{"hash",target_hash},{"source_size",entry.at("size")},
             {"toc_flags",flags},{"template_hash",template_hash}};
  require(supplied.contains("identity") && supplied["identity"]==identity,"Uniform clone identity/template binding differs");
  std::map<std::string,Bytes> originals, payloads;
  std::map<std::string,std::vector<bool>> writable;
  std::set<std::string> allowed{"asset.json"};
  for(const auto& block:layout["blocks"]) for(const auto& c:block["components"]) {
    auto p=c.at("path").get<std::string>(); allowed.insert(p);
    if(payloads.contains(p))continue;
    auto original=read(source_file(p),128ull<<20), changed=read(contained(bank,p),128ull<<20);
    require(original.size()==num(c["end"])-num(c["start"]) && original.size()==changed.size() && sha(original)==c.at("sha256").get<std::string>(),
            "Uniform clone component bounds/source hash differ");
    originals[p]=std::move(original);payloads[p]=std::move(changed);writable[p]=std::vector<bool>(payloads[p].size(),false);
  }
  std::set<std::string> packed;
  for(const auto& b:layout["blocks"])packed.insert(b["path"]);
  for(const auto& p:layout["pieces"]) {
    auto relative=p["path"].get<std::string>();if(packed.contains(relative))continue;
    allowed.insert(relative);
    require(read(source_file(relative))==read(contained(bank,relative)),"Uniform clone changes header, padding or trailer bytes");
  }
  std::map<std::string,std::set<uint32_t>> component_owners;
  for(const auto& r:layout["records"])for(size_t j=0;j<r["offsets"].size();++j){
    auto offset=num(r["offsets"][j]);if(offset==0xffffffff)continue;
    require(j<layout["blocks"].size(),"Record block exceeds template");
    for(const auto& c:layout["blocks"][j]["components"])if(num(c["start"])==offset)
      component_owners[c["path"].get<std::string>()].insert(uint32_t(num(r["type"])));
  }
  J textures=J::array(), ids=J::array();std::set<std::string> private_pixels;
  bool jersey=false, shorts=false;
  for(const auto& r:layout["records"]) {
    auto record_json=r["folder"].get<std::string>()+"/record.json";
    if(fs::exists(contained(bank,record_json))) {
      auto description = json(source_file(record_json));
      if (legacy_layout) {
        description["folder"] = description.at("legacy_folder");
        description.erase("legacy_folder");
        description.erase("name");
      }
      require(json(contained(bank,record_json))==description,"Descriptive record metadata changed");
      allowed.insert(record_json);
    }
    if(num(r["type"])!=0x5c369069)continue;
    std::vector<std::string> parts;
    for(size_t j=0;j<r["offsets"].size();++j) {
      auto start=num(r["offsets"][j]);if(start==0xffffffff)continue;
      require(j<layout["blocks"].size(),"Invalid template record block");
      std::string found;
      for(const auto& c:layout["blocks"][j]["components"])if(num(c["start"])==start){require(found.empty(),"Shared/ambiguous template component");found=c["path"];}
      require(!found.empty(),"Missing template texture component");parts.push_back(found);
    }
    if(parts.empty() || parts.size()>2)continue;
    Texture info{};Bytes dds;
    try{info=describe(originals.at(parts[0]),parts.size()==2?&originals.at(parts[1]):nullptr);
        dds=export_dds(payloads.at(parts[0]),parts.size()==2?&payloads.at(parts[1]):nullptr);}
    catch(const std::exception&){continue;} // Unsupported source textures must remain unchanged below.
    auto data_part=parts.back(); auto& permitted=writable.at(data_part);
    require(component_owners.at(data_part)==std::set<uint32_t>{0x5c369069},
            "Uniform texture bytes share a non-texture component owner");
    require(info.start<=permitted.size() && info.length<=permitted.size()-info.start,"Texture payload exceeds cloned component");
    for(uint64_t n=info.start;n<info.start+info.length;++n)permitted[n]=true;
    auto source_dds=export_dds(originals.at(parts[0]),parts.size()==2?&originals.at(parts[1]):nullptr);
    require(dds.size()==source_dds.size(),"Cloned native DDS dimensions changed");
    const auto pixel_hash=hex(fnv(std::span(dds).subspan(128)),16);
    auto pixel_key=std::to_string(info.width)+":"+std::to_string(info.height)+":"+std::to_string(info.format)+":"+pixel_hash;
    require(!occupied_pixels.contains(pixel_key) && private_pixels.insert(pixel_key).second,
            "New uniforms require independently registered native texture identities; shared originals reject");
    auto file=r["folder"].get<std::string>()+"/texture.dds";allowed.insert(file);
    auto art=read(contained(bank,file),128ull<<20);validate_dds(art,info.width,info.height,info.format);
    textures.push_back(J{{"path",file},{"record",r["index"]},{"sha256",sha(dds)},
                          {"identity",pixel_hash},{"descriptor",tex_json(info)}});
    ids.push_back(pixel_key);
    const auto id=num(r["id"]);
    // Retail embedded names use case-sensitive CRCs. Keep the older
    // uppercase identities accepted for existing source-bound templates.
    jersey |= id==0xfe29ee06 || id==0x2f027d1b || id==crc("unifregion") || id==crc("unif");
    shorts |= id==0x055fbdef || id==0x8f2890a2 || id==crc("shortregion") || id==crc("short");
  }
  require(!textures.empty(),"Uniform template has no supported native textures");
  require(match[1].matched || (jersey && shorts),"World uniform template lacks verified jersey/shorts artwork records");
  for(auto& block:layout["blocks"])for(auto& c:block["components"]) {
    auto p=c["path"].get<std::string>();const auto& before=originals.at(p);const auto& after=payloads.at(p);
    for(size_t i=0;i<before.size();++i)require(before[i]==after[i] || writable.at(p)[i],"Uniform clone edits non-texture native bytes");
    c["sha256"]=sha(after);
  }
  for(const auto& e:fs::recursive_directory_iterator(bank)) {
    auto attributes=GetFileAttributesW(e.path().c_str());
    require(attributes!=INVALID_FILE_ATTRIBUTES && !(attributes&FILE_ATTRIBUTE_REPARSE_POINT),"Linked uniform package path");
    if(e.is_regular_file())require(allowed.contains(utf8(e.path().lexically_relative(bank))),"Undeclared uniform bank file");
  }
  layout["identity"]=identity;layout["textures"]=textures;
  return J{{"ready",true},{"name",name},{"hash",target_hash},{"artwork",artwork},
           {"selection",match[1].matched},{"variant",std::string("haxyz").find(match[2].str())},
           {"layout",layout},{"texture_identities",ids}};
}
