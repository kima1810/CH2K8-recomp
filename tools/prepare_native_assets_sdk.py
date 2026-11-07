"""Version-checked native DDS upload integration for the pinned source SDK."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def once(text, old, new):
    if text.count(old)!=1:
        raise ValueError('Unrecognized native DDS SDK patch site: '+old[:100])
    return text.replace(old,new,1)


def prepare_native_assets(source):
    host=source/'src/filesystem/devices/host_path_device.cpp'
    host_text=host.read_text(encoding='utf-8')
    if '// CH2K8 lazy loose installation' not in host_text:
        host_text=once(host_text,'    if (child_info.type == rex::filesystem::FileInfo::Type::kDirectory) {','''    // CH2K8 lazy loose installation: the pre-guest mount needs the XEX,
    // not a recursive enumeration of tens of thousands of editable resources.
    if (child_info.type == rex::filesystem::FileInfo::Type::kDirectory &&
        !std::filesystem::exists(host_path_ / "assets.map")) {''')
        host.write_text(host_text,encoding='utf-8',newline='\n')
    shared=source/'include/rex/graphics/shared_memory.h'
    shared_text=shared.read_text(encoding='utf-8')
    if 'GuestMemoryForNativeAssets' not in shared_text:
        shared_text=once(shared_text,'class SharedMemory {\n public:','class SharedMemory {\n public:\n  const memory::Memory& GuestMemoryForNativeAssets() const { return memory_; }')
        shared.write_text(shared_text,encoding='utf-8',newline='\n')
    if 'NativeRangeWrittenByGpu' not in shared_text:
        shared_text=once(shared_text,'  const memory::Memory& GuestMemoryForNativeAssets() const { return memory_; }','''  const memory::Memory& GuestMemoryForNativeAssets() const { return memory_; }
  bool NativeRangeWrittenByGpu(uint32_t address,uint32_t length) {
    if(!length || uint64_t(address)+length>kBufferSize) return true;
    auto lock=global_critical_region_.Acquire();
    const auto first=address>>page_size_log2_,last=(address+length-1)>>page_size_log2_;
    for(auto page=first;page<=last;++page) if(system_page_flags_valid_and_gpu_written_[page>>6] & (uint64_t(1)<<(page&63))) return true;
    return false;
  }''')
        shared.write_text(shared_text,encoding='utf-8',newline='\n')
    header=source/'include/rex/graphics/d3d12/texture_cache.h'
    text=header.read_text(encoding='utf-8')
    if '// CH2K8 native DDS v1' not in text:
        text=once(text,'#include <rex/graphics/register_file.h>','#include <rex/graphics/register_file.h>\n#include <rex/graphics/ch2k8_native_dds.h>\n// CH2K8 native DDS v1')
        text=once(text,'    uint8_t swizzled_signs;','    uint8_t swizzled_signs;\n    uint64_t native_revision=0;')
        text=once(text,'    ~D3D12Texture();\n\n    ID3D12Resource* resource() const { return resource_.Get(); }','''    ~D3D12Texture();

    ID3D12Resource* resource() const { return native_resource_ ? native_resource_.Get() : resource_.Get(); }
    uint64_t native_revision_=0;
    std::shared_ptr<const ::ch2k8::NativeDDS> native_dds_;
    Microsoft::WRL::ComPtr<ID3D12Resource> native_resource_;
    D3D12_RESOURCE_STATES native_state_=D3D12_RESOURCE_STATE_COPY_DEST;
    std::vector<Microsoft::WRL::ComPtr<ID3D12Resource>> native_retired_resources_;
    std::vector<uint32_t> native_retired_descriptors_;
    void RetireNativeDescriptors() {
      for(const auto& pair:srv_descriptors_) native_retired_descriptors_.push_back(pair.second);
      srv_descriptors_.clear(); ++native_revision_;
    }
    void AccountNativeMemory(uint64_t bytes) { SetHostMemoryUsage(GetHostMemoryUsage()+bytes); }''')
        # There are two state setters in this header. Limit replacement to the
        # texture class's exact old_state spelling (scaled buffer differs).
        text=once(text,'      D3D12_RESOURCE_STATES old_state = resource_state_;\n      resource_state_ = new_state;\n      return old_state;','''      if(native_resource_) {
        const auto old=native_state_; native_state_=new_state; return old;
      }
      D3D12_RESOURCE_STATES old_state = resource_state_;
      resource_state_ = new_state;
      return old_state;''')
        text=once(text,'  class ScaledResolveVirtualBuffer {','  bool TryLoadNativeDDS(D3D12Texture& texture);\n\n  class ScaledResolveVirtualBuffer {')
    text=text.replace('std::shared_ptr<const ch2k8::NativeDDS>','std::shared_ptr<const ::ch2k8::NativeDDS>')
    text=text.replace('<rex/graphics/ch2k8_native_dds.h>','<rex/graphics/native_dds.h>')
    header.write_text(text,encoding='utf-8',newline='\n')
    if 'native_uploads_' not in text:
        text=once(text,'  bool TryLoadNativeDDS(D3D12Texture& texture);','  bool TryLoadNativeDDS(D3D12Texture& texture);\n  std::vector<std::pair<uint64_t, Microsoft::WRL::ComPtr<ID3D12Resource>>> native_uploads_;')
        header.write_text(text,encoding='utf-8',newline='\n')
    # Upgrade both pristine and previously patched SDKs, retaining fence-safe
    # ownership while allowing frequently replaced textures to shed old VRAM.
    if '// CH2K8 native DDS retirement v2' not in text:
        text=once(text,'    std::shared_ptr<const ::ch2k8::NativeDDS> native_dds_;',
                  '    std::shared_ptr<const ::ch2k8::NativeDDSInfo> native_dds_;')
        text=once(text,'    std::vector<Microsoft::WRL::ComPtr<ID3D12Resource>> native_retired_resources_;','''    // CH2K8 native DDS retirement v2
    struct NativeRetired {
      uint64_t submission,bytes;
      Microsoft::WRL::ComPtr<ID3D12Resource> resource;
      std::vector<uint32_t> descriptors;
    };
    uint64_t native_allocation_=0;
    std::vector<NativeRetired> native_retired_resources_;
    void RetireNativeResource(uint64_t submission) {
      // Allocate the queue slot before transferring ownership.
      native_retired_resources_.push_back({submission,native_allocation_,{}, {}});
      auto& retired=native_retired_resources_.back();
      retired.resource=std::move(native_resource_);
      RetireNativeDescriptors();
      retired.descriptors.swap(native_retired_descriptors_);
      native_allocation_=0; native_dds_.reset();
    }
    void CollectNativeRetired(D3D12TextureCache& cache,uint64_t completed) {
      std::erase_if(native_retired_resources_,[&](const NativeRetired& retired) {
        if(retired.submission>completed) return false;
        for(auto descriptor:retired.descriptors) cache.ReleaseTextureDescriptor(descriptor);
        SetHostMemoryUsage(GetHostMemoryUsage()-retired.bytes);
        return true;
      });
    }''')
        header.write_text(text,encoding='utf-8',newline='\n')
    cpp=source/'src/graphics/d3d12/texture_cache.cpp'
    text=cpp.read_text(encoding='utf-8')
    if '// CH2K8 native DDS v1' not in text:
        text=once(text,'bool D3D12TextureCache::LoadTextureDataFromResidentMemoryImpl(','''// CH2K8 native DDS v1
#include "ch2k8_native_dds.inl"

bool D3D12TextureCache::LoadTextureDataFromResidentMemoryImpl(''')
        text=once(text,'  TextureKey texture_key = d3d12_texture.key();','  TextureKey texture_key = d3d12_texture.key();\n  if (TryLoadNativeDDS(d3d12_texture)) return true;')
        text=once(text,'  for (const auto& descriptor_pair : srv_descriptors_) {','''  for (auto descriptor : native_retired_descriptors_) d3d12_texture_cache.ReleaseTextureDescriptor(descriptor);
  for (const auto& descriptor_pair : srv_descriptors_) {''')
        text=once(text,'    if (key.key != binding->key || key.host_swizzle != binding->host_swizzle ||','''    const auto* native_texture=static_cast<const D3D12Texture*>(binding->texture);
    if (key.native_revision != (native_texture ? native_texture->native_revision_ : 0)) return false;
    if (key.key != binding->key || key.host_swizzle != binding->host_swizzle ||''')
        text=once(text,'    key.key = binding->key;','''    const auto* native_texture=static_cast<const D3D12Texture*>(binding->texture);
    key.native_revision=native_texture ? native_texture->native_revision_ : 0;
    key.key = binding->key;''')
        text=once(text,'  uint32_t mip_levels = texture_key.mip_max_level + 1;','  uint32_t mip_levels = texture.native_dds_ ? texture.native_dds_->mips : texture_key.mip_max_level + 1;')
        cpp.write_text(text,encoding='utf-8',newline='\n')
    if '// CH2K8 native DDS retirement pump v1' not in text:
        header_text=header.read_text(encoding='utf-8')
        header_text=once(header_text,'  bool TryLoadNativeDDS(D3D12Texture& texture);','''  // CH2K8 native DDS retirement pump v1
  std::unordered_set<D3D12Texture*> native_pending_retirements_;
  bool TryLoadNativeDDS(D3D12Texture& texture);''')
        header_text=once(header_text,'#include <rex/graphics/native_dds.h>',
                         '#include <rex/graphics/native_dds.h>\n#include <unordered_set>')
        header.write_text(header_text,encoding='utf-8',newline='\n')
        text=once(text,'void D3D12TextureCache::RequestTextures(uint32_t used_texture_mask) {','''void D3D12TextureCache::RequestTextures(uint32_t used_texture_mask) {
  // CH2K8 native DDS retirement pump v1
  const auto completed=command_processor_.GetCompletedSubmission();
  std::erase_if(native_pending_retirements_,[&](D3D12Texture* texture) {
    texture->CollectNativeRetired(*this,completed);
    return texture->native_retired_resources_.empty();
  });''')
        text=once(text,'  auto& d3d12_texture_cache = static_cast<D3D12TextureCache&>(texture_cache());',
                  '  auto& d3d12_texture_cache = static_cast<D3D12TextureCache&>(texture_cache());\n  d3d12_texture_cache.native_pending_retirements_.erase(this);')
        cpp.write_text(text,encoding='utf-8',newline='\n')
    if '#include <rex/graphics/native_dds_upload.h>' not in text:
        text=once(text,'#include <rex/graphics/flags.h>','#include <rex/graphics/flags.h>\n#include <rex/graphics/native_dds_upload.h>')
        text=once(text,'void D3D12TextureCache::RequestTextures(uint32_t used_texture_mask) {','''void D3D12TextureCache::RequestTextures(uint32_t used_texture_mask) {
  std::erase_if(native_uploads_,[&](const auto& upload){return upload.first<=command_processor_.GetCompletedSubmission();});''')
        cpp.write_text(text,encoding='utf-8',newline='\n')
    if '// CH2K8 release remaining retired descriptors' not in text:
        text=once(text,'  for (auto descriptor : native_retired_descriptors_) d3d12_texture_cache.ReleaseTextureDescriptor(descriptor);','''  // CH2K8 release remaining retired descriptors (destruction is fence-safe).
  for (const auto& retired : native_retired_resources_)
    for (auto descriptor : retired.descriptors) d3d12_texture_cache.ReleaseTextureDescriptor(descriptor);
  for (auto descriptor : native_retired_descriptors_) d3d12_texture_cache.ReleaseTextureDescriptor(descriptor);''')
        cpp.write_text(text,encoding='utf-8',newline='\n')
    (source/'include/rex/graphics/native_dds.h').write_bytes((ROOT/'port/src/native_dds.h').read_bytes())
    (source/'include/rex/graphics/native_dds_upload.h').write_bytes((ROOT/'port/src/native_dds_upload.h').read_bytes())
    (source/'src/graphics/d3d12/ch2k8_native_dds.inl').write_bytes((ROOT/'port/src/native_dds_d3d12.inl').read_bytes())
