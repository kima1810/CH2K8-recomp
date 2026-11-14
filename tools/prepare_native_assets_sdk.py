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
    if ('// CH2K8 native DDS retirement pump v1' not in text and
            '// CH2K8 retire DDS resources when the fence advances.' not in text):
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
    if '// CH2K8 retire DDS resources when the fence advances.' not in text:
        header_text = header.read_text(encoding='utf-8')
        header_text = once(header_text, '  void ClearCache() override;',
            '  void ClearCache() override;\n'
            '  void CompletedSubmissionUpdated(uint64_t completed_submission_index) override;')
        start = text.index('void D3D12TextureCache::RequestTextures(uint32_t used_texture_mask) {')
        end = text.index('#if XE_GPU_FINE_GRAINED_DRAW_SCOPES', start)
        text = text[:start] + '''void D3D12TextureCache::CompletedSubmissionUpdated(uint64_t completed_submission_index) {
  // CH2K8 retire DDS resources when the fence advances.
  std::erase_if(native_uploads_, [completed_submission_index](const auto& upload) {
    return upload.first <= completed_submission_index;
  });
  std::erase_if(native_pending_retirements_, [&](D3D12Texture* texture) {
    texture->CollectNativeRetired(*this, completed_submission_index);
    return texture->native_retired_resources_.empty();
  });
  TextureCache::CompletedSubmissionUpdated(completed_submission_index);
}

void D3D12TextureCache::RequestTextures(uint32_t used_texture_mask) {
''' + text[end:]
        header.write_text(header_text, encoding='utf-8', newline='\n')
        cpp.write_text(text, encoding='utf-8', newline='\n')
    (source/'include/rex/graphics/native_dds.h').write_bytes((ROOT/'port/src/native_dds.h').read_bytes())
    (source/'include/rex/graphics/native_dds_upload.h').write_bytes((ROOT/'port/src/native_dds_upload.h').read_bytes())
    (source/'src/graphics/d3d12/ch2k8_native_dds.inl').write_bytes((ROOT/'port/src/native_dds_d3d12.inl').read_bytes())
    common_cache = source/'src/graphics/pipeline/texture/cache.cpp'
    original = common_cache.read_text(encoding='utf-8')
    updated = patch_texture_requests(original)
    if updated != original:
        common_cache.write_text(updated, encoding='utf-8', newline='\n')
    common_header = source/'include/rex/graphics/pipeline/texture/cache.h'
    text = common_header.read_text(encoding='utf-8')
    if 'void InvalidateTextureFetchMask(' not in text:
        text = once(text, '    texture_bindings_in_sync_ &= ~mask;\n  }',
            '    InvalidateTextureFetchMask(mask);\n  }\n\n'
            '  void InvalidateTextureFetchMask(uint32_t mask) { texture_bindings_in_sync_ &= ~mask; }')
        common_header.write_text(text, encoding='utf-8', newline='\n')
    text = cpp.read_text(encoding='utf-8')
    marker = '// CH2K8 visit each texture binding once per draw.'
    if marker not in text:
        start = text.index('  // Pre-create 3D-as-2D wrappers before draw setup.')
        end = text.index('  // Transition the textures to the needed usage', start)
        text = text[:start] + f'  {marker}\n' + text[end:]
        anchor = '    D3D12Texture* binding_texture = static_cast<D3D12Texture*>(binding->texture);'
        start = text.index(anchor, start)
        text = text[:start] + '''    if (binding->key.dimension == xenos::DataDimension::k3D &&
        REXCVAR_GET(gpu_3d_to_2d_texture)) {
      constexpr auto shader_resource = D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE |
                                       D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
      if (binding->texture) {
        static_cast<D3D12Texture*>(binding->texture)->GetOrCreate3DAs2DResource(shader_resource);
      }
      if (binding->texture_signed) {
        static_cast<D3D12Texture*>(binding->texture_signed)->GetOrCreate3DAs2DResource(shader_resource);
      }
    }
''' + text[start:]
        cpp.write_text(text, encoding='utf-8', newline='\n')

    shared_cpp = source/'src/graphics/shared_memory.cpp'
    text = shared_cpp.read_text(encoding='utf-8')
    updated = patch_shared_memory_upload_merging(patch_shared_memory_requests(text))
    if updated != text:
        shared_cpp.write_text(updated, encoding='utf-8', newline='\n')
    shared_d3d12 = source/'src/graphics/d3d12/shared_memory.cpp'
    text = shared_d3d12.read_text(encoding='utf-8')
    updated = patch_d3d12_sparse_memory(text)
    if updated != text:
        shared_d3d12.write_text(updated, encoding='utf-8', newline='\n')
    prepare_sparse_header(source)
    prepare_shared_upload_trim(source)
    text = shared_d3d12.read_text(encoding='utf-8')
    updated = patch_shared_upload_stats(text)
    if updated != text:
        shared_d3d12.write_text(updated, encoding='utf-8', newline='\n')
    prepare_upload_reuse(source)
    tune_upload_reuse(source)
    simplify_upload_reuse_check(source)


