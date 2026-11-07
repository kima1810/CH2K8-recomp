#pragma once
#include "codec.h"
inline std::string extension(uint32_t type) {
  switch (type) {
  case 0x5c369069:
    return "txtr";
  case 0xe26c9b5d:
    return "scne";
  case 0x86a1ac9e:
    return "layt";
  case 0xc61649b2:
    return "rost";
  case 0x68b693b2:
    return "name";
  case 0xa7701f00:
    return "cdan";
  case 0x1aedda1f:
    return "audo";
  }
  return hex(type);
}
inline J explode(const Bytes &data, const fs::path &folder,
                 bool textures = true) {
  J layout = {{"pieces", J::array()}, {"textures", J::array()}};
  auto piece = [&](uint64_t start, uint64_t end, std::string name,
                   bool emit = true) {
    require(start <= end && end <= data.size(), "Invalid IFF piece extent");
    if (end > start) {
      if (emit)
        write(folder / path(name), sub(data, start, end - start));
      layout["pieces"].push_back(
          J{{"offset", start}, {"size", end - start}, {"path", name}});
    }
  };
  if (data.size() < 32 || be(data, 0) != 0xff3bef94) {
    write(folder / L"payload.dat", data);
    if (!data.empty())
      layout["pieces"].push_back(
          J{{"offset", 0}, {"size", data.size()}, {"path", "payload.dat"}});
    return layout;
  }
  uint64_t header = be(data, 4), length = be(data, 8), bc = be(data, 16),
           rc = be(data, 24), table = 28ull + be(data, 28) - 1;
  require(header >= 32 && header <= length && length <= data.size() &&
              bc <= 100000 && rc <= 100000 && 32 + bc * 32 <= header &&
              table >= 32 + bc * 32 && table + rc * 4 <= header,
          "Invalid IFF boundaries");
  layout["header"] = header;
  layout["length"] = length;
  layout["blocks"] = J::array();
  layout["records"] = J::array();
  layout["unsupported_textures"] = J::array();
  for (uint64_t i = 0; i < bc; ++i) {
    uint64_t o = 32 + i * 32, start = be(data, o + 20), size = be(data, o + 24);
    require(start >= header && start <= length && size <= length - start,
            "Invalid IFF block");
    layout["blocks"].push_back(J{{"index", i},
                                 {"start", start},
                                 {"size", size},
                                 {"logical", be(data, o + 12)}});
  }
  for (uint64_t i = 0; i < rc; ++i) {
    uint64_t field = table + i * 4, off = field + be(data, field) - 1;
    require(off >= table + rc * 4 && off + 12 <= header, "Invalid IFF record");
    uint64_t count = be(data, off + 8);
    require(count <= bc && off + 12 + 4 * count <= header,
            "Invalid IFF record offsets");
    J offsets = J::array();
    for (uint64_t j = 0; j < count; ++j) {
      auto v = be(data, off + 12 + j * 4);
      require(v == 0xffffffff || v <= num(layout["blocks"][j]["logical"]),
              "IFF record exceeds decoded block");
      offsets.push_back(v);
    }
    layout["records"].push_back(J{{"index", i},
                                  {"id", be(data, off)},
                                  {"type", be(data, off + 4)},
                                  {"offsets", offsets}});
  }
  auto ordered = layout["blocks"];
  std::sort(ordered.begin(), ordered.end(),
            [](auto &a, auto &b) { return num(a["start"]) < num(b["start"]); });
  uint64_t cursor = 0;
  for (auto &block : ordered) {
    auto start = num(block["start"]), size = num(block["size"]);
    require(start >= cursor, "Overlapping IFF blocks");
    piece(cursor, start, "gap_" + hex(cursor) + ".dat");
    std::string name = "block_" + decpad(num(block["index"]), 2) + ".stored";
    layout["blocks"][num(block["index"])]["path"] = name;
    piece(start, start + size, name, false);
    cursor = start + size;
  }
  piece(cursor, data.size(), "tail.dat");
  std::vector<Bytes> decoded;
  for (auto &block : layout["blocks"]) {
    auto j = num(block["index"]);
    decoded.push_back(decode(sub(data, num(block["start"]), num(block["size"])),
                             512ull << 20, num(block["logical"])));
    block["components"] = J::array();
    std::set<uint64_t> offsets{0, num(block["logical"])};
    for (auto &r : layout["records"])
      if (r["offsets"].size() > j && num(r["offsets"][j]) != 0xffffffff)
        offsets.insert(num(r["offsets"][j]));
    for (auto it = offsets.begin(); it != offsets.end(); ++it) {
      auto next = std::next(it);
      if (next == offsets.end())
        break;
      std::string name = "_unclaimed";
      for (auto &r : layout["records"])
        if (r["offsets"].size() > j && num(r["offsets"][j]) == *it) {
          name = decpad(num(r["index"])) + "_" + hex(num(r["id"])) + "." +
                 extension(uint32_t(num(r["type"])));
          break;
        }
      std::string relative = name + "/block" + std::to_string(j) + ".dat";
      auto value = sub(decoded[j], *it, *next - *it);
      write(folder / path(relative), value);
      block["components"].push_back(J{{"start", *it},
                                      {"end", *next},
                                      {"path", relative},
                                      {"sha256", sha(value)}});
    }
  }
  for (auto &r : layout["records"]) {
    std::string name = decpad(num(r["index"])) + "_" + hex(num(r["id"])) + "." +
                       extension(uint32_t(num(r["type"])));
    r["folder"] = name;
    fs::create_directories(folder / path(name));
    jsonwrite(folder / path(name) / L"record.json", r);
    if (!textures || num(r["type"]) != 0x5c369069)
      continue;
    try {
      std::vector<Bytes> spans;
      uint64_t firstj = 0, firststart = 0, firstend = 0;
      for (size_t j = 0; j < r["offsets"].size(); ++j) {
        auto start = num(r["offsets"][j]);
        if (start == 0xffffffff)
          continue;
        uint64_t end = num(layout["blocks"][j]["logical"]);
        for (auto &other : layout["records"])
          if (other["offsets"].size() > j) {
            auto n = num(other["offsets"][j]);
            if (n != 0xffffffff && n > start)
              end = std::min(end, n);
          }
        if (spans.empty()) {
          firstj = j;
          firststart = start;
          firstend = end;
        }
        spans.push_back(sub(decoded[j], start, end - start));
      }
      require(spans.size() == 1 || spans.size() == 2,
              "Unsupported TXTR component count");
      auto dds = export_dds(spans[0], spans.size() == 2 ? &spans[1] : nullptr);
      auto info = describe(spans[0], spans.size() == 2 ? &spans[1] : nullptr);
      std::string relative = name + "/texture.dds";
      write(folder / path(relative), dds);
      layout["textures"].push_back(
          J{{"path", relative},
            {"sha256", sha(dds)},
            {"block", firstj},
            {"start", firststart},
            {"end", firstend},
            {"identity", hex(fnv(std::span(dds).subspan(128)), 16)},
            {"descriptor", tex_json(info)}});
    } catch (const std::exception &e) {
      layout["unsupported_textures"].push_back(
          J{{"record", r["index"]}, {"reason", e.what()}});
    }
  }
  return layout;
}
inline void materialize(const fs::path &root, J &manifest, Job &job,
                        bool keep_originals = true) {
  std::map<uint32_t, J> entries;
  for (auto &e : manifest["entries"])
    entries[uint32_t(num(e["hash"]))] = e;
  for (auto &[identity, entry] : entries) {
    job.check();
    auto folder = contained(root, entry["folder"]),
         meta = folder / L"asset.json";
    auto layout = json(meta);
    if (layout.contains("blocks") || layout.contains("loose_segments"))
      continue;
    auto payload = folder / L"payload.dat";
    if (fs::file_size(payload) < 4)
      continue;
    std::ifstream sniff(payload, std::ios::binary);
    Bytes magic(4);
    sniff.read(reinterpret_cast<char *>(magic.data()), 4);
    sniff.close();
    if (be(magic, 0) != 0xf0985030)
      continue;
    auto head = read(payload);
    auto name = utf16be(head, 36ull + be(head, 36) - 1,
                        head.size() - (36ull + be(head, 36) - 1));
    auto found = entries.find(crc(name));
    require(found != entries.end(), "Missing paired data bank");
    auto paired = found->second;
    auto df = contained(root, paired["folder"]);
    auto dl = json(df / L"asset.json");
    require(!dl.contains("loose_segments") ||
                dl.value("paired_owner", std::string()) ==
                    entry["folder"].get<std::string>(),
            "Paired data already owned");
    uint64_t data_size = fs::file_size(df / L"payload.dat");
    require(data_size <= 256ull << 20, "Paired data bank exceeds capacity");
    uint64_t count = be(head, 24), table = 32ull + be(head, 32) - 1;
    require(count <= 100000 && 0x68 + count * 4 <= head.size() &&
                table + count * 4 <= head.size(),
            "Invalid paired table");
    using Extent = std::pair<uint64_t, uint64_t>;
    std::set<Extent> extents;
    std::vector<std::pair<uint64_t, Extent>> patches;
    J records = J::array();
    std::vector<std::array<Extent, 2>> record_extents;
    for (uint64_t i = 0; i < count; ++i) {
      uint64_t field = 0x68 + i * 4, rec = field + be(head, field) - 1;
      field = table + i * 4;
      uint64_t desc = field + be(head, field) - 1;
      bounds(head, rec, 20);
      bounds(head, desc, 16);
      std::array<Extent, 2> ranges;
      for (int j = 0; j < 2; ++j) {
        ranges[j] = {be(head, desc + j * 8), be(head, desc + j * 8 + 4)};
        auto [o, n] = ranges[j];
        require(o <= data_size && n <= data_size - o,
                "Paired extent exceeds data");
        extents.insert(ranges[j]);
        patches.push_back({desc + j * 8, ranges[j]});
      }
      record_extents.push_back(ranges);
      records.push_back(
          J{{"index", i},
            {"id", be(head, rec)},
            {"type", be(head, rec + 4)},
            {"offsets", J::array()},
            {"folder", "_resources/" + decpad(i) + "_" + hex(be(head, rec))},
            {"component_files", J::array()}});
    }
    uint64_t end = 0;
    for (auto [o, n] : extents) {
      require(!n || o >= end, "Partially overlapping paired components");
      end = std::max(end, o + n);
    }
    auto data = read(df / L"payload.dat", 256ull << 20);
    struct Mapped {
      uint64_t offset, size;
      J file;
    };
    std::map<Extent, Mapped> mapping;
    J segments = J::array();
    uint64_t cursor = 0, source = 0;
    auto add = [&](std::string name, const Bytes &b) {
      write(df / path(name), b);
      segments.push_back(
          J{{"offset", cursor}, {"size", b.size()}, {"path", name}});
      cursor += b.size();
    };
    for (auto extent : extents) {
      job.check();
      auto [o, n] = extent;
      if (!n) {
        mapping[extent] = {0, 0, nullptr};
        continue;
      }
      if (o > source)
        add("_loose/gap_" + hex(source) + ".dat",
            sub(data, source, o - source));
      auto value = decode(sub(data, o, n));
      std::string file = "_loose/component_" + hex(o) + "_" + hex(n) + ".dat";
      mapping[extent] = {cursor, value.size(), file};
      add(file, value);
      source = o + n;
    }
    if (source < data_size)
      add("_loose/gap_" + hex(source) + ".dat",
          sub(data, source, data_size - source));
    for (auto &[offset, extent] : patches) {
      auto &m = mapping.at(extent);
      put(head, offset, m.offset);
      put(head, offset + 4, m.size);
    }
    for (size_t i = 0; i < records.size(); ++i)
      for (auto &e : record_extents[i]) {
        auto &m = mapping.at(e);
        records[i]["component_files"].push_back(J{
            {"folder", paired["folder"]}, {"path", m.file}, {"size", m.size}});
      }
    std::string descriptor = "_loose/descriptor.header";
    write(folder / path(descriptor), head);
    dl["loose_segments"] = segments;
    dl["loose_size"] = cursor;
    dl["paired_owner"] = entry["folder"];
    layout["paired_resources"] = records;
    layout["loose_segments"] = J::array(
        {J{{"offset", 0}, {"size", head.size()}, {"path", descriptor}}});
    layout["loose_size"] = head.size();
    jsonwrite(df / L"asset.json", dl);
    jsonwrite(meta, layout);
  }
  if (!keep_originals)
    for (auto &[id, e] : entries) {
      auto f = contained(root, e["folder"]);
      auto l = json(f / L"asset.json");
      if (l.contains("loose_segments") && fs::exists(f / L"payload.dat"))
        fs::remove(f / L"payload.dat");
    }
}
