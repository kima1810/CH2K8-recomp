#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace ch2k8 {
struct NativeDDSInfo {
  uint32_t width=0,height=0,mips=0,format=0,bytes_per_block=0;
  std::string identity,path;
};
struct NativeDDS : NativeDDSInfo {
  std::vector<uint8_t> data;
  static uint32_t LE(const uint8_t* p) { return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24; }
  static NativeDDS Parse(std::vector<uint8_t> bytes,uint32_t original_width,uint32_t original_height,uint32_t original_format) {
    if(bytes.size()<128 || std::string(reinterpret_cast<const char*>(bytes.data()),4)!="DDS " || LE(bytes.data()+4)!=124)
      throw std::runtime_error("Invalid DDS header");
    NativeDDS d; d.width=LE(bytes.data()+16); d.height=LE(bytes.data()+12); d.mips=std::max(LE(bytes.data()+28),1u); d.format=original_format;
    const uint32_t fourcc=original_format==18?0x31545844:original_format==19?0x33545844:original_format==20?0x35545844:original_format==49?0x32495441:original_format==59?0x31495441:0;
    d.bytes_per_block=(original_format==18 || original_format==59)?8:16;
    if(!fourcc || !original_width || !original_height || !d.width || !d.height || d.width>8192 || d.height>8192 || d.width%4 || d.height%4 ||
       LE(bytes.data()+76)!=32 || LE(bytes.data()+80)!=4 || LE(bytes.data()+84)!=fourcc || LE(bytes.data()+112) || LE(bytes.data()+24)>1)
      throw std::runtime_error("Unsupported DDS layout");
    const auto scale=d.width/original_width;
    if(d.width<original_width || d.width%original_width || !scale || (scale&(scale-1)) || uint64_t(d.width)*original_height!=uint64_t(d.height)*original_width)
      throw std::runtime_error("DDS must retain aspect ratio and use a power-of-two upscale");
    unsigned max_mips=0; for(auto n=std::max(d.width,d.height);n;n>>=1) ++max_mips;
    if(d.mips>max_mips) throw std::runtime_error("Invalid DDS mip count");
    size_t expected=128;
    for(uint32_t i=0;i<d.mips;++i) expected+=size_t((std::max(d.width>>i,1u)+3)/4)*((std::max(d.height>>i,1u)+3)/4)*d.bytes_per_block;
    if(bytes.size()!=expected) throw std::runtime_error("DDS mip payload length differs from header");
    d.data=std::move(bytes); return d;
  }
};

class NativeDDSCatalog {
 public:
  explicit NativeDDSCatalog(const std::filesystem::path& root={}) {
    if(root.empty()) return;
    root_=std::filesystem::canonical(root);
    std::ifstream in(root_/"native_dds.index");
    if(!in) return;
    std::string line;
    if(!std::getline(in,line) || line!="CH2K8_DDS_V1") throw std::runtime_error("Invalid native DDS catalog version");
    while(std::getline(in,line)) {
      if(line.empty()) continue;
      std::istringstream row(line); Item item; std::string hash;
      if(!(row>>item.width>>item.height>>item.format>>hash)) throw std::runtime_error("Invalid native DDS identity");
      if(row.get()!='\t' || !std::getline(row,item.path) || item.path.empty() || item.path.find_first_of("\t\r\n")!=std::string::npos || hash.size()!=16 || hash.find_first_not_of("0123456789abcdef")!=std::string::npos)
        throw std::runtime_error("Invalid native DDS path/hash");
      item.hash=std::stoull(hash,nullptr,16);
      item.identity=hash+":"+std::to_string(item.width)+":"+std::to_string(item.height)+":"+std::to_string(item.format);
      items_[Key(item.width,item.height,item.format)].push_back(std::move(item));
    }
    if(in.bad()) throw std::runtime_error("Cannot read native DDS catalog");
  }
  static NativeDDSCatalog& Get() {
    static NativeDDSCatalog catalog([] {
#ifdef _WIN32
      const auto* root=_wgetenv(L"CH2K8_ASSET_ROOT");
      return root?std::filesystem::path(root):std::filesystem::path();
#else
      const auto* root=std::getenv("CH2K8_ASSET_ROOT");
      return root?std::filesystem::path(root):std::filesystem::path();
#endif
    }());
    return catalog;
  }
  bool HasCandidates(uint32_t width,uint32_t height,uint32_t format) const {
    return items_.contains(Key(width,height,format));
  }
  // A resident identity needs only metadata: its GPU resource already contains
  // the payload. Avoid re-reading the file after releasing the CPU copy.
  std::shared_ptr<const NativeDDS> Find(uint32_t width,uint32_t height,uint32_t format,const std::function<uint64_t()>& hash_pixels,bool include_stock=false,const NativeDDSInfo* resident=nullptr) {
    auto found=items_.find(Key(width,height,format));
    if(found==items_.end()) return {};
    const auto hash=hash_pixels();
    for(const auto& item:found->second) {
      if(item.hash!=hash) continue;
      if(!include_stock && unchanged_.contains(item.identity)) return {};
      if(resident && resident->identity==item.identity) {
        auto dds=std::make_shared<NativeDDS>();
        static_cast<NativeDDSInfo&>(*dds)=*resident;
        return dds;
      }
      if(auto cached=loaded_.find(item.identity);cached!=loaded_.end()) if(auto live=cached->second.lock()) return live;
      auto supplied=std::filesystem::u8path(item.path);
      if(supplied.is_absolute() || supplied.has_root_name()) throw std::runtime_error("Absolute DDS path");
      auto path=std::filesystem::canonical(root_/supplied);
      auto relative=path.lexically_relative(root_);
      if(relative.empty() || *relative.begin()=="..") throw std::runtime_error("DDS path escapes installation");
      auto length=std::filesystem::file_size(path);
      if(length>128+(128u<<20)) throw std::runtime_error("DDS exceeds native texture size limit");
      std::ifstream stream(path,std::ios::binary);
      std::vector<uint8_t> bytes(static_cast<size_t>(length));
      if(!stream.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(length))) throw std::runtime_error("Short DDS read");
      auto dds=std::make_shared<NativeDDS>(NativeDDS::Parse(std::move(bytes),width,height,format));
      dds->identity=item.identity; dds->path=item.path;
      // Exported base-only DDS files are editing templates. Keep the original
      // game's mip chain until the user supplies an actual replacement.
      if(!include_stock && dds->width==width && dds->height==height && dds->mips==1) {
        uint64_t base_hash=14695981039346656037ull;
        for(size_t i=128;i<dds->data.size();++i) base_hash=(base_hash^dds->data[i])*1099511628211ull;
        if(base_hash==item.hash) { unchanged_.insert(item.identity);return {}; }
      }
      loaded_[item.identity]=dds;
      return dds;
    }
    return {};
  }
 private:
  static uint64_t Key(uint32_t w,uint32_t h,uint32_t f) { return uint64_t(w)|(uint64_t(h)<<16)|(uint64_t(f)<<32); }
  struct Item { uint32_t width=0,height=0,format=0; uint64_t hash=0; std::string identity,path; };
  std::filesystem::path root_;
  std::unordered_map<uint64_t,std::vector<Item>> items_;
  std::unordered_map<std::string,std::weak_ptr<const NativeDDS>> loaded_;
  std::unordered_set<std::string> unchanged_;
};
} // namespace ch2k8