def simplify_upload_reuse_check(source):
    path = source/'src/graphics/d3d12/shared_memory.cpp'
    text = path.read_text(encoding='utf-8')
    marker = '// Arm the CPU write watch before comparing the page bytes.'
    if marker in text:
        return
    text = once(text, '''  auto matches_snapshot = [&](uint32_t page) {
    return upload_snapshot_pages_[(page & (upload_snapshot_pages_.size() - 1))] == page &&''', '''  const size_t snapshot_mask = upload_snapshot_pages_.size() - 1;
  auto has_snapshot = [&](uint32_t page) {
    return upload_snapshot_pages_[page & snapshot_mask] == page;
  };
  auto matches_snapshot = [&](uint32_t page) {
    return has_snapshot(page) &&''')
    text = once(text, '''        if (matches_snapshot(upload_range_start)) {
          MakeRangeValid(upload_range_start << page_size_log2(), page_size, false);
          // Recheck after arming the CPU write watch. A write between the first
          // comparison and watch setup must still be uploaded.''', f'''        if (has_snapshot(upload_range_start)) {{
          {marker}
          MakeRangeValid(upload_range_start << page_size_log2(), page_size, false);''')
    path.write_text(text, encoding='utf-8', newline='\n')


def tune_upload_reuse(source):
    path = source/'src/graphics/d3d12/shared_memory.cpp'
    text = path.read_text(encoding='utf-8')
    if 'REXCVAR_DEFINE_INT32(ch2k8_upload_snapshot_mib,' in text:
        previous = 'REXCVAR_DEFINE_INT32(ch2k8_upload_snapshot_mib, 2,'
        if previous in text:
            path.write_text(once(text, previous, 'REXCVAR_DEFINE_INT32(ch2k8_upload_snapshot_mib, 8,'),
                            encoding='utf-8', newline='\n')
        return
    text = once(text, 'REXCVAR_DEFINE_BOOL(ch2k8_reuse_shared_uploads,', '''REXCVAR_DEFINE_INT32(ch2k8_upload_snapshot_mib, 8, "GPU/CH2K8",
                     "RAM budget for exact upload snapshots, rounded down to 1, 2, 4, or 8 MiB")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(ch2k8_reuse_shared_uploads,''')
    text = once(text, '''    upload_snapshot_bytes_.resize(size_t(kUploadSnapshotSlots) * page_size);
    upload_snapshot_pages_.assign(kUploadSnapshotSlots, UINT32_MAX);''', '''    const uint32_t budget_mib = std::clamp(REXCVAR_GET(ch2k8_upload_snapshot_mib), 1, 8);
    const uint32_t slots = (std::bit_floor(budget_mib) << 20) / page_size;
    upload_snapshot_bytes_.resize(size_t(slots) * page_size);
    upload_snapshot_pages_.assign(slots, UINT32_MAX);''')
    text = text.replace('kUploadSnapshotSlots - 1', 'upload_snapshot_pages_.size() - 1')
    text = text.replace('page % kUploadSnapshotSlots', '(page & (upload_snapshot_pages_.size() - 1))')
    text = once(text, '#include <cstring>', '#include <bit>\n#include <cstring>')
    header = source/'include/rex/graphics/d3d12/shared_memory.h'
    header.write_text(once(header.read_text(encoding='utf-8'),
                         '  static constexpr uint32_t kUploadSnapshotSlots = 2048;\n', ''),
                      encoding='utf-8', newline='\n')
    path.write_text(text, encoding='utf-8', newline='\n')


