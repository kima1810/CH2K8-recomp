#pragma once
#include "native_dds.h"
#include <d3d12.h>
#include <wrl/client.h>
#include <cstring>

namespace ch2k8 {
struct DDSUpload {
  Microsoft::WRL::ComPtr<ID3D12Resource> texture,staging;
  uint64_t allocation=0;
};
// Shared by the runtime and the standalone GPU round-trip check. The caller
// retains staging until its submission fence completes.
template<class Copy>
DDSUpload UploadDDS(ID3D12Device* device,const NativeDDS& dds,DXGI_FORMAT format,Copy&& copy) {
  const auto first=dds.format==18?DXGI_FORMAT_BC1_TYPELESS:dds.format==19?DXGI_FORMAT_BC2_TYPELESS:dds.format==20?DXGI_FORMAT_BC3_TYPELESS:dds.format==49?DXGI_FORMAT_BC5_TYPELESS:dds.format==59?DXGI_FORMAT_BC4_TYPELESS:DXGI_FORMAT_UNKNOWN;
  if(first==DXGI_FORMAT_UNKNOWN || uint32_t(format)<uint32_t(first) || uint32_t(format)>uint32_t(first)+2)
    throw std::runtime_error("DDS upload resource format does not match its BC payload");
  DDSUpload result;
  D3D12_RESOURCE_DESC desc={};
  desc.Dimension=D3D12_RESOURCE_DIMENSION_TEXTURE2D;
  desc.Width=dds.width; desc.Height=dds.height; desc.DepthOrArraySize=1; desc.MipLevels=UINT16(dds.mips);
  desc.Format=format; desc.SampleDesc.Count=1;
  D3D12_HEAP_PROPERTIES heap={}; heap.Type=D3D12_HEAP_TYPE_DEFAULT;
  if(FAILED(device->CreateCommittedResource(&heap,D3D12_HEAP_FLAG_NONE,&desc,D3D12_RESOURCE_STATE_COPY_DEST,nullptr,IID_PPV_ARGS(&result.texture))))
    throw std::runtime_error("Cannot allocate native DDS texture");
  std::vector<D3D12_PLACED_SUBRESOURCE_FOOTPRINT> layouts(dds.mips);
  std::vector<UINT> rows(dds.mips);
  std::vector<UINT64> row_bytes(dds.mips);
  UINT64 total=0;
  device->GetCopyableFootprints(&desc,0,dds.mips,0,layouts.data(),rows.data(),row_bytes.data(),&total);
  D3D12_RESOURCE_DESC buffer={}; buffer.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;buffer.Width=total;
  buffer.Height=1;buffer.DepthOrArraySize=1;buffer.MipLevels=1;buffer.SampleDesc.Count=1;buffer.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
  heap.Type=D3D12_HEAP_TYPE_UPLOAD;
  if(FAILED(device->CreateCommittedResource(&heap,D3D12_HEAP_FLAG_NONE,&buffer,D3D12_RESOURCE_STATE_GENERIC_READ,nullptr,IID_PPV_ARGS(&result.staging))))
    throw std::runtime_error("Cannot allocate native DDS upload buffer");
  uint8_t* mapped=nullptr; D3D12_RANGE no_read={0,0};
  if(FAILED(result.staging->Map(0,&no_read,reinterpret_cast<void**>(&mapped)))) throw std::runtime_error("Cannot map DDS upload buffer");
  size_t source=128;
  for(uint32_t mip=0;mip<dds.mips;++mip) {
    for(UINT y=0;y<rows[mip];++y) {
      std::memcpy(mapped+layouts[mip].Offset+size_t(y)*layouts[mip].Footprint.RowPitch,dds.data.data()+source,size_t(row_bytes[mip]));
      source+=size_t(row_bytes[mip]);
    }
  }
  result.staging->Unmap(0,nullptr);
  for(uint32_t mip=0;mip<dds.mips;++mip) {
    D3D12_TEXTURE_COPY_LOCATION from={};from.pResource=result.staging.Get();from.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;from.PlacedFootprint=layouts[mip];
    D3D12_TEXTURE_COPY_LOCATION to={};to.pResource=result.texture.Get();to.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;to.SubresourceIndex=mip;
    copy(to,from);
  }
  result.allocation=device->GetResourceAllocationInfo(0,1,&desc).SizeInBytes;
  return result;
}
} // namespace ch2k8
