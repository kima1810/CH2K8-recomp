// Included inside rex::graphics::d3d12. Version-patched into the pinned SDK.
// The guest texture/key and its watched memory stay intact. Native textures and
// obsolete descriptors remain alive until their submission completes, so
// reusing a guest address cannot leave an old DDS bound.
bool D3D12TextureCache::TryLoadNativeDDS(D3D12Texture& texture) {
  texture.CollectNativeRetired(*this,command_processor_.GetCompletedSubmission());
  const auto* enabled=std::getenv("CH2K8_NATIVE_DDS");
  if(enabled && enabled[0]=='0')return false;
  const auto key=texture.key();
  std::shared_ptr<const ::ch2k8::NativeDDS> dds;
  if(!key.scaled_resolve && !key.signed_separate && key.base_page &&
     key.dimension==xenos::DataDimension::k2DOrStacked && key.GetDepthOrArraySize()==1 &&
     !(key.GetWidth()%4) && !(key.GetHeight()%4) &&
     !(key.packed_mips && std::min(key.GetWidth(),key.GetHeight())<=16) &&
     ((uint32_t(key.format)>=18 && uint32_t(key.format)<=20) || uint32_t(key.format)==49 || uint32_t(key.format)==59) &&
     ::ch2k8::NativeDDSCatalog::Get().HasCandidates(key.GetWidth(),key.GetHeight(),uint32_t(key.format)) &&
     !shared_memory().NativeRangeWrittenByGpu(key.base_page<<12,texture.GetGuestBaseSize())) {
    try {
      dds=::ch2k8::NativeDDSCatalog::Get().Find(key.GetWidth(),key.GetHeight(),uint32_t(key.format),[&] {
        const auto* memory=shared_memory().GuestMemoryForNativeAssets().TranslatePhysical<const uint8_t*>(key.base_page<<12);
        const uint32_t bpp=(uint32_t(key.format)==18 || uint32_t(key.format)==59)?8:16, log_bpp=bpp==8?3:4;
        const uint32_t width=(key.GetWidth()+3)/4,height=(key.GetHeight()+3)/4,pitch=key.pitch*8;
        uint64_t hash=14695981039346656037ull;
        for(uint32_t y=0;y<height;++y) for(uint32_t x=0;x<width;++x) {
          uint32_t offset=key.tiled?uint32_t(texture_util::GetTiledOffset2D(x,y,pitch,log_bpp)):(y*pitch+x)*bpp;
          if(uint64_t(offset)+bpp>texture.GetGuestBaseSize() || uint64_t(key.base_page<<12)+offset+bpp>0x20000000ull) return uint64_t(0);
          for(uint32_t i=0;i<bpp;++i) {
            uint32_t j=i;
            switch(uint32_t(key.endianness)) { case 1:j=i^1;break;case 2:j=i^3;break;case 3:j=i^2;break;default:break; }
            hash=(hash^memory[offset+j])*1099511628211ull;
          }
        }
        return hash;
      },false,texture.native_dds_.get());
    } catch(const std::exception& e) { REXLOG_ERROR("Native DDS rejected: {}",e.what()); }
  }
  if(dds && texture.native_dds_ && dds->identity==texture.native_dds_->identity) return true;
  if(texture.native_resource_) {
    native_pending_retirements_.insert(&texture);
    texture.RetireNativeResource(command_processor_.GetCurrentSubmission());
  }
  if(!dds) return false;
  auto* device=command_processor_.GetD3D12Provider().GetDevice();
  ::ch2k8::DDSUpload upload;
  std::shared_ptr<const ::ch2k8::NativeDDSInfo> info;
  try {
    info=std::make_shared<const ::ch2k8::NativeDDSInfo>(*dds);
    upload=::ch2k8::UploadDDS(device,*dds,GetDXGIResourceFormat(key),[&](const auto& to,const auto& from) {
      command_processor_.GetDeferredCommandList().D3DCopyTextureRegion(&to,0,0,0,&from,nullptr);
    });
  } catch(const std::exception& e) { REXLOG_ERROR("Native DDS upload failed: {}",e.what()); return false; }
  native_uploads_.emplace_back(command_processor_.GetCurrentSubmission(),std::move(upload.staging));
  texture.native_resource_=std::move(upload.texture); texture.native_state_=D3D12_RESOURCE_STATE_COPY_DEST;
  // The upload buffer owns the GPU copy source now. Keep only binding metadata,
  // rather than retaining a second compressed payload for every resident texture.
  texture.native_dds_=std::move(info); texture.RetireNativeDescriptors();
  texture.native_allocation_=upload.allocation;
  texture.AccountNativeMemory(upload.allocation);
  REXLOG_INFO("Native DDS upload: {} ({}x{}, {} mip levels; guest tiling bypassed)",texture.native_dds_->path,texture.native_dds_->width,texture.native_dds_->height,texture.native_dds_->mips);
  return true;
}
