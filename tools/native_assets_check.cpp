// Standalone asset/GPU checks. Does not load the XEX, runtime or game code.
#include "../port/src/loose_archive.h"
#include "../port/src/native_dds_upload.h"
#include <dxgi1_6.h>
#include <windows.h>
#include <iostream>

using Microsoft::WRL::ComPtr;
static void Check(HRESULT result) { if(FAILED(result)) throw std::runtime_error("D3D12 check failed: "+std::to_string(uint32_t(result))); }

static void GPUCheck(bool warp) {
  ComPtr<IDXGIFactory4> factory;Check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)));
  ComPtr<IDXGIAdapter1> adapter;
  if(warp) Check(factory->EnumWarpAdapter(IID_PPV_ARGS(&adapter)));
  else Check(factory->EnumAdapters1(0,&adapter));
  DXGI_ADAPTER_DESC1 adapter_desc;Check(adapter->GetDesc1(&adapter_desc));
  std::wcout<<L"GPU upload check: "<<adapter_desc.Description<<L"\n";
  ComPtr<ID3D12Device> device;Check(D3D12CreateDevice(adapter.Get(),D3D_FEATURE_LEVEL_11_0,IID_PPV_ARGS(&device)));
  ComPtr<ID3D12CommandQueue> queue;D3D12_COMMAND_QUEUE_DESC qdesc={};Check(device->CreateCommandQueue(&qdesc,IID_PPV_ARGS(&queue)));
  for(uint32_t format:{18u,19u,20u,59u,49u}) for(uint32_t size:{64u,2048u}) {
    const auto bpp=(format==18 || format==59)?8u:16u;
    auto put=[](std::vector<uint8_t>& b,size_t off,uint32_t v){for(size_t i=0;i<4;++i)b[off+i]=uint8_t(v>>(i*8));};
    std::vector<uint8_t> bytes(128);std::memcpy(bytes.data(),"DDS ",4);
    put(bytes,4,124);put(bytes,12,size);put(bytes,16,size);put(bytes,28,size==64?7:1);put(bytes,76,32);put(bytes,80,4);
    put(bytes,84,format==18?0x31545844:format==19?0x33545844:format==20?0x35545844:format==49?0x32495441:0x31495441);
    for(uint32_t mip=0;mip<(size==64?7u:1u);++mip) {
      auto n=size_t((std::max(size>>mip,1u)+3)/4)*((std::max(size>>mip,1u)+3)/4)*bpp;
      for(size_t i=0;i<n;++i)bytes.push_back(uint8_t(i*31+mip*17));
    }
    auto dds=ch2k8::NativeDDS::Parse(std::move(bytes),size/2,size/2,format);
    ComPtr<ID3D12CommandAllocator> allocator;Check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,IID_PPV_ARGS(&allocator)));
    ComPtr<ID3D12GraphicsCommandList> commands;Check(device->CreateCommandList(0,D3D12_COMMAND_LIST_TYPE_DIRECT,allocator.Get(),nullptr,IID_PPV_ARGS(&commands)));
    auto upload=ch2k8::UploadDDS(device.Get(),dds,format==18?DXGI_FORMAT_BC1_TYPELESS:format==19?DXGI_FORMAT_BC2_TYPELESS:format==20?DXGI_FORMAT_BC3_TYPELESS:format==49?DXGI_FORMAT_BC5_TYPELESS:DXGI_FORMAT_BC4_TYPELESS,
      [&](const auto& to,const auto& from){commands->CopyTextureRegion(&to,0,0,0,&from,nullptr);});
    auto desc=upload.texture->GetDesc();
    if(desc.Width!=size || desc.Height!=size || desc.MipLevels!=dds.mips)throw std::runtime_error("Wrong native DDS resource dimensions");
    D3D12_RESOURCE_BARRIER barrier={};barrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition={upload.texture.Get(),D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,D3D12_RESOURCE_STATE_COPY_DEST,D3D12_RESOURCE_STATE_COPY_SOURCE};commands->ResourceBarrier(1,&barrier);
    std::vector<D3D12_PLACED_SUBRESOURCE_FOOTPRINT> layouts(dds.mips);std::vector<UINT> rows(dds.mips);std::vector<UINT64> widths(dds.mips);UINT64 total=0;
    device->GetCopyableFootprints(&desc,0,dds.mips,0,layouts.data(),rows.data(),widths.data(),&total);
    D3D12_HEAP_PROPERTIES heap={};heap.Type=D3D12_HEAP_TYPE_READBACK;
    D3D12_RESOURCE_DESC bd={};bd.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;bd.Width=total;bd.Height=1;bd.DepthOrArraySize=1;bd.MipLevels=1;bd.SampleDesc.Count=1;bd.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    ComPtr<ID3D12Resource> readback;Check(device->CreateCommittedResource(&heap,D3D12_HEAP_FLAG_NONE,&bd,D3D12_RESOURCE_STATE_COPY_DEST,nullptr,IID_PPV_ARGS(&readback)));
    for(uint32_t mip=0;mip<dds.mips;++mip) {
      D3D12_TEXTURE_COPY_LOCATION to={};to.pResource=readback.Get();to.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;to.PlacedFootprint=layouts[mip];
      D3D12_TEXTURE_COPY_LOCATION from={};from.pResource=upload.texture.Get();from.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;from.SubresourceIndex=mip;
      commands->CopyTextureRegion(&to,0,0,0,&from,nullptr);
    }
    Check(commands->Close());ID3D12CommandList* lists[]={commands.Get()};queue->ExecuteCommandLists(1,lists);
    ComPtr<ID3D12Fence> fence;Check(device->CreateFence(0,D3D12_FENCE_FLAG_NONE,IID_PPV_ARGS(&fence)));
    HANDLE event=CreateEventW(nullptr,FALSE,FALSE,nullptr);if(!event)throw std::runtime_error("Cannot create GPU check event");
    Check(queue->Signal(fence.Get(),1));Check(fence->SetEventOnCompletion(1,event));auto wait=WaitForSingleObject(event,30000);CloseHandle(event);
    if(wait!=WAIT_OBJECT_0)throw std::runtime_error("GPU check fence timeout");
    uint8_t* result=nullptr;D3D12_RANGE range={0,size_t(total)};Check(readback->Map(0,&range,reinterpret_cast<void**>(&result)));
    size_t source=128;
    for(uint32_t mip=0;mip<dds.mips;++mip)for(UINT y=0;y<rows[mip];++y){
      if(std::memcmp(result+layouts[mip].Offset+size_t(y)*layouts[mip].Footprint.RowPitch,dds.data.data()+source,size_t(widths[mip])))throw std::runtime_error("Native DDS GPU readback differs");
      source+=size_t(widths[mip]);
    }
    D3D12_RANGE no_write={0,0};readback->Unmap(0,&no_write);
    std::cout<<"BC"<<(format==49?5:format==59?4:format-17)<<" "<<size<<"x"<<size<<" "<<dds.mips<<" mips: exact GPU round trip\n";
  }
}

