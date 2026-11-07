import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from optimize_codegen import optimize_source, restore_source, dispatch, MARKER, V2_MARKER, scalar_pack, scalar_unpack
from summarize_hot_functions import summarize


def test_store_preserves_byte_order_width_addresses_and_source_aliasing(tmp_path):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('Requires clang++')
    source = tmp_path/'stores.cpp'
    source.write_text(r'''
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>
#include <cstdio>
struct PPCVRegister { uint8_t u8[16]; };
struct Event { uint64_t address; uint8_t value; bool operator==(const Event&) const = default; };
std::vector<Event> events;
bool alias=false;
struct Target {
 uint64_t address;
 void operator=(uint8_t value) {
  events.push_back({address,value});
  if(alias) reinterpret_cast<uint8_t*>(uintptr_t(address))[0]=value;
 }
};
// Reproduce the generated Windows physical-alias address expression, then log
// each byte operation instead of accessing device registers in a unit test.
#define REX_STORE_U8(x,y) (Target{uint64_t(uintptr_t(base)) + uint32_t(x) + ((x)>=0xE0000000u ? 0x1000u : 0u)} = (y))
#include "vector_store_optimized.h"
void baseline(uint8_t* base,uint32_t ea,const PPCVRegister& source) {
 for(size_t i=0;i<(16-(ea&15));++i) REX_STORE_U8(ea+i,source.u8[15-i]);
}
int main() {
 PPCVRegister source{};
 for(unsigned i=0;i<16;++i) source.u8[i]=uint8_t(i*17);
 for(uint32_t page : {0u,0x1000u,0x7FC80000u,0x7FEA0000u,0xDFFFF000u,0xE0000000u,0xFFFFF000u}) {
  for(uint32_t offset=0;offset<4096;++offset) {
   const auto ea=page+offset;
   events.clear();baseline(nullptr,ea,source);const auto expected=events;
   events.clear();Ch2k8StoreVectorLeft(nullptr,ea,source);
   if(events!=expected) return 2;
  }
 }
 // The source can overlap the destination. Each read must follow the preceding
 // volatile write, rather than loading/reversing the entire vector in advance.
 alias=true;
 for(unsigned offset=0;offset<32;++offset) {
  alignas(16) uint8_t a[64],b[64];
  for(unsigned i=0;i<64;++i) a[i]=uint8_t(i*11);
  std::memcpy(b,a,64);
  baseline(a,offset,*reinterpret_cast<PPCVRegister*>(a+16));
  Ch2k8StoreVectorLeft(b,offset,*reinterpret_cast<PPCVRegister*>(b+16));
  if(std::memcmp(a,b,64)) return 3;
 }
 puts("28672 address traces and 32 overlapping-source comparisons passed");
}
''')
    executable = tmp_path/'stores.exe'
    compiled = subprocess.run([compiler, '-std=c++23', '-O2', '-I', str(ROOT/'port/src'),
                               str(source), '-o', str(executable)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '28672 address traces' in result.stdout


def test_v2_upgrade_retains_baseline_and_rejects_changed_store_shape():
    signature = 'DEFINE_REX_FUNC(sub_84723778) {'
    store = '\t// stvlx v1,r3,r4\n\tea = ctx.r3.u32 + ctx.r4.u32;\n\tfor (size_t i = 0; i < (16 - (ea & 0xF)); i++)\n\t\tREX_STORE_U8(ea + i, ctx.v1.u8[15 - i]);'
    body = signature+'\n\tREX_FUNC_PROLOGUE();\n'+'\n'.join(
        scalar_pack(f'v{i}', 'v0', i%2) for i in range(16))+'\n'+scalar_unpack('v22','v23')+'\n'+store+'\n}\n'
    current, _ = optimize_source(body)
    assert current.count('Ch2k8StoreVectorLeft(') == 3
    assert restore_source(current) == body
    start = current.index('static void sub_84723778_store_fast(')
    end = current.index('\n}\n', start)+4
    old = (current[:start]+current[end:]).replace(MARKER+'\n', V2_MARKER+'\n', 1)
    start = old.index('template<bool Count>\nstatic void sub_84723778_geometry_fast(')
    end = old.index('\n}\n', start)+4
    old = old[:start]+old[end:]
    start = old.index('static void sub_84723778_ram_fast(')
    end = old.index('\n}\n', start)+4
    old = old[:start]+old[end:]
    old = old.replace('#include "vector_store_optimized.h"\n', '').replace(
        dispatch(signature, '84723778', 0), dispatch(signature, '84723778', 0, 2))
    assert restore_source(old) == body
    assert optimize_source(old) == (current, 16)
    assert optimize_source(current) == (current, 0)
    with pytest.raises(ValueError, match='unexpected store shape'):
        optimize_source(body.replace('ctx.v1.u8[15 - i]', 'ctx.v1.u8[i]'))


def test_store_csv_variant_is_separate(tmp_path):
    path = tmp_path/'hot.csv'
    path.write_text('elapsed_ms,thread,function,optimized,unpack_optimized,store_optimized,calls,work_units,wall_ns\n'
                    '1000,1,0x84723778,1,1,0,10,100,4000\n'
                    '1000,1,0x84723778,1,1,1,10,100,3000\n')
    result = summarize(path)['0x84723778']
    assert result['pack_unpack']['ns_per_work_unit'] == 40
    assert result['pack_unpack_store']['ns_per_work_unit'] == 30
