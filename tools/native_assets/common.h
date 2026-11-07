#pragma once
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "../../port/src/native_path.h"
#include "../../port/third_party/nlohmann/json.hpp"
#include <algorithm>
#include <array>
#include <bcrypt.h>
#include <bit>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <regex>
#include <set>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using J = nlohmann::json;
using Bytes = std::vector<uint8_t>;
namespace fs = std::filesystem;
inline void require(bool ok, const std::string &error) {
  if (!ok)
    throw std::runtime_error(error);
}
inline std::string utf8(const fs::path &p) {
  auto s = p.generic_u8string();
  return {s.begin(), s.end()};
}
inline fs::path path(const std::string &s) {
  return fs::path(std::u8string(s.begin(), s.end()));
}
// Win32 extended paths keep derived headers usable in deeply nested folders.
inline fs::path longpath(const fs::path &p) { return ch2k8::NativePath(p); }
inline std::string lower(std::string s) {
  for (auto &c : s)
    if (c >= 'A' && c <= 'Z')
      c += 32;
  return s;
}
inline std::string hex(uint64_t n, unsigned width = 8) {
  std::ostringstream s;
  s << std::hex << std::setfill('0') << std::setw(width) << n;
  return s.str();
}
inline std::string decpad(uint64_t n, unsigned width = 4) {
  std::ostringstream s;
  s << std::setfill('0') << std::setw(width) << n;
  return s.str();
}
inline uint64_t num(const J &v) {
  if (v.is_string())
    return std::stoull(v.get<std::string>());
  require(v.is_number_unsigned() ||
              (v.is_number_integer() && v.get<int64_t>() >= 0),
          "Invalid unsigned asset value");
  return v.get<uint64_t>();
}
inline void bounds(std::span<const uint8_t> b, uint64_t off, uint64_t len) {
  require(off <= b.size() && len <= b.size() - off,
          "Truncated resource or invalid extent");
}
inline uint32_t be(std::span<const uint8_t> b, size_t o) {
  bounds(b, o, 4);
  return uint32_t(b[o]) << 24 | uint32_t(b[o + 1]) << 16 |
         uint32_t(b[o + 2]) << 8 | b[o + 3];
}
inline uint32_t le(std::span<const uint8_t> b, size_t o) {
  bounds(b, o, 4);
  return uint32_t(b[o]) | uint32_t(b[o + 1]) << 8 | uint32_t(b[o + 2]) << 16 |
         uint32_t(b[o + 3]) << 24;
}
inline uint16_t le16(std::span<const uint8_t> b, size_t o) {
  bounds(b, o, 2);
  return b[o] | uint16_t(b[o + 1]) << 8;
}
inline void put(Bytes &b, size_t o, uint64_t v, unsigned count = 4,
                bool little = false) {
  bounds(b, o, count);
  for (unsigned i = 0; i < count; ++i)
    b[o + i] = uint8_t(v >> ((little ? i : count - i - 1) * 8));
}
inline Bytes sub(std::span<const uint8_t> b, uint64_t off, uint64_t size) {
  bounds(b, off, size);
  return {b.begin() + off, b.begin() + off + size};
}
inline Bytes read(const fs::path &p, uint64_t max = 512ull << 20) {
  auto size = fs::file_size(longpath(p));
  require(size <= max, "Resource exceeds bounded tool capacity: " + utf8(p));
  Bytes b(size);
  std::ifstream f(longpath(p), std::ios::binary);
  require(bool(f), "Cannot open " + utf8(p));
  f.read(reinterpret_cast<char *>(b.data()), b.size());
  require(uint64_t(f.gcount()) == size, "Short resource read: " + utf8(p));
  return b;
}
inline void write(const fs::path &p, std::span<const uint8_t> b) {
  fs::create_directories(longpath(p.parent_path()));
  std::ofstream f(longpath(p), std::ios::binary | std::ios::trunc);
  require(bool(f), "Cannot write " + utf8(p));
  f.write(reinterpret_cast<const char *>(b.data()), b.size());
  f.close();
  require(bool(f), "Write failed (check disk space): " + utf8(p));
}
inline void publish(const fs::path &p, std::span<const uint8_t> b) {
  if (fs::is_regular_file(longpath(p)) &&
      fs::file_size(longpath(p)) == b.size() &&
      read(p) == Bytes(b.begin(), b.end()))
    return;
  auto tmp = longpath(p);
  tmp += L".tmp";
  write(tmp, b);
  require(MoveFileExW(tmp.c_str(), longpath(p).c_str(),
                      MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH),
          "Cannot publish " + utf8(p));
}
inline void text(const fs::path &p, const std::string &s) {
  publish(p, {reinterpret_cast<const uint8_t *>(s.data()), s.size()});
}
inline J json(const fs::path &p) {
  auto b = read(p, 64ull << 20);
  return J::parse(b);
}
inline void jsonwrite(const fs::path &p, const J &j) {
  text(p, j.dump(2) + "\n");
}
struct Hash {
  BCRYPT_HASH_HANDLE h = nullptr;
  BCRYPT_ALG_HANDLE alg = nullptr;
  Hash() {
    require(BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, nullptr,
                                        0) >= 0,
            "SHA256 unavailable");
    require(BCryptCreateHash(alg, &h, nullptr, 0, nullptr, 0, 0) >= 0,
            "Cannot create SHA256");
  }
  ~Hash() {
    if (h)
      BCryptDestroyHash(h);
    if (alg)
      BCryptCloseAlgorithmProvider(alg, 0);
  }
  void add(std::span<const uint8_t> b) {
    require(b.size() <= ULONG_MAX &&
                BCryptHashData(h, const_cast<PUCHAR>(b.data()), ULONG(b.size()),
                               0) >= 0,
            "SHA256 failed");
  }
  std::string finish() {
    std::array<uint8_t, 32> d;
    require(BCryptFinishHash(h, d.data(), 32, 0) >= 0, "SHA256 failed");
    std::string s;
    for (auto n : d)
      s += hex(n, 2);
    return s;
  }
};
inline std::string sha(std::span<const uint8_t> b) {
  Hash h;
  h.add(b);
  return h.finish();
}
inline std::string file_sha(const fs::path &p) {
  std::ifstream f(longpath(p), std::ios::binary);
  require(bool(f), "Cannot hash file");
  Hash h;
  Bytes b(8 << 20);
  while (f) {
    f.read(reinterpret_cast<char *>(b.data()), b.size());
    if (f.gcount())
      h.add(std::span(b).first(size_t(f.gcount())));
  }
  require(f.eof(), "Hash file read failed");
  return h.finish();
}
inline uint64_t fnv(std::span<const uint8_t> b) {
  uint64_t n = 14695981039346656037ull;
  for (auto c : b)
    n = (n ^ c) * 1099511628211ull;
  return n;
}
inline uint32_t crc(std::string s) {
  uint32_t n = ~0u;
  for (auto c : s) {
    if (c >= 'a' && c <= 'z')
      c -= 32;
    n ^= uint8_t(c);
    for (int i = 0; i < 8; ++i)
      n = (n >> 1) ^ (0xedb88320u & uint32_t(-int32_t(n & 1)));
  }
  return ~n;
}
inline fs::path contained(const fs::path &root, const std::string &relative) {
  auto r = path(relative);
  require(!r.is_absolute() && !r.has_root_name(), "Absolute loose asset path");
  auto base = longpath(fs::weakly_canonical(longpath(root)));
  auto full = longpath(fs::weakly_canonical(longpath(base / r)));
  auto rel = full.lexically_relative(base);
  require(!rel.empty() && *rel.begin() != "..",
          "Loose resource path escapes installation");
  for (auto p = full; p != base; p = p.parent_path()) {
    auto a = GetFileAttributesW(p.c_str());
    require(a == INVALID_FILE_ATTRIBUTES || !(a & FILE_ATTRIBUTE_REPARSE_POINT),
            "Linked asset paths are unsupported");
  }
  return full;
}
inline uint64_t align(uint64_t n, uint64_t a) {
  require(a > 0 && n <= UINT64_MAX - a, "Invalid alignment");
  return (n + a - 1) / a * a;
}
inline std::string utf16be(std::span<const uint8_t> b, size_t o, size_t max) {
  std::string s;
  for (size_t i = 0; i < max; i += 2) {
    bounds(b, o + i, 2);
    if (!b[o + i] && !b[o + i + 1])
      return s;
    require(!b[o + i] && b[o + i + 1] >= 32 && b[o + i + 1] < 127,
            "Unsupported non-ASCII Xbox bank name");
    s += char(b[o + i + 1]);
  }
  throw std::runtime_error("Unterminated Xbox bank name");
}
struct Job {
  fs::path progress, cancel;
  std::chrono::steady_clock::time_point last{};
  void check() {
    if (!cancel.empty() && fs::exists(cancel))
      throw std::runtime_error("ISO import cancelled");
  }
  void update(uint64_t done, uint64_t total, const std::string &message) {
    check();
    auto now = std::chrono::steady_clock::now();
    if (!progress.empty() &&
        (done == total || now - last > std::chrono::milliseconds(250))) {
      jsonwrite(progress,
                J{{"done", done}, {"total", total}, {"message", message}});
      last = now;
    }
  }
};
