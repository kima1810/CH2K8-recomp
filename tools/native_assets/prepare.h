#pragma once
#include "named_layout.h"
#include "scene_image.h"

// Verified court artwork exceptions to the shared Xbox format and material rule.
// Match all four identifiers so a different scene or texture keeps the default.
inline bool court_texture_support(uint32_t bank, uint32_t record, uint32_t slot,
                                  uint32_t texture, bool default_support) {
  struct Placement {
    uint32_t bank, record, slot, texture;
    bool support;
  };
  static constexpr Placement placements[] = {
      {0x3975fa24, 9, 2, 0xb3151c0e, true},   // s013 floor
      {0x42ab980a, 1, 9, 0xaadcd2be, true},  // s258 arena
      {0x42ab980a, 1, 18, 0xff1c08c9, true},
      {0x42ab980a, 1, 21, 0xcd85219f, true},
      {0x42ab980a, 1, 24, 0x7857b3a2, true},
      {0x42ab980a, 1, 25, 0xe61dc45a, true},
      {0x42ab980a, 1, 26, 0x63a021c2, true},
      {0x42ab980a, 1, 30, 0xc518ad48, false},
      {0x42ab980a, 1, 40, 0xe7ba9d70, true},
      {0x42ab980a, 9, 2, 0xb7cb594f, true},  // s258 floor
      {0x42ab980a, 9, 10, 0xcba9122e, true},
      {0xfea11aac, 9, 13, 0x9f39fccc, true}, // s302 floor
  };
  for (const auto &entry : placements)
    if (entry.bank == bank && entry.record == record && entry.slot == slot &&
        entry.texture == texture)
      return entry.support;
  return default_support;
}
inline J discover(Folder &f) {
  J edits = J::array();
  for (auto &[id, e] : f.entries)
    for (auto &r : f.records(e)) {
      auto folder = contained(f.root, e["folder"].get<std::string>() + "/" +
                                          r["folder"].get<std::string>());
      J ref{{"bank", id}, {"record", r["index"]}};
      auto kind = num(r["type"]);
      auto add = [&](const fs::path &p, std::string type, J reference) {
        edits.push_back(J{{"file", utf8(p.lexically_relative(f.root))},
                          {"kind", type},
                          {"source", reference}});
      };
      if ((kind == 0x5c369069 || kind == 0x5c36fb69) &&
          fs::is_regular_file(folder / L"texture.dds"))
        add(folder / L"texture.dds", "dds", ref);
      else if (kind == 0xe26c9b5d && fs::is_directory(folder)) {
        std::regex pattern("texture_([0-9]{4})\\.dds", std::regex::icase);
        for (auto &p : fs::directory_iterator(folder)) {
          std::smatch match;
          auto name = utf8(p.path().filename());
          if (p.is_regular_file() && std::regex_match(name, match, pattern)) {
            auto reference = ref;
            reference["texture"] = std::stoul(match[1]);
            add(p.path(), "dds", reference);
          }
        }
      } else if (kind == 0x1aedda1f &&
                 fs::is_regular_file(folder / L"audio.wav"))
        add(folder / L"audio.wav", "pcm", ref);
      else if (kind == 0x61df2234 && fs::is_directory(folder / L"audio")) {
        std::regex pattern("track_([0-9]{5})");
        for (auto &p : fs::directory_iterator(folder / L"audio")) {
          std::smatch match;
          auto name = utf8(p.path().filename());
          if (p.is_directory() && std::regex_match(name, match, pattern) &&
              fs::is_regular_file(p.path() / L"audio.wav")) {
            auto reference = ref;
            reference["stream"] = std::stoul(match[1]);
            add(p.path() / L"audio.wav", "pcm", reference);
          }
        }
      }
    }
  return edits;
}
inline void validate_tree(const fs::path &root, Job &job) {
  std::vector<fs::path> todo{root / L"assets"};
  while (!todo.empty()) {
    job.check();
    auto current = todo.back();
    todo.pop_back();
    for (auto &e : fs::directory_iterator(current)) {
      auto attr = GetFileAttributesW(e.path().c_str());
      require(attr != INVALID_FILE_ATTRIBUTES &&
                  !(attr & FILE_ATTRIBUTE_REPARSE_POINT),
              "Linked paths are unsupported in loose assets");
      if (e.is_directory())
        todo.push_back(e.path());
    }
  }
}
inline J export_scene_textures(Folder &f, Job &job, bool named = false,
                               const std::string &only_bank = {}) {
  J catalog = J::array(), unsupported = J::array();
  auto marker = f.root / L"scene_textures.json";
  std::map<std::tuple<uint32_t, uint64_t, uint64_t>, J> previous;
  if (named && fs::exists(marker)) {
    auto old = json(marker);
    auto selected = [&](const J &source) {
      return only_bank.empty() ||
          f.entries.at(uint32_t(num(source.at("bank")))).at("folder").get<std::string>() == only_bank;
    };
    for (auto &scene : old.at("scenes")) {
      if (!selected(scene)) {
        catalog.push_back(scene);
        continue;
      }
      for (auto &t : scene.at("textures"))
        previous.emplace(std::tuple{uint32_t(num(scene.at("bank"))),
                   num(scene.at("record")), num(t.at("slot"))}, t);
    }
    for (auto &issue : old.at("unsupported"))
      if (!selected(issue.at("source")))
        unsupported.push_back(issue);
  }
  uint64_t done = 0;
  for (auto &[id, e] : f.entries) {
    if (done++ % 64 == 0)
      job.update(done, f.entries.size(), "Exporting editable Xbox DDS files...");
    job.check();
    auto bank = e.at("folder").get<std::string>();
    if (!only_bank.empty() && bank != only_bank)
      continue;
    for (auto &r : f.records(e)) {
      auto kind = uint32_t(num(r["type"]));
      bool scene = kind == 0xe26c9b5d;
      bool texture = kind == 0x5c369069 || kind == 0x5c36fb69;
      if (!scene && !(named && texture))
        continue;
      auto record = bank + "/" + r.at("folder").get<std::string>();
      if (texture && fs::is_regular_file(contained(f.root, record + "/texture.dds")))
        continue;
      auto files = f.scene_components(e, r);
      bool inline_pixels = texture && files.size() == 1;
      if (files.size() != 2 && !inline_pixels)
        continue;
      auto cpu = read(files[0]);
      if (cpu.size() < (scene ? 0x28 : 0xac))
        continue;
      uint64_t count = scene ? be(cpu, 0x20) : 1;
      if (!count)
        continue;
      auto index = num(r["index"]);
      auto source = J{{"bank", id}, {"record", index}};
      if (texture)
        source["kind"] = "txtr";
      uint64_t table = 0;
      if (scene)
        try {
          table = scene_texture_table(cpu, count);
        } catch (const std::exception &ex) {
          unsupported.push_back(J{{"source", source}, {"reason", ex.what()}});
          continue;
        }
      auto labels = named && scene ? scene_sampler_names(cpu)
                                   : std::map<uint32_t, SceneTextureLabel>{};
      std::map<uint32_t, unsigned> repeated;
      if (named && scene)
        for (uint64_t slot = 0; slot < count; ++slot)
          ++repeated[be(cpu, table + slot * 224)];
      Bytes gpu;
      bool loaded = false;
      J textures = J::array();
      for (uint64_t slot = 0; slot < count; ++slot) {
        job.check();
        Bytes descriptor;
        try {
          descriptor = scene ? sub(cpu, table + slot * 224, 224)
              : inline_pixels ? inline_texture_descriptor(cpu) : cpu;
        } catch (const std::exception &ex) {
          auto ref = source;
          ref["texture"] = slot;
          unsupported.push_back(J{{"source", ref}, {"reason", ex.what()}});
          continue;
        }
        auto texid = be(descriptor, 0);
        J info{{"id", texid},
               {"header_offset", scene ? table + slot * 224 : 0},
               {"xbox_format", be(descriptor, 0x98) & 63}};
        if (is_indexed_texture(descriptor))
          info["pixel_storage"] = "indexed-argb-palette";
        else if (num(info["xbox_format"]) == 0)
          info["explicit_format"] = be(descriptor, 8) & 63;
        auto relative = "assets/textures/scne/" + hex(id) + "/" +
                        decpad(index) + "/texture_" + decpad(slot) + ".dds";
        if (named) {
          std::string label;
          if (!scene)
            label = r.value("name", resource_label(r));
          else if (auto it = resource_names().find(texid); it != resource_names().end())
            label = it->second;
          else if (auto it = labels.find(texid); it != labels.end()) {
            const auto &usage = it->second;
            if (usage.meshes.size() == 1)
              label = *usage.meshes.begin() + "_";
            label += (usage.roles.size() == 1 ? *usage.roles.begin() : "texture") +
                     "_" + hex(texid);
          } else
            label = "texture_" + hex(texid);
          if (scene && repeated[texid] > 1)
            label += "_" + decpad(slot);
          bool support = false;
          if (scene) {
            auto it = labels.find(texid);
            auto fmt = num(info["xbox_format"]);
            support = fmt == 10 || fmt == 49 || fmt == 59 || fmt == 60 ||
                (it != labels.end() && !it->second.roles.contains("diffuse") &&
                                       !it->second.roles.contains("color"));
            support = court_texture_support(id, index, slot, texid, support);
            if (it != labels.end()) {
              info["roles"] = it->second.roles;
              info["geometry"] = it->second.meshes;
            }
            info["usage"] = support ? "support" : "artwork";
          }
          relative = record + (support ? "/_support/" : "/") + label + ".dds";
        }
        if (auto prior = previous.find({id, index, slot}); prior != previous.end()) {
          auto item = prior->second;
          if (item.contains("presentation_file")) {
            info.erase("usage");
            item.update(info);
            textures.push_back(std::move(item));
            continue;
          }
          if (item.at("file").get<std::string>() != relative)
            relocate_resource(contained(f.root, item.at("file")), contained(f.root, relative));
          item["file"] = relative;
          item.update(info);
          textures.push_back(std::move(item));
          continue;
        }
        if (!loaded && !inline_pixels) {
          gpu = read(files[1]);
          loaded = true;
        }
        Bytes dds;
        try {
          dds = export_resource_dds(descriptor, inline_pixels ? cpu : gpu);
        } catch (const std::exception &ex) {
          auto ref = source;
          ref["texture"] = slot;
          unsupported.push_back(J{{"source", ref}, {"reason", ex.what()}});
          continue;
        }
        publish(contained(f.root, relative), dds);
        info["slot"] = slot;
        info["file"] = relative;
        info["sha256"] = sha(dds);
        textures.push_back(std::move(info));
      }
      if (!textures.empty()) {
        source["textures"] = textures;
        catalog.push_back(source);
      }
    }
  }
  if (named && !previous.empty()) {
    auto tree = f.root / L"assets" / L"textures" / L"scne";
    if (fs::is_directory(tree)) {
      std::vector<fs::path> dirs{tree};
      for (auto &item : fs::recursive_directory_iterator(tree))
        if (item.is_directory())
          dirs.push_back(item.path());
      for (auto it = dirs.rbegin(); it != dirs.rend(); ++it)
        if (fs::is_empty(*it))
          fs::remove(*it);
      if (fs::is_empty(tree.parent_path()))
        fs::remove(tree.parent_path());
    }
  }
  jsonwrite(marker, J{{"version", 1}, {"scenes", catalog}, {"unsupported", unsupported}});
  return J{{"resources", catalog.size()}, {"unsupported", unsupported.size()}};
}

