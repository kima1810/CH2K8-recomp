import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from prepare_native_gpu_sdk import patch_backend, patch_common, prepare_native_gpu


def test_native_constant_comparison_and_register_side_effect_boundaries(tmp_path):
    compiler = shutil.which('clang++')
    sdk = ROOT/'port/sdk-vulkan/include'
    if not compiler or not (sdk/'rex/graphics/native_constants.h').is_file():
        pytest.skip('Requires the prepared native SDK and clang++')
    source = tmp_path/'constants.cpp'
    source.write_text(r'''
#include <rex/graphics/native_constants.h>
#include <windows.h>
#include <vector>
#include <cstdio>
bool enabled=true, statistics_enabled=false;
bool& FLAGS_ch2k8_native_constants_storage_() { return enabled; }
bool& FLAGS_ch2k8_gpu_stats_storage_() { return statistics_enabled; }
using namespace rex::graphics;
uint32_t state=0x12345678;
uint32_t next() { state^=state<<13;state^=state>>17;state^=state<<5;return state; }
int main() {
 std::vector<uint32_t> registers(0x10000), guest(2048);
 for(unsigned count=0;count<=2048;++count) {
  for(unsigned i=0;i<count;++i) { registers[0x4000+i]=next();guest[i]=__builtin_bswap32(registers[0x4000+i]); }
  if(!Ch2k8ConstantWordsEqual(registers.data()+0x4000,guest.data(),count)) return 2;
  if(count) {
   for(unsigned at : {0u,count/2,count-1}) {
    guest[at]^=0x80000000;
    if(Ch2k8ConstantWordsEqual(registers.data()+0x4000,guest.data(),count)) return 3;
    guest[at]^=0x80000000;
   }
  }
 }
 for(unsigned index=0;index<0x10000;++index) {
  const bool pure=(index>=XE_GPU_REG_SHADER_CONSTANT_000_X && index<=XE_GPU_REG_SHADER_CONSTANT_511_W) ||
    (index>=XE_GPU_REG_SHADER_CONSTANT_BOOL_000_031 && index<=XE_GPU_REG_SHADER_CONSTANT_LOOP_31);
  if(ch2k8::SkipConstantWrite(registers.data(),index,registers[index])!=pure) return 4;
  if(ch2k8::SkipConstantWrite(registers.data(),index,registers[index]^1)) return 5;
 }
 for(uint32_t bits : {0u,0x80000000u,0x7FC00000u,0x7FA12345u,0xFF800000u}) {
  registers[0x4000]=bits;guest[0]=__builtin_bswap32(bits);
  if(!ch2k8::SkipConstantRange(registers.data(),0x4000,guest.data(),1)) return 6;
  guest[0]^=0x01000000;
  if(ch2k8::SkipConstantRange(registers.data(),0x4000,guest.data(),1)) return 7;
 }
 if(ch2k8::IsConstantRange(0x4000,0) || ch2k8::IsConstantRange(0x47FF,2) ||
    ch2k8::IsConstantRange(0x4000,0xFFFFFFFF) || ch2k8::IsConstantRange(0xFFFFFFFF,2)) return 8;
 enabled=false;
 if(ch2k8::SkipConstantWrite(registers.data(),0x4000,registers[0x4000])) return 9;
 // Changed-vector masks include only actual bit changes, including writes
 // starting/ending inside vectors and crossing the vertex/pixel bank boundary.
 for(unsigned first=0;first<2048;++first) {
  const unsigned words=std::min(2048u-first,17u);
  for(unsigned i=0;i<words;++i) guest[i]=__builtin_bswap32(registers[0x4000+first+i]);
  uint64_t changed[8]{};
  Ch2k8ChangedConstantVectors(registers.data()+0x4000+first,guest.data(),first,words,changed);
  for(auto bits:changed) if(bits) return 12;
  guest[words-1]^=1;
  Ch2k8ChangedConstantVectors(registers.data()+0x4000+first,guest.data(),first,words,changed);
  const unsigned vector=(first+words-1)/4;
  for(unsigned i=0;i<8;++i) if(changed[i]!=(i==vector/64 ? uint64_t(1)<<(vector%64) : 0)) return 13;
  uint64_t used[4]{}; used[(vector%256)/64]=uint64_t(1)<<(vector%64);
  if(!Ch2k8ChangedConstantsUsed(used,changed+(vector>=256?4:0),vector%256,vector%256)) return 14;
  used[(vector%256)/64]=0;
  if(Ch2k8ChangedConstantsUsed(used,changed+(vector>=256?4:0),vector%256,vector%256)) return 15;
 }
 // Adjacent guard page proves the SIMD comparison does not over-read its tail.
 auto pages=static_cast<uint8_t*>(VirtualAlloc(nullptr,8192,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
 DWORD old; if(!pages || !VirtualProtect(pages+4096,4096,PAGE_NOACCESS,&old)) return 10;
 for(unsigned count=1;count<32;++count) {
  auto tail=reinterpret_cast<uint32_t*>(pages+4096-count*4);
  for(unsigned i=0;i<count;++i) tail[i]=__builtin_bswap32(registers[0x4000+i]);
  if(!Ch2k8ConstantWordsEqual(registers.data()+0x4000,tail,count)) return 11;
 }
 VirtualFree(pages,0,MEM_RELEASE);
 puts("constant bits, 2049 lengths, register boundaries and guarded tails passed");
}
''')
    executable = tmp_path/'constants.exe'
    compile_result = subprocess.run([compiler, '-std=c++23', '-O2', '-msse4.1',
        '-DNOMINMAX', '-DSPDLOG_FMT_EXTERNAL', '-DSPDLOG_COMPILED_LIB',
        '-I', str(sdk), str(source), '-o', str(executable)], capture_output=True, text=True)
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('backend', ['d3d12', 'vulkan'])
def test_sdk_patch_is_repeatable_and_rejects_unfamiliar_sources(backend):
    source = ROOT/f'work/third_party/rexglue-vulkan/src/graphics/{backend}/command_processor.cpp'
    if not source.is_file():
        pytest.skip('Requires local pinned SDK source')
    patched = source.read_text()
    assert patch_backend(patched, backend) == patched
    # Recover the pinned input using Git, not a hand-maintained test facsimile.
    original = subprocess.check_output(['git', '-C', str(source.parents[3]), 'show',
        f'HEAD:src/graphics/{backend}/command_processor.cpp'], text=True)
    from prepare_native_sync_sdk import patch_sync
    expected = patch_backend(original, backend)
    if '// CH2K8 sync attribution v1' in patched: expected = patch_sync(expected, backend)
    assert expected == patched
    with pytest.raises(ValueError, match='Unrecognized'):
        patch_backend(original.replace('uint32_t index, uint32_t value', 'uint32_t changed, uint32_t value'), backend)


