#pragma once
#include "folder.h"

inline uint32_t resource_crc(std::string_view name) {
  uint32_t value = ~0u;
  for (auto c : name) {
    value ^= uint8_t(c);
    for (int j = 0; j < 8; ++j)
      value = (value >> 1) ^ (0xedb88320u & uint32_t(-int32_t(value & 1)));
  }
  return ~value;
}

inline const std::map<uint32_t, std::string> &resource_names() {
  static const auto names = [] {
    std::map<uint32_t, std::string> result;
    for (std::string name : {"floor", "arena", "crowd", "rost", "roster",
         "shorts", "jersey", "unifregion", "shortregion", "hi_shoe1",
         "lo_shoe1", "jersey_numbers", "numbers", "names", "unidata", "basket", "rim", "backboard", "net", "bench", "diffuse",
         "normal", "specular", "reflection", "ambientocclusion", "floor_lines",
         "floor_logo", "floor_wood", "court", "lines", "wood", "lightmap",
         "logo", "centerlogo", "scoreboard", "scorebug", "sponsors"})
      result.emplace(resource_crc(name), name);
    for (unsigned i = 0; i < 1000; ++i) {
      auto name = "logo" + decpad(i, 3);
      result.emplace(resource_crc(name), name);
    }
    return result;
  }();
  return names;
}

inline std::string resource_label(const J &record) {
  auto id = uint32_t(num(record.at("id")));
  auto type = uint32_t(num(record.at("type")));
  if (auto it = resource_names().find(id); it != resource_names().end())
    return it->second;
  auto ext = extension(type);
  if (ext == "cdan" || ext == "anim")
    return "animation_" + hex(id);
  if (ext == "layt")
    return "layout_" + hex(id);
  if (ext == "txtr")
    return "texture_" + hex(id);
  return (ext == hex(type) ? "resource" : ext) + "_" + hex(id);
}

inline std::string component_name(uint32_t type, size_t slot) {
  if (slot > 1)
    return "component_" + std::to_string(slot) + ".dat";
  switch (type) {
  case 0xe26c9b5d: return slot ? "scene_gpu.dat" : "scene.dat";
  case 0x5c369069:
  case 0x5c36fb69: return slot ? "texture_pixels.dat" : "texture_header.dat";
  case 0x86a1ac9e: return slot ? "layout_gpu.dat" : "layout.dat";
  case 0x513e89ef:
  case 0xa7701f00: return slot ? "animation_aux.dat" : "animation.dat";
  case 0xc61649b2: return slot ? "roster_aux.dat" : "roster.dat";
  case 0x1aedda1f: return slot ? "audio_packets.dat" : "audio_header.dat";
  case 0x68b693b2: return slot ? "names_aux.dat" : "names.dat";
  default: {
    auto ext = extension(type);
    if (ext == hex(type))
      ext = "resource";
    return ext + (slot ? "_aux.dat" : "_data.dat");
  }
  }
}

inline std::map<unsigned, std::set<std::string>> scene_geometry_names(
    const Bytes &cpu, unsigned materials) {
  std::map<unsigned, std::set<std::string>> names;
  try {
    auto count = be(cpu, 0x44);
    if (!count || count > 4096 || !be(cpu, 0x48))
      return names;
    uint64_t table = 0x47ull + be(cpu, 0x48);
    bounds(cpu, table, count * 176ull);
    for (unsigned i = 0; i < count; ++i) {
      auto mesh = table + i * 176;
      auto bias = int32_t(be(cpu, mesh));
      auto hash = be(cpu, mesh + 4);
      auto begin = int64_t(mesh) + bias - 1;
      std::string name;
      if (bias && bias != -1 && begin >= 0 && uint64_t(begin) < cpu.size()) {
        auto end = uint64_t(begin);
        for (; end + 1 < cpu.size() && end - begin < 128; end += 2) {
          auto c = cpu[end + 1];
          if (!cpu[end] && !c)
            break;
          if (cpu[end] || (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') &&
              !(c >= '0' && c <= '9') && c != '_' && c != '-' && c != '.')) {
            name.clear();
            break;
          }
          name += char(c);
        }
        if (end + 1 >= cpu.size() || cpu[end] || cpu[end + 1] ||
            resource_crc(name) != hash)
          name.clear();
      }
      if (name.empty()) {
        static const std::map<uint32_t, const char *> verified{
            {0xbe45d62e, "floor"}, {0x577a8417, "paint"},
            {0x0c093d16, "centerlogo"}, {0x4f018c96, "lines"}};
        if (auto known = verified.find(hash); known != verified.end())
          name = known->second;
        else
          continue;
      }
      auto draws = be(cpu, mesh + 0x7c), indices = be(cpu, mesh + 0xa8);
      auto pointer = int32_t(be(cpu, mesh + 0x80));
      auto draw_start = int64_t(mesh) + 0x7f + pointer;
      if (!draws || draws > 10000 || !pointer || pointer == -1 || draw_start < 0)
        continue;
      auto start = uint64_t(draw_start);
      std::vector<std::set<unsigned>> candidates;
      for (uint64_t stride : {48ull, 64ull}) {
        if (start > cpu.size() || draws * stride > cpu.size() - start)
          continue;
        std::set<unsigned> linked;
        bool valid = true;
        for (unsigned j = 0; j < draws; ++j) {
          auto draw = start + j * stride;
          auto material = be(cpu, draw + 32);
          if (stride == 64)
            material >>= 16;
          if (be(cpu, draw) != 6 ||
              uint64_t(be(cpu, draw + 4)) + be(cpu, draw + 8) > indices ||
              material >= materials) {
            valid = false;
            break;
          }
          if (be(cpu, draw + 8))
            linked.insert(material);
        }
        if (valid && (candidates.empty() || candidates.front() != linked))
          candidates.push_back(std::move(linked));
      }
      if (candidates.size() == 1)
        for (auto index : candidates.front())
          names[index].insert(lower(name));
    }
  } catch (const std::exception &) {
    names.clear();
  }
  return names;
}