inline size_t apply_scene_textures(Folder &f, Job &job) {
  auto marker = f.root / L"scene_textures.json";
  if (!fs::exists(marker))
    return 0;
  auto catalog = json(marker);
  require(catalog.at("version") == 1, "Unsupported scene DDS catalog");
  size_t edited = 0;
  for (auto &scene : catalog.at("scenes")) {
    job.check();
    std::map<uint64_t, Bytes> edits;
    for (auto &item : scene.at("textures")) {
      auto file = contained(f.root, item.at("file"));
      auto dds = read(file, 128ull << 20);
      if (sha(dds) != item.at("sha256").get<std::string>())
        require(edits.emplace(num(item.at("slot")), std::move(dds)).second,
                "Duplicate scene DDS slot");
    }
    if (edits.empty())
      continue;
    auto &e = f.entries.at(uint32_t(num(scene.at("bank"))));
    auto records = f.records(e);
    auto record = std::find_if(records.begin(), records.end(), [&](auto &r) {
      return r.at("index") == scene.at("record");
    });
    bool scene_texture = scene.value("kind", std::string()) != "txtr";
    require(record != records.end(), "Missing DDS resource owner");
    auto type = num(record->at("type"));
    require(scene_texture ? type == 0xe26c9b5d :
                (type == 0x5c369069 || type == 0x5c36fb69),
            "DDS resource type differs from the catalog");
    auto files = f.scene_components(e, *record);
    bool inline_pixels = !scene_texture && files.size() == 1;
    require(files.size() == 2 || inline_pixels, "Missing DDS resource components");
    for (auto &other : records) {
      if (other.at("index") == record->at("index"))
        continue;
      auto shared = f.scene_components(e, other);
      require(std::find(shared.begin(), shared.end(), files.back()) == shared.end(),
              "Scene DDS component is shared with another resource");
    }
    auto cpu = read(files.front()), gpu = inline_pixels ? cpu : read(files.back());
    const auto original = gpu;
    uint64_t count = scene_texture ? be(cpu, 0x20) : 1;
    uint64_t table = scene_texture ? scene_texture_table(cpu, count) : 0;
    for (auto &[slot, dds] : edits) {
      require(slot < count, "Missing scene DDS slot");
      auto descriptor = scene_texture ? sub(cpu, table + slot * 224, 224)
          : inline_pixels ? inline_texture_descriptor(cpu) : cpu;
      replace_resource_dds(descriptor, dds, gpu);
    }
    for (uint64_t slot = 0; slot < count; ++slot) {
      auto descriptor = scene_texture ? sub(cpu, table + slot * 224, 224)
          : inline_pixels ? inline_texture_descriptor(cpu) : cpu;
      if (auto it = edits.find(slot); it != edits.end()) {
        auto actual = export_resource_dds(descriptor, gpu);
        auto header = le(actual, 84) == 0x30315844 ? 148 : 128;
        require(std::equal(actual.begin() + header, actual.end(),
                           it->second.begin() + header),
                "Conflicting shared scene DDS pixels");
      } else {
        // Verify the full source extent, including unsupported formats/mips.
        int64_t start = int64_t(be(descriptor, 0x6c)) - 1;
        auto length = be(descriptor, 0x70);
        if (!length)
          continue;
        require(start >= 0, "Invalid neighboring scene texture offset");
        bounds(gpu, start, length);
        require(std::equal(gpu.begin() + start, gpu.begin() + start + length,
                           original.begin() + start),
                "Scene DDS edit overlaps a neighboring texture");
      }
    }
    auto file = f.root / L"_runtime" / L"scene-textures" / path(sha(gpu) + ".dat");
    publish(file, gpu);
    require(f.component_overrides.emplace(files.back(), file).second,
            "Scene DDS component has multiple owners");
    edited += edits.size();
  }
  return edited;
}

