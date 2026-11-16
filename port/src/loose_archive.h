#pragma once
#include <algorithm>
#include "native_path.h"
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <mutex>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace ch2k8 {
// Immutable scatter map. Files are opened lazily; the bounded handle cache and
// all seeks are protected because guest asynchronous I/O uses worker threads.
class LooseArchive {
 public:
  struct Range { uint64_t offset, size; std::string path; };
  explicit LooseArchive(const std::filesystem::path& root, bool verify_files = true)
      : root_(NativePath(std::filesystem::canonical(NativePath(root)))) {
    std::ifstream overlay(root_ / "stock-root.txt");
    if (overlay) {
      std::string base;
      if (!std::getline(overlay, base) || base.empty()) throw std::runtime_error("Invalid stock asset root");
      auto supplied = std::filesystem::u8path(base);
      if (!supplied.is_absolute()) throw std::runtime_error("Stock asset root must be absolute");
      stock_ = NativePath(std::filesystem::canonical(NativePath(supplied)));
      if (stock_ == root_ || !std::filesystem::is_regular_file(stock_ / "assets.map") ||
          !std::filesystem::is_regular_file(stock_ / "default.xex"))
        throw std::runtime_error("Invalid stock asset installation");
    }
    std::ifstream input(root_ / "assets.map");
    std::string line;
    if (!std::getline(input,line) || line != "CH2K8_LOOSE_V1") throw std::runtime_error("Invalid assets.map version");
    uint64_t covered=0, part_end=0;
    while (std::getline(input,line)) {
      if (line.empty()) continue;
      std::istringstream row(line);
      std::string kind, offset, size, path, extra;
      if (!std::getline(row,kind,'\t') || !std::getline(row,offset,'\t') || !std::getline(row,size,'\t') || !std::getline(row,path) || path.empty())
        throw std::runtime_error("Invalid assets.map row");
      auto number=[](const std::string& text) {
        if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos) throw std::runtime_error("Invalid map integer");
        return std::stoull(text);
      };
      Range range{number(offset),number(size),path};
      if (!range.size || range.offset > UINT64_MAX-range.size) throw std::runtime_error("Invalid map extent");
      if (kind=="P") {
        if (range.offset!=part_end || parts_.size()>=26 || path!=std::string("0")+char('A'+parts_.size())) throw std::runtime_error("Invalid virtual archive part");
        parts_.push_back(range); part_end+=range.size;
      } else if (kind=="S") {
        if (range.offset!=covered) throw std::runtime_error("Scatter map has a gap or overlap");
        if (verify_files) CheckedComponent(range);
        ranges_.push_back(range); covered+=range.size;
      } else throw std::runtime_error("Unknown map row");
    }
    if (input.bad() || parts_.empty() || covered!=part_end) throw std::runtime_error("Incomplete assets.map");
    total_=covered;
  }
  const std::vector<Range>& parts() const { return parts_; }
  const std::vector<Range>& ranges() const { return ranges_; }
  size_t Read(uint64_t offset, std::span<uint8_t> output) {
    std::lock_guard lock(mutex_);
    if (offset>=total_ || output.empty()) return 0;
    auto it=std::upper_bound(ranges_.begin(),ranges_.end(),offset,[](uint64_t v,const Range& r){return v<r.offset;});
    if (it!=ranges_.begin()) --it;
    size_t done=0;
    while (done<output.size() && it!=ranges_.end()) {
      const auto count=size_t(std::min<uint64_t>(output.size()-done,it->size-(offset-it->offset)));
      auto found=files_.find(it->path);
      if (found==files_.end()) {
        if (files_.size()>=64) files_.clear();
        auto stream=std::make_unique<std::ifstream>(CheckedComponent(*it),std::ios::binary);
        if (!*stream) throw std::runtime_error("Cannot open loose asset: "+it->path);
        found=files_.emplace(it->path,std::move(stream)).first;
      }
      auto& stream=*found->second;
      stream.clear(); stream.seekg(std::streamoff(offset-it->offset));
      stream.read(reinterpret_cast<char*>(output.data()+done),std::streamsize(count));
      if (size_t(stream.gcount())!=count) throw std::runtime_error("Short loose asset read: "+it->path);
      done+=count; offset+=count; ++it;
    }
    return done;
  }
 private:
  std::filesystem::path CheckedComponent(const Range& range) const {
    auto full=CheckedPath(range.path);
    if (std::filesystem::file_size(full)!=range.size)
      throw std::runtime_error("Loose component size differs from map: "+range.path);
    return full;
  }
  std::filesystem::path CheckedPath(const std::string& relative) const {
    std::string_view name(relative);
    const auto *root = &root_;
    if (name.starts_with("@stock/")) {
      name.remove_prefix(7);
      if (stock_.empty() || !(name.starts_with("assets/") || name.starts_with("_runtime/")))
        throw std::runtime_error("Invalid stock asset path");
      root = &stock_;
    }
    const auto supplied=std::filesystem::u8path(name);
    if (supplied.is_absolute() || supplied.has_root_name()) throw std::runtime_error("Absolute loose asset path");
    auto full=NativePath(std::filesystem::canonical(NativePath(*root/supplied)));
    auto rel=full.lexically_relative(*root);
    if (rel.empty() || *rel.begin()=="..") throw std::runtime_error("Loose asset path escapes installation");
    if (root == &stock_ && *rel.begin() != "assets" && *rel.begin() != "_runtime")
      throw std::runtime_error("Stock asset path escapes its asset directories");
    return full;
  }
  std::filesystem::path root_;
  std::filesystem::path stock_;
  uint64_t total_=0;
  std::vector<Range> parts_,ranges_;
  std::mutex mutex_;
  std::unordered_map<std::string,std::unique_ptr<std::ifstream>> files_;
};
} // namespace ch2k8
