import subprocess
import sys
import shutil
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_native_assets_sdk import prepare_native_assets


def test_pinned_native_asset_patch_is_complete_and_idempotent(tmp_path):
    source=ROOT/'work/third_party/rexglue-vulkan'
    if not (source/'.git').exists():pytest.skip('Requires local pinned source SDK')
    files=['include/rex/graphics/shared_memory.h','include/rex/graphics/d3d12/texture_cache.h',
           'src/graphics/d3d12/texture_cache.cpp','src/filesystem/devices/host_path_device.cpp']
    for name in files:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(subprocess.check_output(['git','-C',str(source),'show','HEAD:'+name]))
    prepare_native_assets(tmp_path)
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    prepare_native_assets(tmp_path)
    assert before=={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert b'TryLoadNativeDDS' in before[Path(files[2])]
    assert b'NativeRangeWrittenByGpu' in before[Path(files[0])]
    assert b'native_revision' in before[Path(files[1])]
    assert b'native_retired_resources_' in before[Path(files[1])]


def test_native_dds_payload_release_and_fenced_retirement(tmp_path):
    compiler=shutil.which('clang++') or 'C:/Program Files/LLVM/bin/clang++.exe'
    if not Path(compiler).exists():pytest.skip('Requires C++ compiler')
    sdk=ROOT/'work/third_party/rexglue-vulkan'
    if not (sdk/'.git').exists():pytest.skip('Requires pinned SDK')
    for name in ['include/rex/graphics/shared_memory.h','include/rex/graphics/d3d12/texture_cache.h',
                 'src/graphics/d3d12/texture_cache.cpp','src/filesystem/devices/host_path_device.cpp']:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(subprocess.check_output(['git','-C',str(sdk),'show','HEAD:'+name]))
    prepare_native_assets(tmp_path)
    header=(tmp_path/'include/rex/graphics/d3d12/texture_cache.h').read_text()
    methods=header[header.index('    // CH2K8 native DDS retirement v2'):header.index('    void AccountNativeMemory')]
    harness=r'''
#include "native_dds.h"
#include <cassert>
#include <map>
using ID3D12Resource=int;
namespace Microsoft::WRL { template<class T> using ComPtr=std::shared_ptr<T>; }
struct D3D12TextureCache {
  std::vector<uint32_t> released;
  void ReleaseTextureDescriptor(uint32_t id) { released.push_back(id); }
};
struct Texture {
  uint64_t usage=4096,native_revision_=0;
  std::shared_ptr<const ch2k8::NativeDDSInfo> native_dds_;
  std::shared_ptr<int> native_resource_;
  std::map<int,uint32_t> srv_descriptors_;
  uint64_t GetHostMemoryUsage() const { return usage; }
  void SetHostMemoryUsage(uint64_t bytes) { usage=bytes; }
METHODS
};
int main(int argc,char** argv) {
  Texture texture; D3D12TextureCache cache;
  for(uint64_t i=1;i<=1000;++i) {
    auto resource=std::make_shared<int>(42);std::weak_ptr<int> alive=resource;
    texture.native_resource_=std::move(resource);
    texture.native_allocation_=65536;texture.usage+=65536;
    texture.srv_descriptors_[0]=uint32_t(i);
    texture.RetireNativeResource(i);
    assert(!texture.native_resource_ && texture.srv_descriptors_.empty());
    texture.CollectNativeRetired(cache,i-1);
    assert(!alive.expired() && texture.usage==4096+65536);
    assert(cache.released.size()==i-1);
    texture.CollectNativeRetired(cache,i);
    assert(alive.expired() && texture.usage==4096);
    assert(texture.native_retired_resources_.empty());
    assert(cache.released.size()==i && cache.released.back()==i);
    texture.CollectNativeRetired(cache,i); // No duplicate releases/accounting.
    assert(cache.released.size()==i && texture.usage==4096);
  }
  // Mixed submissions must collect only the completed allocation.
  for(uint64_t submission:{2000u,2002u}) {
    texture.native_resource_=std::make_shared<int>(1);
    texture.native_allocation_=65536;texture.usage+=65536;
    texture.srv_descriptors_[0]=uint32_t(submission);
    texture.RetireNativeResource(submission);
  }
  texture.CollectNativeRetired(cache,2001);
  assert(texture.usage==4096+65536 && texture.native_retired_resources_.size()==1);
  assert(cache.released.back()==2000);
  texture.CollectNativeRetired(cache,2002);
  assert(texture.usage==4096 && texture.native_retired_resources_.empty());
  assert(cache.released.back()==2002);
  const auto root=std::filesystem::path(argv[1]);
  std::vector<uint8_t> bytes(160,7);
  std::fill(bytes.begin(),bytes.begin()+128,0);
  auto put=[&](size_t off,uint32_t n){for(unsigned i=0;i<4;++i)bytes[off+i]=uint8_t(n>>(8*i));};
  std::copy_n("DDS ",4,bytes.begin());put(4,124);put(12,8);put(16,8);
  put(76,32);put(80,4);put(84,0x31545844);
  {std::ofstream out(root/"test.dds",std::ios::binary);out.write(reinterpret_cast<char*>(bytes.data()),bytes.size());}
  {std::ofstream out(root/"native_dds.index");out<<"CH2K8_DDS_V1\n4 4 18 0000000000000001\ttest.dds\n";}
  ch2k8::NativeDDSCatalog catalog(root);
  auto payload=catalog.Find(4,4,18,[]{return 1;});assert(payload && payload->data.size()==160);
  auto info=std::make_shared<const ch2k8::NativeDDSInfo>(*payload);
  std::weak_ptr<const ch2k8::NativeDDS> alive=payload;payload.reset();assert(alive.expired());
  std::filesystem::remove(root/"test.dds"); // Resident path must not touch disk.
  auto resident=catalog.Find(4,4,18,[]{return 1;},false,info.get());
  assert(resident && resident->data.empty() && resident->width==8 && resident->mips==1);
  assert(!catalog.Find(4,4,18,[]{return 2;},false,info.get()));
  bool rejected=false;
  try { catalog.Find(4,4,18,[]{return 1;}); } catch(const std::exception&) { rejected=true; }
  assert(rejected);
}
'''.replace('METHODS',methods)
    source=tmp_path/'memory.cpp';source.write_text(harness)
    executable=tmp_path/'memory.exe'
    result=subprocess.run([compiler,'-std=c++20','-O2','-I',str(ROOT/'port/src'),str(source),'-o',str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    result=subprocess.run([str(executable),str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