def test_actual_type0_packet_path_matches_original_across_ring_wrap_and_side_effects(tmp_path):
    compiler = shutil.which('clang++')
    sdk = ROOT/'port/sdk-vulkan/include'
    upstream = ROOT/'work/third_party/rexglue-vulkan'
    if not compiler or not upstream.is_dir():
        pytest.skip('Requires prepared SDK and clang++')
    source_text = (upstream/'src/graphics/command_processor.cpp').read_text()
    functions = []
    for name in ('ExecutePacketType0', 'WriteRegisterRangeFromRing'):
        at = source_text.index(('bool' if name.startswith('Execute') else 'void')+' CommandProcessor::'+name+'(')
        end = source_text.index('\n}', at)+2
        functions.append(source_text[at:end].replace('CommandProcessor::', 'Model::'))
    support = r'''
#include <rex/graphics/native_constants.h>
#include <rex/memory/ring_buffer.h>
#include <vector>
#include <cstdio>
bool fast=false;
bool& FLAGS_ch2k8_native_packets_storage_() {return fast;}
bool& FLAGS_ch2k8_packet_compare_storage_() {static bool value=false;return value;}
bool& FLAGS_ch2k8_gpu_stats_storage_() {static bool value=false;return value;}
using namespace rex;
using namespace rex::graphics;
#undef REXGPU_ERROR
#define REXGPU_ERROR(...) (++errors)
struct Model {
 std::vector<uint32_t> regs=std::vector<uint32_t>(65536);
 unsigned writes=0,bulk=0,events=0,errors=0;
 void WriteRegister(uint32_t index,uint32_t value) {regs[index]=value;++writes;if(!ch2k8::IsConstantRange(index,1))++events;}
 void WriteRegistersFromMem(uint32_t start,uint32_t* data,uint32_t count) {
  ++bulk;for(uint32_t i=0;i<count;++i) regs[start+i]=__builtin_bswap32(data[i]);
 }
 bool ExecutePacketType0(memory::RingBuffer*,uint32_t);
 void WriteRegisterRangeFromRing(memory::RingBuffer*,uint32_t,uint32_t);
};
'''
    main = r'''
int main() {
 unsigned checks=0;
 for(unsigned kind=0;kind<6;++kind) for(unsigned count=1;count<=2048;++count) {
  const unsigned capacity=kind==4 ? 16385 : 16384;
  const unsigned offset=kind==5 ? 1 : capacity-4*(1+count%127);
  const unsigned base=kind==1 ? 0x4900 : kind==2 ? 0x47F0 : kind==3 ? 0x1720 : 0x4000;
  const bool one=kind==3;
  std::vector<uint8_t> bytes(capacity);
  memory::RingBuffer a(bytes.data(),capacity),b(bytes.data(),capacity);
  a.set_read_offset(offset);a.set_write_offset(offset);
  for(unsigned i=0;i<count;++i) { uint32_t word=__builtin_bswap32(i*0x117+count);a.Write(word); }
  b.set_read_offset(offset);b.set_write_offset(a.write_offset());
  const uint32_t packet=((count-1)<<16)|base|(one ? 0x8000 : 0);
  Model old,newer;fast=false;
  bool oa=old.ExecutePacketType0(&a,packet);fast=true;bool ob=newer.ExecutePacketType0(&b,packet);
  if(oa!=ob || old.regs!=newer.regs || a.read_offset()!=b.read_offset() || old.events!=newer.events) return 2;
  if(kind==0 && newer.bulk>2) return 3;
  const bool eligible=!one && !(offset&3) && !(capacity&3) && ch2k8::IsConstantRange(base,count);
  if(!eligible && newer.bulk) return 4;
  ++checks;
 }
 std::vector<uint8_t> bytes(64);memory::RingBuffer short_ring(bytes.data(),64);
 short_ring.set_write_offset(4);Model malformed;fast=true;
 if(malformed.ExecutePacketType0(&short_ring,(3<<16)|0x4000) || short_ring.read_offset()!=0 || malformed.errors!=1) return 5;
 printf("%u original/native packet comparisons passed\n",checks);
}
'''
    source = tmp_path/'packets.cpp'
    source.write_text(support+'\n'.join(functions)+main)
    executable = tmp_path/'packets.exe'
    result = subprocess.run([compiler, '-std=c++23', '-O2', '-DNDEBUG', '-msse4.1',
        '-DNOMINMAX', '-DSPDLOG_FMT_EXTERNAL', '-DSPDLOG_COMPILED_LIB', '-I', str(sdk),
        str(source), str(upstream/'src/core/ring_buffer.cpp'), '-o', str(executable)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout+result.stderr
    assert '12288 original/native packet comparisons passed' in result.stdout


def test_common_patch_idempotence_and_unreviewed_changes_fail_before_writes(tmp_path, monkeypatch):
    upstream = ROOT/'work/third_party/rexglue-vulkan'
    if not upstream.is_dir():
        pytest.skip('Requires pinned SDK source')
    originals = {}
    for relative in ('src/graphics/command_processor.cpp',
                     'src/graphics/d3d12/command_processor.cpp',
                     'src/graphics/vulkan/command_processor.cpp'):
        original = subprocess.check_output(['git','-C',str(upstream),'show','HEAD:'+relative],text=True)
        originals[relative] = original
        path = tmp_path/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(original)
    current = patch_common(originals['src/graphics/command_processor.cpp'])
    assert patch_common(current) == current
    assert current.count('REXCVAR_DEFINE_BOOL(ch2k8_native_packets,') == 1
    with pytest.raises(ValueError, match='Unrecognized'):
        patch_common(originals['src/graphics/command_processor.cpp'].replace('uint32_t write_one_reg =', 'uint32_t unfamiliar ='))
    changed = tmp_path/'src/graphics/vulkan/command_processor.cpp'
    changed.write_text(changed.read_text()+'\n// external local change\n')
    before = {p:p.read_bytes() for p in tmp_path.rglob('*.cpp')}
    monkeypatch.setattr(subprocess, 'check_output', lambda args, **kwargs: originals[args[-1].removeprefix('HEAD:')])
    with pytest.raises(ValueError, match='Unreviewed local'):
        prepare_native_gpu(tmp_path)
    assert all(p.read_bytes() == content for p,content in before.items())