def prepare_upload_reuse(source):
    if 'REXCVAR_DEFINE_INT32(ch2k8_upload_snapshot_mib,' in (
            source/'src/graphics/d3d12/shared_memory.cpp').read_text(encoding='utf-8'):
        return
    edits = [
        ('include/rex/graphics/shared_memory.h', '  void RangeWrittenByGpu(',
         '  virtual void RangeWrittenByGpu('),
        ('include/rex/graphics/shared_memory.h', '  void InvalidateAllPages();',
         '  virtual void InvalidateAllPages();'),
        ('include/rex/graphics/d3d12/shared_memory.h', '  void ClearCache() override;',
         '''  void ClearCache() override;
  void RangeWrittenByGpu(uint32_t start, uint32_t length) override;
  void InvalidateAllPages() override;'''),
        ('include/rex/graphics/d3d12/shared_memory.h', '  uint64_t next_upload_trim_submission_ = 300;',
         '''  uint64_t next_upload_trim_submission_ = 300;
  static constexpr uint32_t kUploadSnapshotSlots = 2048;
  std::vector<uint8_t> upload_snapshot_bytes_;
  std::vector<uint32_t> upload_snapshot_pages_;'''),
        ('src/graphics/d3d12/shared_memory.cpp', 'REXCVAR_DEFINE_BOOL(d3d12_tiled_shared_memory,',
         '''REXCVAR_DEFINE_BOOL(ch2k8_reuse_shared_uploads, false, "GPU/CH2K8",
                    "Skip byte-identical shared uploads using a bounded CPU snapshot")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(d3d12_tiled_shared_memory,'''),
        ('src/graphics/d3d12/shared_memory.cpp', 'void D3D12SharedMemory::ClearCache() {',
         '''void D3D12SharedMemory::RangeWrittenByGpu(uint32_t start, uint32_t length) {
  if (!upload_snapshot_pages_.empty() && start < kBufferSize && length) {
    const uint32_t first = start >> page_size_log2();
    const uint32_t last = (start + std::min(length, kBufferSize - start) - 1) >> page_size_log2();
    if (last - first >= kUploadSnapshotSlots - 1) {
      std::fill(upload_snapshot_pages_.begin(), upload_snapshot_pages_.end(), UINT32_MAX);
    } else {
      for (uint32_t page = first; page <= last; ++page) {
        auto& tag = upload_snapshot_pages_[page % kUploadSnapshotSlots];
        if (tag == page) tag = UINT32_MAX;
      }
    }
  }
  SharedMemory::RangeWrittenByGpu(start, length);
}

void D3D12SharedMemory::InvalidateAllPages() {
  std::fill(upload_snapshot_pages_.begin(), upload_snapshot_pages_.end(), UINT32_MAX);
  SharedMemory::InvalidateAllPages();
}

void D3D12SharedMemory::ClearCache() {'''),
        ('src/graphics/d3d12/shared_memory.cpp', 'void D3D12SharedMemory::Shutdown(bool from_destructor) {',
         '''void D3D12SharedMemory::Shutdown(bool from_destructor) {
  upload_snapshot_pages_.clear();
  upload_snapshot_bytes_.clear();'''),
        ('src/graphics/d3d12/shared_memory.cpp', '  uint32_t copies = 0;\n  for (auto upload_range',
         '''  uint32_t copies = 0;
  const uint32_t page_size = uint32_t(1) << page_size_log2();
  if (REXCVAR_GET(ch2k8_reuse_shared_uploads) && upload_snapshot_pages_.empty()) {
    upload_snapshot_bytes_.resize(size_t(kUploadSnapshotSlots) * page_size);
    upload_snapshot_pages_.assign(kUploadSnapshotSlots, UINT32_MAX);
  }
  auto snapshot = [&](uint32_t page) {
    return upload_snapshot_bytes_.data() + size_t(page % kUploadSnapshotSlots) * page_size;
  };
  auto matches_snapshot = [&](uint32_t page) {
    return upload_snapshot_pages_[page % kUploadSnapshotSlots] == page &&
           std::memcmp(snapshot(page), memory().TranslatePhysical(page << page_size_log2()),
                       page_size) == 0;
  };
  for (auto upload_range'''),
        ('src/graphics/d3d12/shared_memory.cpp', '''  CommitUAVWritesAndTransitionBuffer(D3D12_RESOURCE_STATE_COPY_DEST);
  command_processor_.SubmitBarriers();
  auto& command_list''', '''  bool prepared_copy = false;
  auto& command_list'''),
        ('src/graphics/d3d12/shared_memory.cpp', '      command_list.D3DCopyBufferRegion(buffer_, upload_range_start',
         '''      if (!prepared_copy) {
        CommitUAVWritesAndTransitionBuffer(D3D12_RESOURCE_STATE_COPY_DEST);
        command_processor_.SubmitBarriers();
        prepared_copy = true;
      }
      command_list.D3DCopyBufferRegion(buffer_, upload_range_start'''),
        ('src/graphics/d3d12/shared_memory.cpp', '    while (upload_range_length != 0) {',
         '''    while (upload_range_length != 0) {
      uint32_t copy_pages = upload_range_length;
      if (!upload_snapshot_pages_.empty()) {
        if (matches_snapshot(upload_range_start)) {
          MakeRangeValid(upload_range_start << page_size_log2(), page_size, false);
          // Recheck after arming the CPU write watch. A write between the first
          // comparison and watch setup must still be uploaded.
          if (matches_snapshot(upload_range_start)) {
            ++upload_range_start;
            --upload_range_length;
            continue;
          }
        }
        copy_pages = 1;
        while (copy_pages < upload_range_length && !matches_snapshot(upload_range_start + copy_pages)) {
          ++copy_pages;
        }
      }'''),
        ('src/graphics/d3d12/shared_memory.cpp', 'upload_range_length << page_size_log2(),',
         'copy_pages << page_size_log2(),'),
        ('src/graphics/d3d12/shared_memory.cpp', '      std::memcpy(upload_buffer_mapping,\n                  memory().TranslatePhysical(upload_range_start << page_size_log2()),\n                  upload_buffer_size);',
         '''      if (upload_snapshot_pages_.empty()) {
        std::memcpy(upload_buffer_mapping,
                    memory().TranslatePhysical(upload_range_start << page_size_log2()),
                    upload_buffer_size);
      } else {
        for (uint32_t i = 0; i < (upload_buffer_size >> page_size_log2()); ++i) {
          const uint32_t page = upload_range_start + i;
          uint8_t* saved = snapshot(page);
          std::memcpy(saved, memory().TranslatePhysical(page << page_size_log2()), page_size);
          std::memcpy(upload_buffer_mapping + size_t(i) * page_size, saved, page_size);
          upload_snapshot_pages_[page % kUploadSnapshotSlots] = page;
        }
      }'''),
    ]
    for relative, original, updated in edits:
        path = source/relative
        text = path.read_text(encoding='utf-8')
        marker = 'REXCVAR_DEFINE_BOOL(ch2k8_reuse_shared_uploads,' if updated.startswith(
            'REXCVAR_DEFINE_BOOL(ch2k8_reuse_shared_uploads,') else updated
        if marker not in text:
            path.write_text(once(text, original, updated), encoding='utf-8', newline='\n')


