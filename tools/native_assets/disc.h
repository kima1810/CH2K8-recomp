#pragma once
#include "common.h"
struct Disc {
  struct Member {
    uint64_t offset, size;
  };
  fs::path source;
  bool iso;
  uint64_t image_size = 0, base = 0;
  std::map<std::string, Member> members;
  std::set<uint64_t> dirs;
  explicit Disc(fs::path p)
      : source(longpath(fs::canonical(longpath(p)))),
        iso(fs::is_regular_file(longpath(p))) {
    if (!iso)
      return;
    image_size = fs::file_size(source);
    bool found = false;
    for (uint64_t b : {0ull, 0xfd90000ull, 0x2080000ull, 0x18300000ull})
      if (b + 65536 + 28 <= image_size) {
        auto h = physical(b + 65536, 28);
        if (std::string(h.begin(), h.begin() + 20) == "MICROSOFT*XBOX*MEDIA") {
          base = b;
          walk(le(h, 20), le(h, 24), "", 0);
          found = true;
          break;
        }
      }
    // Some valid trimmed/rebuilt disc dumps use another partition offset.
    // Scan sector-aligned descriptors in bounded blocks, preserving the fast
    // path above for normal XGD2/XGD3 and game-partition-only images.
    if (!found) {
      constexpr uint64_t chunk = 2ull << 20;
      auto limit = std::min<uint64_t>(image_size, 1ull << 30);
      for (uint64_t start = 65536; start + 28 <= limit && !found;
           start += chunk) {
        auto data = physical(start, std::min<uint64_t>(chunk, limit - start));
        for (size_t o = 0; o + 28 <= data.size(); o += 2048) {
          if (std::string_view(reinterpret_cast<const char *>(data.data() + o),
                               20) != "MICROSOFT*XBOX*MEDIA")
            continue;
          base = start + o - 65536;
          walk(le(data, o + 20), le(data, o + 24), "", 0);
          found = true;
          break;
        }
      }
    }
    require(
        found,
        "No XDVDFS volume descriptor found at standard offsets or within the "
        "first 1 GiB. Supply a complete Xbox 360 ISO or extracted disc folder; "
        "ZIP/7z, GOD/STFS and PS3 containers are not ISO disc images.");
    require(exists("default.xex") && exists("0A"),
            "Xbox game ISO lacks default.xex/0A");
  }
  Bytes physical(uint64_t offset, uint64_t size) {
    require(offset <= image_size && size <= image_size - offset &&
                size <= 2ull << 30,
            "Xbox ISO member exceeds image extent");
    std::ifstream f(source, std::ios::binary);
    f.seekg(offset);
    Bytes b(size);
    f.read(reinterpret_cast<char *>(b.data()), size);
    require(uint64_t(f.gcount()) == size, "Truncated Xbox ISO");
    return b;
  }
  void walk(uint64_t sector, uint64_t size, const std::string &prefix,
            unsigned depth) {
    if (!size)
      return;
    uint64_t offset = base + sector * 2048;
    require(depth <= 64 && dirs.insert(offset).second,
            "Cyclic or excessively deep Xbox ISO directory");
    require(size >= 14 && size <= 32ull << 20,
            "Invalid Xbox ISO directory size");
    auto b = physical(offset, size);
    std::vector<size_t> stack{0};
    std::set<size_t> seen;
    while (!stack.empty()) {
      size_t o = stack.back();
      stack.pop_back();
      require(seen.insert(o).second && o + 14 <= size,
              "Invalid Xbox ISO directory tree");
      auto left = le16(b, o), right = le16(b, o + 2);
      if (left == 65535 && right == 65535)
        continue;
      auto len = b[o + 13];
      bounds(b, o + 14, len);
      require(len > 0, "Empty Xbox ISO filename");
      std::string name(b.begin() + o + 14, b.begin() + o + 14 + len);
      require(name != "." && name != ".." &&
                  name.find_first_of("/\\:\0", 0, 4) == std::string::npos,
              "Invalid Xbox ISO filename");
      for (unsigned char c : name)
        require(c >= 32 && c < 127, "Invalid Xbox ISO filename");
      auto start = uint64_t(le(b, o + 4)) * 2048 + base,
           length = uint64_t(le(b, o + 8));
      require(start <= image_size && length <= image_size - start,
              "Xbox ISO member exceeds image extent");
      auto full = prefix + name;
      if (b[o + 12] & 16)
        walk(le(b, o + 4), length, full + "/", depth + 1);
      else
        require(members.emplace(lower(full), Member{start, length}).second,
                "Duplicate Xbox ISO member");
      if (left)
        stack.push_back(left * 4);
      if (right)
        stack.push_back(right * 4);
    }
  }
  bool exists(std::string name) {
    return iso ? members.contains(lower(name))
               : fs::is_regular_file(contained(source, name));
  }
  uint64_t size(std::string name) {
    if (!iso)
      return fs::file_size(contained(source, name));
    require(exists(name), "Missing Xbox ISO member: " + name);
    return members.at(lower(name)).size;
  }
  Bytes member(std::string name, uint64_t offset, uint64_t count) {
    require(offset <= size(name) && count <= size(name) - offset,
            "Truncated Xbox disc member: " + name);
    if (iso)
      return physical(members.at(lower(name)).offset + offset, count);
    std::ifstream f(contained(source, name), std::ios::binary);
    f.seekg(offset);
    Bytes b(count);
    f.read(reinterpret_cast<char *>(b.data()), count);
    require(uint64_t(f.gcount()) == count, "Short Xbox disc read");
    return b;
  }
};
struct Archive {
  struct Part {
    std::string name;
    uint64_t offset, size;
    uint32_t flags;
  };
  struct Entry {
    uint32_t index, hash, flags;
    uint64_t offset, size;
  };
  Disc &disc;
  std::vector<Part> parts;
  std::vector<Entry> entries;
  Bytes header;
  uint64_t total = 0;
  explicit Archive(Disc &d) : disc(d) {
    auto h = d.member("0A", 0, 24);
    require(be(h, 0) == 0xaa00b3bf && be(h, 4) == 2048,
            "Unsupported Xbox archive header");
    auto na = be(h, 8), nf = be(h, 16);
    require(na > 0 && na <= 26 && nf > 0 && nf <= 100000,
            "Invalid Xbox archive counts");
    header = d.member("0A", 0, 24 + uint64_t(na + nf) * 16);
    for (uint32_t i = 0; i < na; ++i) {
      size_t o = 24 + i * 16;
      std::string name = utf16be(header, o + 8, 8);
      require(std::regex_match(name, std::regex("0[A-Z]")),
              "Invalid archive part name");
      uint64_t size = uint64_t(be(header, o)) * 2048;
      require(d.exists(name) && d.size(name) >= size,
              "Missing or truncated Xbox archive part: " + name);
      parts.push_back({name, total, size, be(header, o + 4)});
      total += size;
    }
    std::set<uint32_t> hashes;
    for (uint32_t i = 0; i < nf; ++i) {
      size_t o = 24 + na * 16 + i * 16;
      Entry e{i, be(header, o), be(header, o + 8),
              uint64_t(be(header, o + 4)) * 2048, be(header, o + 12)};
      require(e.offset >= align(header.size(), 2048) && e.offset <= total &&
                  e.size <= total - e.offset && e.size <= 2ull << 30,
              "Invalid Xbox archive entry extent");
      require(hashes.insert(e.hash).second, "Duplicate Xbox archive identity");
      entries.push_back(e);
    }
    auto ordered = entries;
    std::sort(ordered.begin(), ordered.end(),
              [](auto &a, auto &b) { return a.offset < b.offset; });
    uint64_t end = align(header.size(), 2048);
    for (auto &e : ordered) {
      require(e.offset >= end, "Overlapping archive entries");
      end = e.offset + e.size;
    }
  }
  Bytes read(uint64_t offset, uint64_t size) {
    require(offset <= total && size <= total - offset && size <= 2ull << 30,
            "Archive read exceeds extent");
    Bytes out;
    out.reserve(size);
    for (auto &p : parts) {
      if (size && offset >= p.offset && offset < p.offset + p.size) {
        auto n = std::min(size, p.offset + p.size - offset);
        auto b = disc.member(p.name, offset - p.offset, n);
        out.insert(out.end(), b.begin(), b.end());
        offset += n;
        size -= n;
      }
    }
    require(!size, "Incomplete archive read");
    return out;
  }
  J compatibility() {
    J flags = J::object(), pf = J::array(), words = J::array();
    for (unsigned i = 0; i < 6; ++i)
      words.push_back(be(header, i * 4));
    for (auto &e : entries)
      flags[std::to_string(e.hash)] = e.flags;
    for (auto &p : parts)
      pf.push_back(p.flags);
    return J{{"version", 1},     {"platform", "xbox360"},
             {"header", words},  {"toc_flags", flags},
             {"part_flags", pf}, {"part_size", parts.front().size}};
  }
};
inline std::map<uint32_t, std::string> candidate_names() {
  std::map<uint32_t, std::string> out;
  auto add = [&](std::string n) { out[crc(n)] = n; };
  std::istringstream banks(
      "frontend frontend_sync global gamedata gamedataextra loading legalpage "
      "loc fonts online playercreate playeditor teamselectlogo arenapics "
      "overlaycache jukebox roster_english streetdata studio studio_preview "
      "studio_pontiac dornas crowd sfx_inside facegen ababall basket "
      "chantcreate chantcreate_drums chantcreate_sounds gameintro "
      "gameintro_cameras gameintro_drums gameintro_playerspeech "
      "halftimeadjustments legacy powerbar reelmanual weeklyshow tutorial "
      "drilldata shrine shrine_trophies statefarm kellogg gumbel director");
  std::string name;
  while (banks >> name)
    for (auto ext : {".iff", ".cdf", ".bin"})
      add(name + ext);
  for (auto prefix : {"ua", "uh", "ux", "selua", "seluh", "selux", "s", "m",
                      "p", "coach", "h"})
    for (unsigned i = 0; i < (std::string(prefix) == "h" ? 10000 : 1000); ++i)
      for (auto ext : {".iff", ".cdf", ".bin"})
        add(std::string(prefix) +
            decpad(i, std::string(prefix) == "h" ? 4 : 3) + ext);
  return out;
}