inline J prepare(const fs::path &source, Job &job) {
  auto root = longpath(fs::canonical(longpath(source)));
  validate_tree(root, job);
  auto original = json(root / L"assets.json");
  materialize(root, original, job, true);
  Folder f(root);
  std::vector<std::string> dds_rows, pcm_rows;
  std::map<std::string, std::string> identities;
  std::set<std::string> known;
  auto key = [](unsigned w, unsigned h, unsigned fmt, std::string hash) {
    return std::to_string(w) + "\t" + std::to_string(h) + "\t" +
           std::to_string(fmt) + "\t" + hash;
  };
  auto identity = [&](std::string k, std::string digest) {
    auto it = identities.find(k);
    require(it == identities.end() || it->second == digest,
            "Conflicting native DDS identities");
    bool fresh = it == identities.end();
    identities[k] = digest;
    return fresh;
  };
  for (auto &[id, e] : f.entries) {
    job.check();
    const auto &l = f.layout(e);
    for (auto &t : l.value("textures", J::array())) {
      std::string relative =
          e["folder"].get<std::string>() + "/" + t["path"].get<std::string>();
      auto file = contained(root, relative);
      auto d = read(file, 128ull << 20);
      auto digest = sha(d);
      auto info = t["descriptor"];
      auto k =
          key(unsigned(num(info["width"])), unsigned(num(info["height"])),
              unsigned(num(info["format"])), t["identity"].get<std::string>());
      known.insert(lower(relative));
      if (digest != t["sha256"].get<std::string>()) {
        J index;
        if (t.contains("record"))
          index = t["record"];
        else {
          unsigned n = 0;
          for (auto &r : l.at("records"))
            if (t["path"] == r["folder"].get<std::string>() + "/texture.dds") {
              index = r["index"];
              ++n;
            }
          require(n == 1, "Ambiguous DDS resource folder");
        }
        auto [kind, blocks] = f.blocks(J{{"bank", id}, {"record", index}});
        require(!blocks.empty() && blocks.size() <= 2,
                "Invalid native texture components");
        auto orig =
            export_dds(blocks[0], blocks.size() == 2 ? &blocks[1] : nullptr);
        auto desc =
            describe(blocks[0], blocks.size() == 2 ? &blocks[1] : nullptr);
        validate_dds(d, desc.width, desc.height, desc.format);
        k = key(desc.width, desc.height, desc.format,
                hex(fnv(std::span(orig).subspan(128)), 16));
      }
      if (identity(k, digest) && digest != t["sha256"].get<std::string>())
        dds_rows.push_back(k + "\t" + relative);
    }
  }
  auto marker = root / L"asset_edits.json";
  auto reg = fs::exists(marker) ? json(marker)
                                : J{{"version", 1}, {"platform", "xbox360"}};
  require(reg.value("version", 0) == 1 &&
              reg.value("platform", std::string()) == "xbox360",
          "Unsupported native edits registry");
  auto edits = reg.value("edits", J::array());
  for (auto &edit : discover(f))
    edits.push_back(edit);
  std::map<std::string, std::string> audio_seen;
  for (auto &edit : edits) {
    job.check();
    std::string relative = edit.at("file");
    if (!known.insert(lower(relative)).second)
      continue;
    auto file = contained(root, relative);
    auto rel = file.lexically_relative(root / L"assets");
    require(!rel.empty() && *rel.begin() != "..", "Edit path escapes assets");
    auto [kind, blocks] = f.blocks(edit.at("source"));
    if (edit["kind"] == "dds") {
      require((kind == 0x5c369069 || kind == 0x5c36fb69) &&
                  blocks.size() >= 1 && blocks.size() <= 2,
              "DDS target is not a texture");
      auto d = read(file, 128ull << 20),
           orig =
               export_dds(blocks[0], blocks.size() == 2 ? &blocks[1] : nullptr);
      auto info =
          describe(blocks[0], blocks.size() == 2 ? &blocks[1] : nullptr);
      validate_dds(d, info.width, info.height, info.format);
      auto k = key(info.width, info.height, info.format,
                   hex(fnv(std::span(orig).subspan(128)), 16));
      if (identity(k, sha(d)) && d != orig)
        dds_rows.push_back(k + "\t" + relative);
    } else if (edit["kind"] == "pcm") {
      require(kind == 0x1aedda1f && blocks.size() == 2 &&
                  blocks[0].size() == 44,
              "PCM target is not Xbox audio");
      auto &b = blocks[0];
      auto fmt = be(b, 8), samples = be(b, 12), rate = be(b, 16),
           size = be(b, 24);
      require(be(b, 0) == 1 && be(b, 4) == 5 && (fmt == 2 || fmt == 5) &&
                  size > 0 && size <= blocks[1].size() && size % 2048 == 0,
              "Unsupported Xbox audio source");
      auto channels = fmt == 2 ? 1 : 2;
      auto wave = read(file, 512ull << 20);
      auto info = wave_info(wave);
      require(num(info["channels"]) == uint64_t(channels) &&
                  num(info["rate"]) == rate && num(info["samples"]) == samples,
              "PCM WAV must retain original channels, rate and sample count");
      auto prefix = std::min(size, 16384u);
      std::string k = hex(fnv(std::span(blocks[1]).first(2048)), 16) + "\t" +
                      std::to_string(prefix) + "\t" +
                      hex(fnv(std::span(blocks[1]).first(prefix)), 16) + "\t" +
                      std::to_string(channels);
      auto digest = sha(wave);
      auto it = audio_seen.find(k);
      require(it == audio_seen.end() || it->second == digest,
              "Conflicting native WAV identities");
      if (it == audio_seen.end())
        pcm_rows.push_back(k + "\t" + std::to_string(rate) + "\t" +
                           std::to_string(samples) + "\t" + relative);
      audio_seen[k] = digest;
    } else
      throw std::runtime_error("Unsupported native edit kind");
  }
  auto scene_edits = apply_scene_textures(f, job);
  auto plan = f.plan(job);
  std::string map = "CH2K8_LOOSE_V1\n";
  for (auto &p : plan["parts"])
    map += "P\t" + std::to_string(num(p["offset"])) + "\t" +
           std::to_string(num(p["size"])) + "\t" +
           p["name"].get<std::string>() + "\n";
  uint64_t cursor = 0;
  for (auto &s : plan["segments"]) {
    auto n = num(s["size"]);
    std::string name = s["path"];
    require(n && num(s["offset"]) == cursor &&
                name.find_first_of("\t\r\n") == std::string::npos &&
                fs::file_size(contained(root, name)) == n,
            "Invalid scatter-map coverage or file size");
    map += "S\t" + std::to_string(cursor) + "\t" + std::to_string(n) + "\t" +
           name + "\n";
    cursor += n;
  }
  require(cursor == num(plan["total"]),
          "Scatter map does not cover virtual archive");
  auto catalog = [](std::string header, const std::vector<std::string> &rows) {
    header += '\n';
    for (size_t i = 0; i < rows.size(); ++i) {
      if (i)
        header += '\n';
      header += rows[i];
    }
    return header + '\n';
  };
  job.check();
  text(root / L"native_dds.index", catalog("CH2K8_DDS_V1", dds_rows));
  text(root / L"native_audio.index", catalog("CH2K8_PCM_V1", pcm_rows));
  text(root / L"assets.map", map);
  return J{{"ready", true},
           {"banks", f.entries.size()},
           {"parts", plan["parts"].size()},
           {"dds_bindings", dds_rows.size()},
           {"scene_dds_edits", scene_edits},
           {"pcm_bindings", pcm_rows.size()}};
}