struct SceneTextureLabel {
  std::set<std::string> roles, meshes;
};

inline std::map<uint32_t, SceneTextureLabel> scene_sampler_names(const Bytes &cpu) {
  std::map<uint32_t, SceneTextureLabel> labels;
  if (cpu.size() < 0x3c)
    return labels;
  static const std::map<uint32_t, std::string> semantics = [] {
    std::map<uint32_t, std::string> names;
    for (const auto &[name, label] :
         std::initializer_list<std::pair<std::string_view, const char *>>{
             {"DiffuseSampler", "diffuse"}, {"DiffuseTextureSampler", "diffuse"},
             {"DiffuseMapSampler", "diffuse"}, {"ColorSampler", "color"},
             {"NormalSampler", "normal"}, {"NormalMapSampler", "normal"},
             {"NormalGlossDetailSampler", "normal_gloss_detail"},
             {"AmbientOcclusionSampler", "ambient_occlusion"},
             {"ReflectionSampler", "reflection"}, {"SpecularSampler", "specular"},
             {"GlossSampler", "gloss"}, {"LightMapSampler", "lightmap"},
             {"ShadowSampler", "shadow"}, {"DetailSampler", "detail"},
             {"MaskSampler", "mask"}, {"EnvMapSampler", "environment"}})
      names.emplace(resource_crc(name), label);
    names.emplace(0xb6e7ae40, "diffuse");
    names.emplace(0x49412c54, "diffuse");
    return names;
  }();
  try {
    auto shaders = be(cpu, 0x28), materials = be(cpu, 0x30);
    if (!shaders || shaders > 256 || !materials || materials > 10000 ||
        !be(cpu, 0x38))
      return labels;
    uint64_t shader_table = 0x2bull + be(cpu, 0x2c);
    uint64_t material_table = 0x37ull + be(cpu, 0x38);
    bounds(cpu, shader_table, shaders * 48ull);
    bounds(cpu, material_table, materials * 40ull);
    std::map<uint32_t, uint64_t> shader_offsets;
    for (unsigned i = 0; i < shaders; ++i) {
      auto shader = shader_table + i * 48;
      shader_offsets.try_emplace(be(cpu, shader), shader);
    }
    auto geometry = scene_geometry_names(cpu, materials);
    for (unsigned i = 0; i < materials; ++i) {
      auto material = material_table + i * 40;
      auto shader = shader_offsets.find(be(cpu, material + 8));
      if (shader == shader_offsets.end())
        continue;
      auto at = shader->second;
      auto count = be(cpu, at + 8) & 65535, length = be(cpu, at + 12) & 65535;
      if (!count || count > 32 || !length)
        continue;
      auto params = material + 31 + be(cpu, material + 32);
      auto samplers = at + 27 + be(cpu, at + 28);
      bounds(cpu, params, length);
      bounds(cpu, samplers, count * 36ull);
      for (unsigned j = 0; j < count; ++j) {
        auto entry = samplers + j * 36;
        auto label = semantics.find(be(cpu, entry));
        auto ref = be(cpu, entry + 16) / 65536 + 12;
        if (label != semantics.end() && ref + 4 <= length) {
          auto &usage = labels[be(cpu, params + ref)];
          usage.roles.insert(label->second);
          if (auto mesh = geometry.find(i); mesh != geometry.end())
            usage.meshes.insert(mesh->second.begin(), mesh->second.end());
        }
      }
    }
  } catch (const std::exception &) {
    labels.clear();
  }
  return labels;
}

inline void relocate_resource(const fs::path &from, const fs::path &to) {
  if (from == to)
    return;
  require(!fs::exists(to), "Named resource already exists: " + utf8(to));
  fs::create_directories(to.parent_path());
  fs::rename(from, to);
}