def prepare_sparse_header(source):
    sparse_header = source/'include/rex/graphics/d3d12/shared_memory.h'
    text = sparse_header.read_text(encoding='utf-8')
    if 'sparse_heap_remaining_bytes_' not in text:
        text = once(text, '  std::vector<ID3D12Heap*> buffer_tiled_heaps_;',
            '  std::vector<ID3D12Heap*> buffer_tiled_heaps_;\n'
            '  ID3D12Heap* sparse_pool_heap_ = nullptr;\n'
            '  uint32_t sparse_heap_remaining_bytes_ = 0;')
        sparse_header.write_text(text, encoding='utf-8', newline='\n')


def patch_shared_memory_upload_merging(text):
    marker = '// CH2K8 coalesce overlapping page uploads.'
    if marker in text:
        return text
    return once(text, '''      if (last_upload_range.first + last_upload_range.second == page_start) {
        last_upload_range.second += page_count;''', f'''      {marker}
      const uint32_t last_end = last_upload_range.first + last_upload_range.second;
      if (page_start <= last_end) {{
        last_upload_range.second = std::max(last_end, page_start + page_count) - last_upload_range.first;''')


def patch_shared_upload_stats(text):
    if '// CH2K8 count shared-memory upload traffic.' in text:
        return text
    start = text.index('bool D3D12SharedMemory::UploadRanges(')
    prefix, upload = text[:start], text[start:]
    upload = once(upload, '  auto& command_list = command_processor_.GetDeferredCommandList();', '''  auto& command_list = command_processor_.GetDeferredCommandList();
  // CH2K8 count shared-memory upload traffic.
  const bool count_uploads = REXCVAR_GET(ch2k8_gpu_stats);
  uint64_t bytes = 0;
  uint32_t copies = 0;''')
    upload = once(upload, '      uint32_t upload_buffer_pages =', '''      if (count_uploads) {
        bytes += upload_buffer_size;
        ++copies;
      }
      uint32_t upload_buffer_pages =''')
    upload = once(upload, '  return true;\n}\n', '''  if (count_uploads) {
    using Clock = std::chrono::steady_clock;
    static thread_local auto last_report = Clock::now();
    static thread_local uint64_t total_bytes = 0, total_copies = 0;
    total_bytes += bytes;
    total_copies += copies;
    const auto now = Clock::now();
    if (now - last_report >= std::chrono::seconds(1)) {
      REXGPU_INFO("CH2K8 shared uploads: {} bytes in {} copies", total_bytes, total_copies);
      total_bytes = total_copies = 0;
      last_report = now;
    }
  }
  return true;
}
''')
    return once(prefix, '#include <rex/math.h>', '#include <chrono>\n\n#include <rex/math.h>') + upload