int main(int argc,char** argv) {
  try {
    if(argc==2 && std::string(argv[1])=="gpu") { GPUCheck(false);GPUCheck(true);return 0; }
    if(argc<3) throw std::runtime_error("Usage: ch2k8_assets_check gpu | verify ROOT SOURCE | catalog ROOT");
    const auto root=std::filesystem::u8path(argv[2]);
    if(std::string(argv[1])=="catalog") {
      ch2k8::NativeDDSCatalog catalog(root);std::ifstream index(root/"native_dds.index");std::string line;std::getline(index,line);size_t count=0,active=0;
      while(std::getline(index,line)) {
        if(line.empty())continue;std::istringstream row(line);uint32_t w,h,f;std::string hash;row>>w>>h>>f>>hash;
        if(catalog.Find(w,h,f,[&]{return std::stoull(hash,nullptr,16);}))++active;
        if(!row || !catalog.Find(w,h,f,[&]{return std::stoull(hash,nullptr,16);},true))throw std::runtime_error("Catalog DDS match failed");++count;
      }
      std::cout<<count<<" DDS identities validated with native parser; "<<active<<" active replacements\n";return 0;
    }
    if(std::string(argv[1])!="verify" || argc!=4)throw std::runtime_error("Invalid command");
    ch2k8::LooseArchive archive(root);std::vector<uint8_t> expected(8<<20),actual(expected.size());uint64_t total=0;
    for(const auto& part:archive.parts()) {
      std::ifstream source(std::filesystem::u8path(argv[3])/part.path,std::ios::binary);
      if(!source)throw std::runtime_error("Missing original source part");
      for(uint64_t at=0;at<part.size;) {
        auto n=size_t(std::min<uint64_t>(expected.size(),part.size-at));
        if(!source.read(reinterpret_cast<char*>(expected.data()),std::streamsize(n)))throw std::runtime_error("Short original archive read");
        if(archive.Read(part.offset+at,std::span(actual).first(n))!=n || std::memcmp(actual.data(),expected.data(),n))throw std::runtime_error("Loose archive differs at "+std::to_string(part.offset+at));
        at+=n;total+=n;
      }
      std::cout<<part.path<<": exact\n";
    }
    // Cross-part and EOF behavior, not just aligned reads.
    for(size_t i=1;i<archive.parts().size();++i)if(archive.Read(archive.parts()[i].offset-37,std::span(actual).first(79))!=79)throw std::runtime_error("Cross-part short read");
    if(archive.Read(total,std::span(actual).first(1))!=0)throw std::runtime_error("EOF read failed");
    std::cout<<total<<" virtual bytes identical; boundary/EOF checks passed\n";return 0;
  } catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
