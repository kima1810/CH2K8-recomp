#pragma once
// Native WAV substitution at the decoded XMA frame boundary. The original
// decoder still drives packet consumption/timing; no console encoder is used.
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace ch2k8 {
inline uint64_t PCMHash(std::span<const uint8_t> data) { uint64_t h=14695981039346656037ull;for(auto b:data)h=(h^b)*1099511628211ull;return h; }
struct PCMClip {
  uint32_t channels=0,rate=0,samples=0;
  std::vector<uint8_t> pcm;
  static uint32_t LE(const uint8_t* p){return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
  static PCMClip Parse(std::span<const uint8_t> wav,uint32_t channels,uint32_t rate,uint32_t samples) {
    if(wav.size()<44 || std::memcmp(wav.data(),"RIFF",4) || std::memcmp(wav.data()+8,"WAVE",4) || uint64_t(LE(wav.data()+4))+8!=wav.size())throw std::runtime_error("Invalid native PCM WAV");
    PCMClip clip;clip.channels=channels;clip.rate=rate;clip.samples=samples;bool fmt=false,data=false;
    for(size_t pos=12;pos+8<=wav.size();) {
      const auto size=LE(wav.data()+pos+4);const auto* p=wav.data()+pos+8;
      if(uint64_t(pos)+8+size>wav.size())throw std::runtime_error("Truncated WAV chunk");
      if(!std::memcmp(wav.data()+pos,"fmt ",4)) {
        if(fmt || size<16 || (LE(p)&65535)!=1 || (LE(p)>>16)!=channels || LE(p+4)!=rate || (LE(p+12)&65535)!=channels*2 || (LE(p+12)>>16)!=16)throw std::runtime_error("Native WAV must retain PCM16 channels/rate");
        fmt=true;
      }
      if(!std::memcmp(wav.data()+pos,"data",4)) {
        if(data || uint64_t(samples)*channels*2!=size)throw std::runtime_error("Native WAV sample count differs from source");
        clip.pcm.assign(p,p+size);data=true;
      }
      pos+=8+size+(size&1);
    }
    if(!fmt || !data || !samples || channels<1 || channels>2)throw std::runtime_error("Incomplete native WAV");
    return clip;
  }
  void CopyBE(uint64_t cursor,size_t frames,std::span<uint8_t> output) const {
    if(output.size()<frames*channels*2)throw std::runtime_error("PCM output buffer too small");
    for(size_t i=0;i<frames*channels;++i) {
      const auto source=(cursor*channels+i)*2;
      output[i*2]=source+1<pcm.size()?pcm[size_t(source)+1]:0;
      output[i*2+1]=source<pcm.size()?pcm[size_t(source)]:0;
    }
  }
};

class PCMCatalog {
 public:
  explicit PCMCatalog(const std::filesystem::path& root={}) {
    if(root.empty())return;root_=std::filesystem::canonical(root);std::ifstream in(root_/"native_audio.index");if(!in)return;
    std::string line;if(!std::getline(in,line)||line!="CH2K8_PCM_V1")throw std::runtime_error("Invalid native audio catalog");
    while(std::getline(in,line)) {
      if(line.empty())continue;std::istringstream row(line);std::string first,prefix;Item item;
      if(!(row>>first>>item.prefix_length>>prefix>>item.channels>>item.rate>>item.samples) || row.get()!='\t' || !std::getline(row,item.path) || item.path.empty() || item.prefix_length<2048 || item.prefix_length>16384 || item.prefix_length%2048 || item.channels<1 || item.channels>2 || !item.samples)throw std::runtime_error("Invalid native audio entry");
      item.first=std::stoull(first,nullptr,16);item.prefix=std::stoull(prefix,nullptr,16);items_[item.first].push_back(std::move(item));
    }
  }
  static PCMCatalog& Get() {
    static PCMCatalog catalog([] {
#ifdef _WIN32
      const auto* p=_wgetenv(L"CH2K8_ASSET_ROOT");return p?std::filesystem::path(p):std::filesystem::path();
#else
      const auto* p=std::getenv("CH2K8_ASSET_ROOT");return p?std::filesystem::path(p):std::filesystem::path();
#endif
    }());return catalog;
  }
  std::shared_ptr<const PCMClip> Find(std::span<const uint8_t> input,uint32_t channels) {
    std::lock_guard lock(mutex_);
    if(items_.empty() || input.size()<2048)return {};
    auto it=items_.find(PCMHash(input.first(2048)));if(it==items_.end())return {};
    for(const auto& item:it->second) {
      if(item.channels!=channels || item.prefix_length>input.size() || PCMHash(input.first(item.prefix_length))!=item.prefix)continue;
      if(auto found=loaded_.find(item.path);found!=loaded_.end())if(auto clip=found->second.lock())return clip;
      auto path=std::filesystem::canonical(root_/std::filesystem::u8path(item.path));auto rel=path.lexically_relative(root_);
      if(rel.empty()||*rel.begin()==".."||std::filesystem::u8path(item.path).is_absolute())throw std::runtime_error("Native WAV path escapes assets");
      const auto size=std::filesystem::file_size(path);if(size>512ull*1024*1024)throw std::runtime_error("Native WAV exceeds memory limit");
      std::ifstream file(path,std::ios::binary);std::vector<uint8_t> bytes(size_t(size),0);
      if(!file.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(size)))throw std::runtime_error("Short native WAV read");
      auto clip=std::make_shared<PCMClip>(PCMClip::Parse(bytes,item.channels,item.rate,item.samples));loaded_[item.path]=clip;return clip;
    }
    return {};
  }
 private:
  struct Item{uint64_t first=0,prefix=0;uint32_t prefix_length=0,channels=0,rate=0,samples=0;std::string path;};
  std::filesystem::path root_;std::mutex mutex_;std::unordered_map<uint64_t,std::vector<Item>> items_;std::unordered_map<std::string,std::weak_ptr<const PCMClip>> loaded_;
};

class PCMStream {
 public:
  void Reset(){checked_=false;clip_.reset();cursor_=0;observed_=false;}
  void Observe(uintptr_t address,uint32_t bit_offset) {
    if(observed_ && address==address_ && bit_offset<bit_offset_)Disable();
    address_=address;bit_offset_=bit_offset;observed_=true;
  }
  bool active() const{return bool(clip_);}
  bool Consider(std::span<const uint8_t> input,uint32_t channels,bool eligible) {
    if(checked_)return bool(clip_);checked_=true;if(!eligible)return false;
    const auto* enabled=std::getenv("CH2K8_NATIVE_AUDIO");if(enabled && enabled[0]=='0')return false;
    clip_=PCMCatalog::Get().Find(input,channels);return bool(clip_);
  }
  bool Apply(std::span<uint8_t> output,uint32_t frames,uint32_t channels) {
    if(!clip_ || channels!=clip_->channels)return false;
    clip_->CopyBE(cursor_,frames,output);cursor_+=frames;return true;
  }
  void Disable(){clip_.reset();checked_=true;}
 private:
  bool checked_=false,observed_=false;uintptr_t address_=0;uint32_t bit_offset_=0;std::shared_ptr<const PCMClip> clip_;uint64_t cursor_=0;
};
} // namespace ch2k8
