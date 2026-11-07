#pragma once
#include "import_layout.h"
inline J augment(const fs::path &root, J m) {
  auto marker = root / L"asset_edits.json";
  J reg = fs::exists(marker) ? json(marker)
                             : J{{"version", 1}, {"platform", "xbox360"}};
  require(reg.value("version", 0) == 1 &&
              reg.value("platform", std::string()) == "xbox360",
          "Invalid native asset registry");
  std::map<uint32_t, J> known;
  std::set<uint32_t> occupied;
  uint64_t maxindex = 0, end = num(m["total"]);
  for (auto &e : m["entries"]) {
    known[uint32_t(num(e["hash"]))] = e;
    occupied.insert(uint32_t(num(e["hash"])));
    maxindex = std::max(maxindex, num(e["index"]));
  }
  for (auto &spec : reg.value("banks", J::array())) {
    std::string name = spec.at("name");
    require(
        std::regex_match(name, std::regex("(?:sel)?u[haxyz][0-9]{3,4}\\.iff")),
        "Unsupported new Xbox uniform filename");
    auto id = crc(name);
    require(occupied.insert(id).second, "Duplicate Xbox asset identity");
    auto t = known.find(uint32_t(num(spec.at("template"))));
    require(t != known.end(), "Missing uniform template");
    require(spec.at("folder") == "assets/" + name,
            "New uniform folder/name mismatch");
    auto f = contained(root, spec.at("folder"));
    require(f.parent_path() == root / L"assets" &&
                json(f / L"asset.json").contains("blocks"),
            "New uniform needs standard Xbox components");
    auto e = t->second;
    e["index"] = ++maxindex;
    e["hash"] = id;
    e["folder"] = spec["folder"];
    e["offset"] = end;
    e["added"] = true;
    e["template_hash"] = t->first;
    m["entries"].push_back(e);
    end += align(num(t->second["size"]), 2048);
  }
  std::set<std::string> folders;
  for (auto &e : m["entries"])
    folders.insert(e["folder"]);
  std::vector<fs::path> ordered;
  for (auto &f : fs::directory_iterator(root / L"assets"))
    if (f.is_directory())
      ordered.push_back(f.path());
  std::sort(ordered.begin(), ordered.end());
  for (auto &f : ordered) {
    std::string relative = "assets/" + utf8(f.filename());
    if (folders.contains(relative) || !fs::exists(f / L"asset.json"))
      continue;
    auto layout = json(contained(root, relative + "/asset.json"));
    if (!layout.contains("identity"))
      continue;
    auto spec = layout["identity"];
    std::string name = spec.at("name");
    require(name == utf8(f.filename()) &&
                std::regex_match(name, std::regex("[a-z0-9_]{1,48}\\.iff")),
            "Invalid loose bank identity");
    auto id = crc(name);
    require(id == num(spec["hash"]) && occupied.insert(id).second,
            "Duplicate or incorrect loose bank identity");
    uint64_t size = num(spec["source_size"]), flags = num(spec["toc_flags"]);
    require(layout.contains("blocks") && num(layout["length"]) <= size &&
                size <= 512ull << 20 && flags <= UINT32_MAX,
            "Invalid loose bank metadata");
    J e{{"index", ++maxindex},
        {"hash", id},
        {"folder", relative},
        {"offset", end},
        {"size", size},
        {"added", true},
        {"toc_flags", flags},
        {"sha256", spec.value("source_sha256", std::string())}};
    if (spec.contains("template_hash"))
      e["template_hash"] = spec["template_hash"];
    m["entries"].push_back(e);
    end += align(size, 2048);
  }
  return m;
}
struct Folder {
  fs::path root;
  J manifest, compat;
  std::map<uint32_t, J> layouts, entries;
  explicit Folder(fs::path r)
      : root(longpath(fs::canonical(longpath(r)))),
        manifest(json(root / L"assets.json")) {
    require(manifest.value("version", 0) == 1 &&
                manifest.value("platform", std::string()) == "xbox360",
            "Unsupported asset installation");
    if (manifest.contains("loader_metadata"))
      compat = manifest["loader_metadata"];
    else if (fs::exists(longpath(root / L"_runtime/compatibility.json")))
      compat = json(root / L"_runtime/compatibility.json");
    else {
      require(manifest.contains("parts") && manifest.contains("segments"),
              "Missing loader compatibility metadata");
      J first;
      for (auto &s : manifest["segments"])
        if (num(s["offset"]) == 0) {
          first = s;
          break;
        }
      require(!first.is_null(), "Missing loader header");
      auto h = read(contained(root, first["path"]));
      auto n = manifest["parts"].size();
      bounds(h, 0, 24 + 16 * (n + manifest["entries"].size()));
      J words = J::array(), flags = J::object(), pf = J::array();
      for (int i = 0; i < 6; ++i)
        words.push_back(be(h, i * 4));
      for (size_t i = 0; i < n; ++i)
        pf.push_back(be(h, 24 + i * 16 + 4));
      for (auto &e : manifest["entries"])
        flags[std::to_string(num(e["hash"]))] =
            be(h, 24 + n * 16 + num(e["index"]) * 16 + 8);
      compat = {
          {"version", 1},     {"platform", "xbox360"},
          {"header", words},  {"toc_flags", flags},
          {"part_flags", pf}, {"part_size", manifest["parts"][0]["size"]}};
      jsonwrite(root / L"_runtime/compatibility.json", compat);
    }
    manifest = augment(root, manifest);
    for (auto &e : manifest["entries"]) {
      require(entries.emplace(uint32_t(num(e["hash"])), e).second,
              "Duplicate asset identity");
    }
  }
  const J &layout(const J &e) {
    auto id = uint32_t(num(e["hash"]));
    if (!layouts.contains(id)) {
      auto f = contained(root, e["folder"]);
      require(f.parent_path() == root / L"assets",
              "Loose bank lies outside assets");
      layouts[id] = json(f / L"asset.json");
    }
    return layouts.at(id);
  }
  J records(const J &e) {
    const auto &l = layout(e);
    if (l.contains("paired_resources"))
      return l["paired_resources"];
    if (l.contains("blocks"))
      return l["records"];
    return J::array();
  }
  std::pair<uint32_t, std::vector<Bytes>> blocks(const J &ref) {
    auto it = entries.find(uint32_t(num(ref.at("bank"))));
    require(it != entries.end(), "Native edit refers to missing bank");
    auto &e = it->second;
    const auto &l = layout(e);
    auto index = num(ref.at("record"));
    require(index < 100000, "Resource index exceeds limit");
    J rec;
    auto rs = records(e);
    for (auto &r : rs)
      if (num(r["index"]) == index) {
        rec = r;
        break;
      }
    require(!rec.is_null(), "Native edit refers to missing resource");
    uint32_t kind = uint32_t(num(rec["type"]));
    std::vector<Bytes> data;
    if (l.contains("paired_resources")) {
      for (auto &c : rec["component_files"]) {
        Bytes b;
        if (!c["path"].is_null())
          b = read(contained(root, c["folder"].get<std::string>() + "/" +
                                       c["path"].get<std::string>()));
        require(b.size() == num(c["size"]),
                "Loose paired component extent changed");
        data.push_back(std::move(b));
      }
    } else {
      for (size_t j = 0; j < rec["offsets"].size(); ++j) {
        auto start = num(rec["offsets"][j]);
        if (start == 0xffffffff)
          continue;
        require(j < l["blocks"].size(), "Invalid record block index");
        bool found = false;
        for (auto &c : l["blocks"][j]["components"])
          if (num(c["start"]) == start) {
            data.push_back(
                read(contained(root, e["folder"].get<std::string>() + "/" +
                                         c["path"].get<std::string>())));
            found = true;
            break;
          }
        require(found, "Missing loose record component");
      }
    }
    if (ref.contains("stream")) {
      require(kind == 0x61df2234 && !data.empty(), "Not an Xbox stream table");
      const auto &b = data[0];
      std::string name = utf16be(b, 0, 64);
      auto paired = entries.find(crc(name));
      require(paired != entries.end(), "Missing stream data bank");
      auto stream = num(ref["stream"]);
      auto count = be(b, 64), rate = be(b, 76), fmt = be(b, 84);
      require(stream < count && (fmt == 2 || fmt == 5),
              "Unsupported Xbox stream slot");
      auto start = be(b, 92 + stream * 8), end = be(b, 100 + stream * 8);
      uint32_t bits = be(b, 96 + stream * 8);
      float seconds = std::bit_cast<float>(bits);
      auto filename = contained(
          root, paired->second["folder"].get<std::string>() + "/payload.dat");
      require(start < end && end <= fs::file_size(filename),
              "Stream data exceeds bank");
      std::ifstream f(filename, std::ios::binary);
      f.seekg(start);
      Bytes encoded(end - start);
      f.read(reinterpret_cast<char *>(encoded.data()), encoded.size());
      require(size_t(f.gcount()) == encoded.size(), "Short stream read");
      Bytes desc(44);
      require(std::isfinite(seconds) && seconds >= 0 &&
                  double(seconds) * rate <= UINT32_MAX,
              "Invalid stream sample count");
      std::array<uint32_t, 11> w{
          1,
          5,
          fmt,
          uint32_t(std::nearbyint(double(seconds) * rate)),
          rate,
          0,
          uint32_t(encoded.size()),
          0,
          32,
          0,
          0};
      for (size_t i = 0; i < w.size(); ++i)
        put(desc, i * 4, w[i]);
      data = {desc, encoded};
      kind = 0x1aedda1f;
    }
    if (ref.contains("texture")) {
      require(kind == 0xe26c9b5d && data.size() == 2,
              "Not a split Xbox scene texture");
      auto slot = num(ref["texture"]), count = uint64_t(be(data[0], 0x20)),
           table = 0x24ull + be(data[0], 0x24) - 1;
      require(slot < count && table <= data[0].size() &&
                  count * 224 <= data[0].size() - table,
              "Scene texture exceeds descriptor table");
      data[0] = sub(data[0], table + slot * 224, 224);
      kind = 0x5c369069;
    }
    return {kind, std::move(data)};
  }
  J zero(uint64_t n) {
    std::string relative = "_runtime/padding/" + std::to_string(n) + ".pad";
    if (n)
      publish(root / path(relative), Bytes(n));
    return J{{"size", n}, {"path", relative}};
  }
  J bank(const J &e) {
    auto folder = contained(root, e["folder"]);
    const auto &l = layout(e);
    bool committed = true;
    if (l.contains("paired_owner")) {
      auto owner = contained(root, l["paired_owner"]);
      require(owner.parent_path() == root / L"assets",
              "Paired owner escapes assets");
      committed = json(owner / L"asset.json").contains("paired_resources");
    }
    if (l.contains("loose_segments") && committed) {
      J segments = J::array();
      uint64_t cursor = 0;
      for (auto &s : l["loose_segments"]) {
        auto file = contained(folder, s["path"]);
        auto n = fs::file_size(file);
        require(num(s["offset"]) == cursor && num(s["size"]) == n,
                "Loose paired component extent changed");
        if (n)
          segments.push_back(J{{"offset", cursor},
                               {"size", n},
                               {"path", utf8(file.lexically_relative(root))}});
        cursor += n;
      }
      require(cursor == num(l["loose_size"]),
              "Incomplete paired component mapping");
      return J{{"size", cursor}, {"segments", segments}};
    }
    if (!l.contains("blocks")) {
      std::string relative = e["folder"].get<std::string>() + "/payload.dat";
      auto n = fs::file_size(contained(root, relative));
      J segments = J::array();
      if (n)
        segments.push_back(J{{"offset", 0}, {"size", n}, {"path", relative}});
      return J{{"size", n}, {"segments", segments}};
    }
    auto pieces = l["pieces"];
    std::sort(pieces.begin(), pieces.end(), [](auto &a, auto &b) {
      return num(a["offset"]) < num(b["offset"]);
    });
    require(!pieces.empty() && num(pieces[0]["offset"]) == 0,
            "Missing loose bank header");
    auto header = read(contained(folder, pieces[0]["path"]));
    require(header.size() == num(pieces[0]["size"]) &&
                header.size() >= num(l["header"]) &&
                be(header, 0) == 0xff3bef94 &&
                be(header, 16) == l["blocks"].size(),
            "Invalid loose bank header metadata");
    std::map<std::string, J> bs;
    for (auto &b : l["blocks"])
      bs[b["path"]] = b;
    J seg = J::array();
    uint64_t cursor = 0;
    std::string pending = "_runtime/pending.header";
    for (auto &p : pieces) {
      auto it = bs.find(p["path"].get<std::string>());
      if (it != bs.end()) {
        const auto &b = it->second;
        auto alignment = num(b["start"]) % 4096 == 0 ? 4096
                         : num(b["start"]) % 16 == 0 ? 16
                                                     : 1;
        auto padding = align(cursor, alignment) - cursor;
        if (padding) {
          auto z = zero(padding);
          z["offset"] = cursor;
          seg.push_back(z);
          cursor += padding;
        }
        uint64_t start = cursor, logical = 0;
        auto cs = b["components"];
        std::sort(cs.begin(), cs.end(), [](auto &a, auto &b) {
          return num(a["start"]) < num(b["start"]);
        });
        for (auto &c : cs) {
          require(num(c["start"]) == logical, "Loose component gap or overlap");
          auto f = contained(folder, c["path"]);
          auto n = fs::file_size(f), old = num(c["end"]) - num(c["start"]);
          if (n != old) {
            bool roster = l["records"].size() == 1 &&
                          num(l["records"][0]["type"]) == 0xc61649b2 &&
                          cs.size() == 1 && num(c["start"]) == 0 &&
                          num(c["end"]) == num(b["logical"]);
            require(roster && n >= old && n % 2 == 0 && n <= 64ull << 20,
                    "Unsupported loose resource resizing");
          }
          if (n)
            seg.push_back(J{{"offset", cursor},
                            {"size", n},
                            {"path", utf8(f.lexically_relative(root))}});
          cursor += n;
          logical = num(c["end"]);
        }
        require(logical == num(b["logical"]) && cursor <= UINT32_MAX,
                "Incomplete or oversized loose block");
        auto o = 32 + num(b["index"]) * 32;
        put(header, o + 12, cursor - start);
        put(header, o + 20, start);
        put(header, o + 24, cursor - start);
      } else {
        bool first = num(p["offset"]) == 0;
        auto n = num(p["size"]);
        if (!first)
          require(fs::file_size(contained(folder, p["path"])) == n,
                  "Loose metadata/padding size changed");
        if (n)
          seg.push_back(
              J{{"offset", cursor},
                {"size", n},
                {"path", first ? pending
                               : e["folder"].get<std::string>() + "/" +
                                     p["path"].get<std::string>()}});
        cursor += n;
      }
    }
    auto length =
        int64_t(num(l["length"])) + int64_t(cursor) - int64_t(num(e["size"]));
    require(length >= 0 && length <= UINT32_MAX, "Invalid loose bank length");
    put(header, 8, length);
    std::string final = "_runtime/headers/" + hex(num(e["hash"])) + "_" +
                        sha(header) + ".header";
    publish(root / path(final), header);
    seg[0]["path"] = final;
    return J{{"size", cursor}, {"segments", seg}};
  }
  J plan(Job &job) {
    std::vector<std::pair<J, J>> views;
    uint64_t done = 0;
    for (auto &e : manifest["entries"]) {
      job.update(done++, manifest["entries"].size(),
                 "Validating native loose resource maps...");
      views.push_back({e, bank(e)});
    }
    uint64_t partsize = num(compat["part_size"]);
    require(partsize && partsize % 2048 == 0,
            "Invalid virtual loader part size");
    uint64_t count = 1, total = 0;
    bool converged = false;
    for (int i = 0; i < 8; ++i) {
      uint64_t cursor = align(24 + count * 16 + views.size() * 16, 2048);
      for (auto &v : views)
        cursor = align(cursor + num(v.second["size"]), 2048);
      auto n = std::max(1ull, (cursor + partsize - 1) / partsize);
      if (n == count) {
        total = cursor;
        converged = true;
        break;
      }
      count = n;
    }
    require(converged && count <= 26,
            "Loose resources exceed virtual loader capacity");
    J parts = J::array();
    for (uint64_t i = 0; i < count; ++i)
      parts.push_back(J{{"name", "0" + std::string(1, char('A' + i))},
                        {"offset", i * partsize},
                        {"size", std::min(partsize, total - i * partsize)}});
    Bytes header(24 + count * 16 + views.size() * 16);
    require(compat["header"].size() == 6, "Invalid compatibility header");
    for (unsigned i = 0; i < 6; ++i)
      put(header, i * 4, num(compat["header"][i]));
    put(header, 8, count);
    put(header, 16, views.size());
    for (uint64_t i = 0; i < count; ++i) {
      auto flags = compat.value("part_flags", J::array());
      uint64_t flag = flags.empty() ? 0 : num(flags[i < flags.size() ? i : 0]);
      put(header, 24 + i * 16, num(parts[i]["size"]) / 2048);
      put(header, 28 + i * 16, flag);
      header[24 + i * 16 + 9] = '0';
      header[24 + i * 16 + 11] = uint8_t('A' + i);
    }
    auto prefix = 24 + count * 16;
    J seg = J::array({J{{"offset", 0},
                        {"size", header.size()},
                        {"path", "_runtime/pending.header"}}});
    uint64_t cursor = header.size();
    auto pad = [&]() {
      auto n = align(cursor, 2048) - cursor;
      if (n) {
        auto z = zero(n);
        z["offset"] = cursor;
        seg.push_back(z);
        cursor += n;
      }
    };
    pad();
    std::map<uint32_t, std::pair<uint64_t, uint64_t>> positions;
    for (auto &[e, v] : views) {
      positions[uint32_t(num(e["hash"]))] = {cursor, num(v["size"])};
      for (auto s : v["segments"]) {
        s["offset"] = cursor + num(s["offset"]);
        seg.push_back(s);
      }
      cursor += num(v["size"]);
      pad();
    }
    std::sort(views.begin(), views.end(), [](auto &a, auto &b) {
      return num(a.first["hash"]) < num(b.first["hash"]);
    });
    for (size_t i = 0; i < views.size(); ++i) {
      auto &e = views[i].first;
      auto id = uint32_t(num(e["hash"]));
      auto [pos, size] = positions.at(id);
      auto templ = std::to_string(
          num(e.contains("template_hash") ? e["template_hash"] : e["hash"]));
      auto flag = num(e.contains("toc_flags") ? e["toc_flags"]
                                              : compat["toc_flags"].at(templ));
      require(size <= UINT32_MAX && pos / 2048 <= UINT32_MAX,
              "Virtual bank exceeds loader limits");
      put(header, prefix + i * 16, id);
      put(header, prefix + i * 16 + 4, pos / 2048);
      put(header, prefix + i * 16 + 8, flag);
      put(header, prefix + i * 16 + 12, size);
    }
    require(cursor == total, "Direct resource coverage mismatch");
    std::string file = "_runtime/catalog_" + sha(header) + ".header";
    publish(root / path(file), header);
    seg[0]["path"] = file;
    return J{{"parts", parts},
             {"segments", seg},
             {"total", total},
             {"mode", "direct-resources"}};
  }
};