inline void name_assets(Folder &f, Job &job) {
  std::map<std::string, std::string> moved_components;
  std::map<uint32_t, J> layouts;
  uint64_t done = 0;
  for (auto &[id, e] : f.entries) {
    if (done++ % 64 == 0)
      job.update(done, f.entries.size(), "Naming Xbox resources from their headers...");
    job.check();
    auto l = f.layout(e);
    if (l.value("named_resources", 0) == 1)
      continue;
    auto bank = e.at("folder").get<std::string>();
    auto folder = contained(f.root, bank);
    auto key = l.contains("paired_resources") ? "paired_resources" : "records";
    if (!l.contains(key))
      continue;
    auto &records = l[key];
    std::map<std::string, unsigned> names;
    for (auto &r : records) {
      auto ext = extension(uint32_t(num(r.at("type"))));
      r["name"] = resource_label(r);
      ++names[r["name"].get<std::string>() + "." + ext];
    }
    std::map<std::string, std::tuple<std::string, uint32_t, bool>> destinations;
    for (auto &r : records) {
      uint32_t type = uint32_t(num(r.at("type")));
      auto old = r.at("folder").get<std::string>();
      auto label = r["name"].get<std::string>(), ext = extension(type);
      if (names[label + "." + ext] > 1)
        label += "_" + decpad(num(r.at("index")));
      auto name = label + "." + ext;
      r["legacy_folder"] = old;
      r["folder"] = name;
      bool inline_pixels = (type == 0x5c369069 || type == 0x5c36fb69) &&
          std::count_if(r["offsets"].begin(), r["offsets"].end(),
                        [](const auto &offset) { return num(offset) != 0xffffffff; }) == 1;
      destinations.emplace(old, std::tuple{name, type, inline_pixels});
      if (fs::exists(contained(folder, old)))
        relocate_resource(contained(folder, old), contained(folder, name));
      if (r.contains("component_files"))
        for (size_t j = 0; j < r["component_files"].size(); ++j) {
          auto &c = r["component_files"][j];
          if (c["path"].is_null())
            continue;
          auto original = c["folder"].get<std::string>() + "/" +
                          c["path"].get<std::string>();
          auto target = name + "/" +
              (inline_pixels ? "texture_inline.dat" : component_name(type, j));
          auto [it, fresh] = moved_components.emplace(original, bank + "/" + target);
          if (fresh)
            relocate_resource(contained(f.root, original), contained(f.root, it->second));
          auto split = it->second.find('/', 7);
          c["folder"] = it->second.substr(0, split);
          c["path"] = it->second.substr(split + 1);
        }
      jsonwrite(contained(folder, name + "/record.json"), r);
    }
    if (l.contains("blocks"))
      for (auto &b : l["blocks"]) {
        auto j = num(b["index"]);
        for (auto &c : b["components"]) {
          auto old = c["path"].get<std::string>();
          auto split = old.find('/');
          auto dest = destinations.find(old.substr(0, split));
          if (dest == destinations.end())
            continue;
          const auto &[name, type, inline_pixels] = dest->second;
          auto source = name + old.substr(split);
          auto target = name + "/" +
              (inline_pixels ? "texture_inline.dat" : component_name(type, j));
          relocate_resource(contained(folder, source), contained(folder, target));
          c["legacy_path"] = old;
          c["path"] = target;
        }
      }
    for (auto &t : l["textures"]) {
      auto old = t["path"].get<std::string>();
      auto split = old.find('/');
      auto dest = destinations.find(old.substr(0, split));
      if (dest != destinations.end())
        t["path"] = std::get<0>(dest->second) + old.substr(split);
    }
    if (l.contains("pieces"))
      for (auto &piece : l["pieces"])
        if (num(piece["offset"]) == 0 && piece["path"] == "gap_00000000.dat") {
          relocate_resource(contained(folder, "gap_00000000.dat"),
                            contained(folder, "archive_header.dat"));
          piece["path"] = "archive_header.dat";
        }
    static const std::regex uniform_bank("(sel)?u[haxyz][0-9]{3,4}\\.iff");
    if (std::regex_match(utf8(folder.filename()), uniform_bank))
      l["legacy_layout_sha256"] = file_sha(folder / L"asset.json");
    l["named_resources"] = 1;
    layouts.emplace(id, std::move(l));
  }
  for (auto &[id, e] : f.entries) {
    auto found = layouts.find(id);
    auto l = found == layouts.end() ? f.layout(e) : std::move(found->second);
    bool changed = found != layouts.end();
    auto bank = e["folder"].get<std::string>();
    if (l.contains("loose_segments"))
      for (auto &s : l["loose_segments"]) {
        auto it = moved_components.find(bank + "/" + s["path"].get<std::string>());
        if (it == moved_components.end())
          continue;
        s["resource_file"] = it->second;
        changed = true;
      }
    if (changed)
      jsonwrite(contained(f.root, bank + "/asset.json"), l);
  }
}