def prepare_shared_upload_trim(source):
    header = source/'include/rex/ui/graphics_upload_buffer_pool.h'
    cpp = source/'src/ui/graphics_upload_buffer_pool.cpp'
    shared = source/'src/graphics/d3d12/shared_memory.cpp'
    edits = [
        (shared, 'REXCVAR_DEFINE_BOOL(d3d12_tiled_shared_memory,', '''REXCVAR_DEFINE_BOOL(ch2k8_trim_shared_uploads, false, "GPU/CH2K8",
                    "Release excess idle D3D12 shared-memory staging pages")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(d3d12_tiled_shared_memory,'''),
        (header, '  void ClearCache();', '  size_t TrimWritablePages(size_t keep_count);\n  void ClearCache();'),
        (cpp, 'void GraphicsUploadBufferPool::ClearCache() {', '''size_t GraphicsUploadBufferPool::TrimWritablePages(size_t keep_count) {
  // The first page may still be referenced by the GPU. Keep it even if the
  // caller requests zero spare pages. Subsequent writable pages were reclaimed.
  Page* last_kept = writable_first_;
  if (!last_kept) {
    return 0;
  }
  while (keep_count && last_kept->next_) {
    last_kept = last_kept->next_;
    --keep_count;
  }
  Page* page = last_kept->next_;
  last_kept->next_ = nullptr;
  writable_last_ = last_kept;
  size_t trimmed_bytes = 0;
  while (page) {
    Page* next = page->next_;
    delete page;
    trimmed_bytes += page_size_;
    page = next;
  }
  return trimmed_bytes;
}

void GraphicsUploadBufferPool::ClearCache() {'''),
        (shared, '  upload_buffer_pool_->Reclaim(command_processor_.GetCompletedSubmission());', '''  const uint64_t completed = command_processor_.GetCompletedSubmission();
  upload_buffer_pool_->Reclaim(completed);
  if (REXCVAR_GET(ch2k8_trim_shared_uploads) && completed >= next_upload_trim_submission_) {
    // Keep 16 MiB of reusable staging pages for the next burst.
    const size_t trimmed_bytes = upload_buffer_pool_->TrimWritablePages(8);
    if (trimmed_bytes && REXCVAR_GET(ch2k8_gpu_stats)) {
      REXGPU_INFO("CH2K8 shared upload pool trimmed: {} bytes", trimmed_bytes);
    }
    next_upload_trim_submission_ = completed + 300;
  }'''),
        (source/'include/rex/graphics/d3d12/shared_memory.h',
         '  uint32_t sparse_heap_remaining_bytes_ = 0;',
         '  uint32_t sparse_heap_remaining_bytes_ = 0;\n  uint64_t next_upload_trim_submission_ = 300;'),
        (shared, '  sparse_heap_remaining_bytes_ = 0;\n',
         '  sparse_heap_remaining_bytes_ = 0;\n  next_upload_trim_submission_ = 300;\n'),
    ]
    for path, original, updated in edits:
        text = path.read_text(encoding='utf-8')
        marker = 'REXCVAR_DEFINE_BOOL(ch2k8_trim_shared_uploads,' if updated.startswith(
            'REXCVAR_DEFINE_BOOL(ch2k8_trim_shared_uploads,') else updated
        if marker not in text:
            path.write_text(once(text, original, updated), encoding='utf-8', newline='\n')


