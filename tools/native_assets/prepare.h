#pragma once
#include "folder.h"
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
           {"pcm_bindings", pcm_rows.size()}};
}
