// Opens the real SDK VFS and folder device, without loading or launching a game.
#include "../port/src/loose_archive.h"
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <future>
#include <array>
#include <cctype>
#include <iostream>

std::unique_ptr<rex::filesystem::Device> Ch2k8CreateLooseDevice(const std::filesystem::path& root);

int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::runtime_error("Usage: ch2k8_vfs_check ROOT");
    rex::InitLoggingEarly();
    using namespace rex::filesystem;using rex::X_STATUS;
    const auto path=std::filesystem::u8path(argv[1]);
    ch2k8::LooseArchive expected(path);
    VirtualFileSystem vfs;
    if(!vfs.RegisterDevice(Ch2k8CreateLooseDevice(path)))throw std::runtime_error("Device registration failed");
    vfs.RegisterSymbolicLink("game:","\\Device\\CH2K8Assets");vfs.RegisterSymbolicLink("d:","\\Device\\CH2K8Assets");
    vfs.RegisterSymbolicLink("\\Device\\Harddisk0\\Partition1","\\Device\\CH2K8Assets");
    auto* root=vfs.ResolvePath("game:\\");
    if(!root || root->child_count()!=expected.parts().size()+1)throw std::runtime_error("Directory enumeration misses virtual parts/XEX");
    for(const auto& part:expected.parts()) {
      if(vfs.ResolvePath("\\Device\\Harddisk0\\Partition1\\"+part.path)!=vfs.ResolvePath("game:\\"+part.path))throw std::runtime_error("Physical device alias differs");
      for(bool relative:{false,true}) {
        File* file=nullptr;FileAction action;
        auto name=relative?part.path:"d:\\"+part.path;
        std::transform(name.begin(),name.end(),name.begin(),[](unsigned char c){return char(std::tolower(c));});
        if(vfs.OpenFile(relative?root:nullptr,name,FileDisposition::kOpen,FileAccess::kGenericRead,false,true,&file,&action)!=X_STATUS_SUCCESS || !file)
          throw std::runtime_error("SDK cannot open virtual part: "+name);
        std::vector<std::future<void>> workers;
        for(size_t worker=0;worker<4;++worker)workers.push_back(std::async(std::launch::async,[&,worker] {
          for(size_t i=0;i<12;++i) {
            const size_t offset=size_t((worker*2147483+i*3719)%(part.size-4096));
            std::array<uint8_t,4096> actual,reference;size_t read=0;
            expected.Read(part.offset+offset,reference);
            if(file->ReadSync(actual,offset,&read)!=X_STATUS_SUCCESS || read!=actual.size() || actual!=reference)
              throw std::runtime_error("Concurrent VFS read mismatch");
          }
        }));
        for(auto& worker:workers)worker.get();
        std::array<uint8_t,97> tail;size_t read=0;
        if(file->ReadSync(tail,size_t(part.size-17),&read)!=X_STATUS_SUCCESS || read!=17)throw std::runtime_error("Partial VFS EOF read differs");
        if(file->ReadSync(tail,size_t(part.size),&read)!=X_STATUS_END_OF_FILE || read)throw std::runtime_error("VFS EOF status differs");
        file->Destroy();
      }
      File* writable=nullptr;
      if(vfs.ResolvePath("game:\\"+part.path)->Open(FileAccess::kGenericWrite,&writable)!=X_STATUS_ACCESS_DENIED || writable)
        throw std::runtime_error("Virtual archive accepted a write");
    }
    std::cout<<expected.parts().size()<<" virtual parts: absolute/relative case-insensitive opens, enumeration, concurrent reads, EOF and read-only checks passed\n";
    return 0;
  } catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