def patch_d3d12_sparse_memory(text):
    text = patch_d3d12_sparse_memory_v1(text)
    if 'ch2k8_pool_sparse_heaps,' in text:
        return text
    text = once(text, 'REXCVAR_DEFINE_INT32(ch2k8_sparse_heap_mib,', '''REXCVAR_DEFINE_BOOL(ch2k8_pool_sparse_heaps, true, "GPU/CH2K8",
                    "Pack small D3D12 shared-memory tile mappings into 4 MiB heaps")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(ch2k8_sparse_heap_mib,''')
    text = once(text, '  buffer_tiled_heaps_.clear();',
        '  buffer_tiled_heaps_.clear();\n  sparse_pool_heap_ = nullptr;\n  sparse_heap_remaining_bytes_ = 0;')
    start = text.index('  D3D12_HEAP_DESC heap_desc = {};',
                       text.index('bool D3D12SharedMemory::AllocateSparseHostGpuMemoryRange('))
    end = text.index('  D3D12_TILED_RESOURCE_COORDINATE', start)
    text = text[:start] + '''  // Physical heap offsets are independent of the guest tile addresses.
  constexpr uint32_t pool_bytes = 4 * (1 << 20);
  uint32_t heap_offset_bytes = 0;
  ID3D12Heap* heap;
  if (length_bytes <= sparse_heap_remaining_bytes_) {
    heap = sparse_pool_heap_;
    heap_offset_bytes = pool_bytes - sparse_heap_remaining_bytes_;
    sparse_heap_remaining_bytes_ -= length_bytes;
  } else {
    const uint32_t heap_bytes = REXCVAR_GET(ch2k8_pool_sparse_heaps) && length_bytes < pool_bytes
                                    ? pool_bytes : length_bytes;
    D3D12_HEAP_DESC heap_desc = {};
    heap_desc.SizeInBytes = heap_bytes;
    heap_desc.Properties.Type = D3D12_HEAP_TYPE_DEFAULT;
    heap_desc.Flags = D3D12_HEAP_FLAG_ALLOW_ONLY_BUFFERS | provider.GetHeapFlagCreateNotZeroed();
    if (FAILED(device->CreateHeap(&heap_desc, IID_PPV_ARGS(&heap)))) {
      REXGPU_ERROR("Shared memory: Failed to create a tile heap");
      return false;
    }
    buffer_tiled_heaps_.push_back(heap);
    if (heap_bytes > length_bytes) {
      sparse_pool_heap_ = heap;
      sparse_heap_remaining_bytes_ = heap_bytes - length_bytes;
    }
    if (REXCVAR_GET(ch2k8_gpu_stats)) {
      REXGPU_INFO("CH2K8 sparse shared memory allocation: {} bytes", heap_bytes);
    }
  }

''' + text[end:]
    return once(text, '  UINT heap_range_start_offset = 0;',
        '  UINT heap_range_start_offset = heap_offset_bytes / D3D12_TILED_RESOURCE_TILE_SIZE_IN_BYTES;')


def patch_d3d12_sparse_memory_v1(text):
    if 'REXCVAR_DEFINE_INT32(ch2k8_sparse_heap_mib,' in text:
        return text
    text = once(text, 'REXCVAR_DEFINE_BOOL(d3d12_tiled_shared_memory,', '''REXCVAR_DECLARE(bool, ch2k8_gpu_stats);
REXCVAR_DEFINE_INT32(ch2k8_sparse_heap_mib, 4, "GPU/CH2K8",
                     "D3D12 shared memory tile heap granularity in MiB (1, 2, or 4)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(d3d12_tiled_shared_memory,''')
    text = once(text, '''    InitializeSparseHostGpuMemory(
        std::max(kHostGpuMemoryOptimalSparseAllocationLog2, uint32_t(16)));''', '''    const int32_t heap_mib = REXCVAR_GET(ch2k8_sparse_heap_mib);
    InitializeSparseHostGpuMemory(heap_mib == 1 ? 20 : heap_mib == 2 ? 21 :
                                  kHostGpuMemoryOptimalSparseAllocationLog2);''')
    return once(text, '  buffer_tiled_heaps_.push_back(heap);', '''  buffer_tiled_heaps_.push_back(heap);
  if (REXCVAR_GET(ch2k8_gpu_stats)) {
    REXGPU_INFO("CH2K8 sparse shared memory allocation: {} bytes", length_bytes);
  }''')


