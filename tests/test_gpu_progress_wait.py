import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from gpu_wait_codegen import prepare_source,MARKER,SIGNATURE


def compile_cpp(tmp_path,name,source,extra=()):
    compiler=shutil.which('clang++')
    if not compiler:pytest.skip('Requires Clang')
    cpp=tmp_path/(name+'.cpp');cpp.write_text(source)
    executable=tmp_path/(name+('.dll' if '-shared' in extra else '.exe'))
    result=subprocess.run([compiler,'-std=c++23','-O2','-DNOMINMAX',
        '-I',str(ROOT/'port/src'),'-I',str(ROOT/'port/sdk_patches'),
        str(cpp),*map(str,extra),'-o',str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    return executable


def test_progress_generation_handles_early_notifications_timeouts_and_many_waiters(tmp_path):
    program=compile_cpp(tmp_path,'progress',r'''
#include "native_gpu_progress.h"
#include <thread>
#include <vector>
#include <cstdio>
using namespace std::chrono_literals;
int main(){
 rex::graphics::ch2k8::GpuProgress progress;
 if(progress.Wait(progress.Serial(),1ms))return 1;
 auto first=progress.Serial();progress.Notify();
 if(!progress.Wait(first,1ms))return 2;
 for(unsigned trial=0;trial<100;++trial){
  auto before=progress.Serial();std::atomic<unsigned> ready{0},woken{0};
  std::vector<std::thread> threads;
  for(unsigned i=0;i<4;++i)threads.emplace_back([&]{++ready;if(progress.Wait(before,1000ms))++woken;});
  while(ready.load()!=4)std::this_thread::yield();
  progress.Notify();
  for(auto& t:threads)t.join();
  if(woken!=4)return 3;
 }
 puts("early signals, bounded timeout and 400 concurrent waits passed");
}
''')
    checked=subprocess.run([str(program)],capture_output=True,text=True,timeout=20)
    assert checked.returncode==0,checked.stdout+checked.stderr


FAKE_GPU=r'''
#include "native_gpu_progress.h"
std::atomic<unsigned> wait_calls{0};
extern "C" __declspec(dllexport) uint64_t Ch2k8GpuProgressSerialV1(){return rex::graphics::ch2k8::NativeGpuProgress().Serial();}
extern "C" __declspec(dllexport) bool Ch2k8WaitGpuProgressV1(uint64_t serial,uint32_t ms){
 ++wait_calls;return rex::graphics::ch2k8::NativeGpuProgress().Wait(serial,std::chrono::milliseconds(ms>1?1:ms));
}
extern "C" __declspec(dllexport) void TestNotify(){rex::graphics::ch2k8::NativeGpuProgress().Notify();}
extern "C" __declspec(dllexport) unsigned TestWaitCalls(){return wait_calls.load();}
'''


def test_actual_guest_wait_helper_rechecks_words_excludes_devices_and_handles_missing_plugin(tmp_path):
    plugin=compile_cpp(tmp_path,'rexgpu-xenos',FAKE_GPU,('-shared',))
    program=compile_cpp(tmp_path,'waiter',r'''
#include "native_gpu_wait.h"
#include <windows.h>
#include <cstdio>
int main(int argc,char** argv){
 Ch2k8ConfigureGpuWait(true);
 if(argc==1){Ch2k8GpuWait missing;for(int i=0;i<256;i++)missing.Poll(nullptr,0,0,0,0);return 0;}
 auto module=LoadLibraryA(argv[1]);if(!module)return 1;
 auto calls=reinterpret_cast<unsigned(*)()>(GetProcAddress(module,"TestWaitCalls"));
 auto mem=static_cast<uint8_t*>(VirtualAlloc(nullptr,1ull<<32,MEM_RESERVE,PAGE_NOACCESS));
 if(!mem||!VirtualAlloc(mem+0x10000,8192,MEM_COMMIT,PAGE_READWRITE))return 2;
 auto put=[&](uint32_t ea,uint32_t value){*reinterpret_cast<uint32_t*>(mem+ea)=__builtin_bswap32(value);};
 put(0x10000,32);put(0x11000,128);
 Ch2k8GpuWait active;for(unsigned i=0;i<64;i++)active.Poll(mem,0x10000,32,0x11000,128);
 if(calls()!=1)return 3;
 // Never sleep after either the read cursor or the write cursor changed.
 put(0x10000,96);for(unsigned i=0;i<64;i++)active.Poll(mem,0x10000,32,0x11000,128);
 put(0x10000,32);put(0x11000,129);for(unsigned i=0;i<64;i++)active.Poll(mem,0x10000,32,0x11000,128);
 if(calls()!=1)return 4;
 Ch2k8ConfigureGpuWait(false);Ch2k8GpuWait disabled;
 for(unsigned i=0;i<256;i++)disabled.Poll(mem,0x10000,32,0x11000,129);
 if(calls()!=1)return 5;
 Ch2k8ConfigureGpuWait(true);Ch2k8GpuWait device;
 for(unsigned i=0;i<64;i++)device.Poll(mem,0x7FC80000,32,0x11000,129);
 if(calls()!=1)return 6;
 DWORD previous;VirtualProtect(mem+0x10000,4096,PAGE_NOACCESS,&previous);
 Ch2k8GpuWait protected_page;for(unsigned i=0;i<64;i++)protected_page.Poll(mem,0x10000,32,0x11000,129);
 if(calls()!=1)return 7;
 VirtualFree(mem,0,MEM_RELEASE);FreeLibrary(module);
 puts("real helper, bounded wait, changed words, disabled path and page/device exclusions passed");
}
''',(ROOT/'port/src/native_gpu_wait.cpp',))
    for arguments in ([],[str(plugin)]):
        checked=subprocess.run([str(program),*arguments],capture_output=True,text=True,timeout=10)
        assert checked.returncode==0,checked.stdout+checked.stderr


def test_checked_guest_wait_patch_is_idempotent_and_rejects_unknown_bodies():
    candidate=next((p for p in (ROOT/'port/generated/default').glob('*_recomp.*.cpp')
                    if SIGNATURE in p.read_text()),None)
    if not candidate:pytest.skip('Requires generated game code')
    current=candidate.read_text();expected=prepare_source(current)
    assert expected==current and expected.startswith(MARKER)
    start=current.index(SIGNATURE)
    changed=current[:start]+current[start:].replace('ctx.r11.u64 - ctx.r10.u64','ctx.r11.u64 + ctx.r10.u64',1)
    with pytest.raises(ValueError):prepare_source(changed)


def test_complete_counter_wait_retains_context_memory_and_all_original_exit_paths(tmp_path):
    generated=ROOT/'port/generated/default';sdk=ROOT/'port/sdk-vulkan/include'
    if not generated.exists() or not sdk.exists():pytest.skip('Requires generated game/SDK')
    wanted={'sub_84DDA4D0','__savegprlr_29','__restgprlr_29'};bodies={}
    for path in generated.glob('*_recomp.*.cpp'):
        text=path.read_text()
        for name in wanted-bodies.keys():
            signature=f'DEFINE_REX_FUNC({name}) {{'
            if signature in text:
                start=text.index(signature);bodies[name]=text[start:text.index('\n}\n',start)+3]
    assert wanted==bodies.keys()
    plugin=compile_cpp(tmp_path,'rexgpu-xenos',FAKE_GPU,('-shared',))
    prefix=r'''
#include "ch2k8_pch.h"
#include "native_gpu_wait.h"
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <vector>
unsigned polls=0;uint32_t final_cursor=128;
REX_EXTERN(__savegprlr_29);REX_EXTERN(__restgprlr_29);
REX_EXTERN(sub_84DDACE0);REX_EXTERN(sub_84DC9FD0);REX_EXTERN(sub_84DCA290);REX_EXTERN(sub_84DCA000);
DEFINE_REX_FUNC(sub_84DDACE0){}
DEFINE_REX_FUNC(sub_84DC9FD0){}
DEFINE_REX_FUNC(sub_84DCA000){}
DEFINE_REX_FUNC(sub_84DCA290){if(++polls==128)REX_STORE_U32(0x20000,final_cursor);ctx.r3.u64=1;}
'''
    main=r'''
int main(int argc,char** argv){
 if(argc!=2)return 1;auto plugin=LoadLibraryA(argv[1]);if(!plugin)return 2;
 auto wait_calls=reinterpret_cast<unsigned(*)()>(GetProcAddress(plugin,"TestWaitCalls"));
 constexpr size_t bytes=1024*1024;
 auto memory=static_cast<uint8_t*>(VirtualAlloc(nullptr,1ull<<32,MEM_RESERVE,PAGE_NOACCESS));
 if(!memory||!VirtualAlloc(memory,bytes,MEM_COMMIT,PAGE_READWRITE))return 3;
 std::vector<uint8_t> initial(bytes),expected(bytes);
 for(bool wrapping : {false,true})for(uint32_t target : {0u,16u,64u,128u})for(uint32_t flag : {0u,1u}){
  final_cursor=wrapping?0u:128u;
  const uint32_t ticket=target?target+(wrapping?0xFFFFFF80u:0u):0u;
  auto put=[&](uint32_t ea,uint32_t value){value=__builtin_bswap32(value);std::memcpy(initial.data()+ea,&value,4);};
  put(0x10000+10896,0x20000);put(0x10000+10908,final_cursor);put(0x10000+13216,flag);put(0x20000,wrapping?0xFFFFFFA0u:32u);
  PPCContext a{},b{};a.r1.u64=0x80000;a.r3.u64=0x10000;a.r4.u64=ticket;a.r5.u64=17;a.lr=0x12345678;b=a;
  std::memcpy(memory,initial.data(),bytes);polls=0;Ch2k8ConfigureGpuWait(false);sub_84DDA4D0(a,memory);
  auto expected_polls=polls;std::memcpy(expected.data(),memory,bytes);
  std::memcpy(memory,initial.data(),bytes);polls=0;Ch2k8ConfigureGpuWait(true);auto before=wait_calls();sub_84DDA4D0(b,memory);
  if(std::memcmp(&a,&b,sizeof(a))||std::memcmp(expected.data(),memory,bytes)||polls!=expected_polls)return 4;
  if(expected_polls==128 && wait_calls()-before!=2)return 5;
  if(!expected_polls && wait_calls()!=before)return 6;
 }
 VirtualFree(memory,0,MEM_RELEASE);FreeLibrary(plugin);puts("16 complete context/memory comparisons and native timeout paths passed");
}
'''
    program=compile_cpp(tmp_path,'whole_wait',prefix+'\n'.join(bodies.values())+main,
        ('-msse4.1','-DNOMINMAX','-DSPDLOG_FMT_EXTERNAL','-DSPDLOG_COMPILED_LIB',
         '-I',sdk,'-I',generated,ROOT/'port/src/native_gpu_wait.cpp'))
    checked=subprocess.run([str(program),str(plugin)],capture_output=True,text=True,timeout=20)
    assert checked.returncode==0,checked.stdout+checked.stderr
