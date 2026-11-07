#include "loose_archive.h"
#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/devices/host_path_entry.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/runtime.h>

namespace {
using namespace rex::filesystem;
using rex::X_STATUS;
class LooseFile final : public File {
 public:
  LooseFile(uint32_t access,Entry* entry,std::shared_ptr<ch2k8::LooseArchive> archive,uint64_t offset,uint64_t size)
    : File(access,entry), archive_(std::move(archive)),offset_(offset),size_(size) {}
  void Destroy() override { delete this; }
  X_STATUS ReadSync(std::span<uint8_t> buffer,size_t offset,size_t* read) override {
    *read=0;
    if (!(file_access_ & (FileAccess::kGenericRead|FileAccess::kFileReadData))) return X_STATUS_ACCESS_DENIED;
    if (offset>=size_) return buffer.empty()?X_STATUS_SUCCESS:X_STATUS_END_OF_FILE;
    try {
      *read=archive_->Read(offset_+offset,buffer.first(size_t(std::min<uint64_t>(buffer.size(),size_-offset))));
      return X_STATUS_SUCCESS;
    } catch(const std::exception& e) { REXLOG_ERROR("Loose asset I/O: {}",e.what()); return X_STATUS_UNSUCCESSFUL; }
  }
  X_STATUS WriteSync(std::span<const uint8_t>,size_t,size_t* written) override { *written=0; return X_STATUS_ACCESS_DENIED; }
 private:
  std::shared_ptr<ch2k8::LooseArchive> archive_;
  uint64_t offset_,size_;
};
class LooseEntry final : public Entry {
 public:
  LooseEntry(Device* device,Entry* parent,const ch2k8::LooseArchive::Range& part,std::shared_ptr<ch2k8::LooseArchive> archive)
    : Entry(device,parent,part.path),archive_(std::move(archive)),offset_(part.offset) {
    size_=part.size; allocation_size_=size_; attributes_=kFileAttributeReadOnly|kFileAttributeNormal;
  }
  X_STATUS Open(uint32_t access,File** file) override {
    *file=nullptr;
    if (access & (FileAccess::kGenericWrite|FileAccess::kFileWriteData|FileAccess::kFileAppendData)) return X_STATUS_ACCESS_DENIED;
    *file=new LooseFile(access,this,archive_,offset_,size_); return X_STATUS_SUCCESS;
  }
 private:
  std::shared_ptr<ch2k8::LooseArchive> archive_;
  uint64_t offset_;
};
class LooseDevice final : public HostPathDevice {
  class Root final : public Entry {
   public:
    Root(Device* device,const std::filesystem::path& folder,std::shared_ptr<ch2k8::LooseArchive> archive)
      : Entry(device,nullptr,""),archive_(std::move(archive)) {
      attributes_=kFileAttributeDirectory|kFileAttributeReadOnly;
      for(const auto& part:archive_->parts()) children_.push_back(std::make_unique<LooseEntry>(device,this,part,archive_));
      FileInfo info;
      if(rex::filesystem::GetInfo(folder/"default.xex",&info)) children_.emplace_back(HostPathEntry::Create(device,this,folder/"default.xex",info));
    }
    X_STATUS Open(uint32_t access,File** file) override { *file=new LooseFile(access,this,archive_,0,0);return X_STATUS_SUCCESS; }
   private:
    std::shared_ptr<ch2k8::LooseArchive> archive_;
  };
 public:
  explicit LooseDevice(const std::filesystem::path& root)
    : HostPathDevice("\\Device\\CH2K8Assets",root,true),archive_(std::make_shared<ch2k8::LooseArchive>(root)) {}
  bool Initialize() override {
    // A synthetic root is essential: HostPathEntry's existence check would
    // discard virtual archive parts because no physical 0A..0M files exist.
    root_=std::make_unique<Root>(this,host_path(),archive_);
    return true;
  }
  void Dump(rex::string::StringBuffer* buffer) override { root_->Dump(buffer,0); }
  Entry* ResolvePath(std::string_view path) override {
    while (!path.empty() && (path.front()=='\\' || path.front()=='/')) path.remove_prefix(1);
    return root_->ResolvePath(path);
  }
 private:
  std::shared_ptr<ch2k8::LooseArchive> archive_;
  std::unique_ptr<Root> root_;
};
}

std::unique_ptr<rex::filesystem::Device> Ch2k8CreateLooseDevice(const std::filesystem::path& root) {
  auto device=std::make_unique<LooseDevice>(root);
  if(!device->Initialize()) throw std::runtime_error("Cannot initialize loose game device");
  return device;
}

bool Ch2k8MountLooseAssets(rex::Runtime& runtime) {
  if (!std::filesystem::exists(runtime.game_data_root()/"assets.map")) return true;
  try {
    auto device=Ch2k8CreateLooseDevice(runtime.game_data_root());
    auto* vfs=runtime.file_system();
    if (!vfs->RegisterDevice(std::move(device))) throw std::runtime_error("Cannot register loose game device");
    // Keep the original mount and already-open XEX handles alive.
    for (auto link:{"game:","d:","\\Device\\Harddisk0\\Partition1"}) {
      vfs->UnregisterSymbolicLink(link);
      vfs->RegisterSymbolicLink(link,"\\Device\\CH2K8Assets");
    }
    REXLOG_INFO("CH2K8 loose-folder archive mounted (13-part compatibility address space)");
    return true;
  } catch (const std::exception& e) { REXLOG_ERROR("CH2K8 loose installation rejected: {}",e.what()); return false; }
}