def patch_shared_memory_requests(text):
    marker = '// CH2K8 keep single-range requests off the heap.'
    if marker in text:
        return text
    start = text.index('  // Some texture or buffer is empty, for example - safe to draw in this case.')
    end = text.index('  for (const std::pair<uint32_t, uint32_t>& range : merged_ranges)', start)
    block = text[start:end]
    block = once(block, '  SCOPE_profile_cpu_f("gpu");\n\n', '')
    block = once(block, '  std::vector<std::pair<uint32_t, uint32_t>> merged_ranges;\n', '')
    block = block.replace('merged_ranges', 'range_storage')
    block = '\n'.join('  ' + line if line else '' for line in block.rstrip().splitlines())
    text = once(text, '#include <rex/graphics/shared_memory.h>',
        '#include <rex/graphics/shared_memory.h>\n\n#include <span>')
    start = text.index('  // Some texture or buffer is empty, for example - safe to draw in this case.')
    end = text.index('  for (const std::pair<uint32_t, uint32_t>& range : merged_ranges)', start)
    return text[:start] + f'''  {marker}
  std::vector<std::pair<uint32_t, uint32_t>> range_storage;
  std::span<const std::pair<uint32_t, uint32_t>> merged_ranges;
  if (count == 1) {{
    const auto [start, length] = ranges[0];
    if (!length) {{
      return true;
    }}
    if (start > kBufferSize || (kBufferSize - start) < length) {{
      return false;
    }}
    merged_ranges = {{ranges, 1}};
  }} else {{
{block}
    merged_ranges = range_storage;
  }}

  SCOPE_profile_cpu_f("gpu");

''' + text[end:]


def patch_texture_requests(text):
    marker = '// CH2K8 avoid a write to the invalidation flag on steady-state draws.'
    if marker in text:
        return patch_texture_range_batch(text)
    text = once(text, '  if (texture_became_outdated_.exchange(false, std::memory_order_acquire)) {',
        f'  {marker}\n'
        '  if (texture_became_outdated_.load(std::memory_order_acquire) &&\n'
        '      texture_became_outdated_.exchange(false, std::memory_order_acquire)) {')
    text = once(text, '  uint32_t textures_remaining = used_texture_mask & ~texture_bindings_in_sync_;\n'
        '  uint32_t index = 0;', '  uint32_t index = 0;')
    return patch_texture_range_batch(once(text, '  // Update the texture keys and the textures.\n  uint32_t bindings_changed = 0;',
        '''  // Only changed fetch slots need decoding or texture uploads. The backend
  // still tracks resource state and usage for every texture used by the draw.
  uint32_t textures_remaining = used_texture_mask & ~texture_bindings_in_sync_;
  if (!textures_remaining) {
    COUNT_profile_set("gpu/texture_cache/request_textures_pending_load_count", 0);
    COUNT_profile_set("gpu/texture_cache/request_textures_pending_range_count", 0);
    return;
  }

  // Update the texture keys and the textures.
  uint32_t bindings_changed = 0;'''))


def patch_texture_range_batch(text):
    if '// CH2K8 batch texture upload ranges directly.' in text:
        return text
    text = once(text, '  std::vector<PendingSharedMemoryRange> pending_shared_memory_ranges;',
        '  // CH2K8 batch texture upload ranges directly.\n'
        '  std::vector<std::pair<uint32_t, uint32_t>> pending_shared_memory_ranges;')
    text = once(text, '      pending_shared_memory_ranges.push_back(pending_ranges[i]);',
        '      pending_shared_memory_ranges.emplace_back(pending_ranges[i].start, pending_ranges[i].length);')
    start = text.index('  bool batched_shared_memory_request_succeeded = true;')
    end = text.index('  if (batched_shared_memory_request_succeeded)', start)
    return text[:start] + '''  const bool batched_shared_memory_request_succeeded =
      shared_memory().RequestRanges(pending_shared_memory_ranges.data(), pending_shared_memory_ranges.size());

''' + text[end:]
