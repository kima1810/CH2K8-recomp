import shutil
import subprocess
import sys
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from optimize_codegen import optimize_source, scalar_pack, scalar_unpack, TARGETS, restore_source
from catalog_hot_functions import catalog
from summarize_hot_functions import summarize


def test_fast_variants_are_scoped_idempotent_and_reject_unreviewed_shapes():
    body = 'DEFINE_REX_FUNC(sub_84723778) {\n\tREX_FUNC_PROLOGUE();\n' + '\n'.join(
        scalar_pack(f'v{i}', 'v0', i % 2) for i in range(16)) + '\n' + scalar_unpack('v22', 'v23') + '\n}\n'
    transformed, count = optimize_source(body)
    assert count == 16
    assert transformed.count('Ch2k8PackBiased64(') == 80
    assert transformed.count('Ch2k8UnpackBiased64(') == 4
    assert transformed.count('Ch2k8HotScope hot(') == 6
    assert optimize_source(transformed) == (transformed, 0)
    assert restore_source(transformed) == body
    unrelated = body.replace('sub_84723778', 'sub_12345678')
    assert optimize_source(unrelated) == (unrelated, 0)
    with pytest.raises(ValueError, match='unexpected pack shape'):
        optimize_source(body.replace('0x40380001u', '0x40380000u', 1))


def test_integer_pack_matches_baseline_at_boundaries_random_bits_and_aliases(tmp_path):
    compiler = shutil.which('clang++')
    sdk = ROOT/'port/sdk/include'
    if not compiler or not sdk.exists():
        pytest.skip('Requires clang++ and local SDK headers')
    executable = tmp_path/'benchmark.exe'
    compilation = subprocess.run([compiler, '-std=c++23', '-O3', '-msse4.1',
        '-DNOMINMAX', '-DSPDLOG_FMT_EXTERNAL', '-DSPDLOG_COMPILED_LIB',
        '-I', str(ROOT/'port/src'), '-I', str(sdk),
        str(ROOT/'tools/benchmark_vector_pack.cpp'), '-o', str(executable)],
        capture_output=True, text=True)
    assert compilation.returncode == 0, compilation.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'validated_vectors,317848' in result.stdout
    # Timing is recorded for research, never asserted as a flaky pass condition.
    assert 'trial,baseline_ns,optimized_ns' in result.stdout


def test_local_hot_variants_have_complete_pack_coverage():
    generated = ROOT/'port/generated/default'
    if not generated.is_dir():
        pytest.skip('Requires local generated game code')
    for address in TARGETS:
        candidates = [p.read_text() for p in generated.glob('*_recomp.*.cpp')
                      if f'static void sub_{address}_fast(' in p.read_text()]
        assert len(candidates) == 1
        text = candidates[0]
        start = text.index(f'static void sub_{address}_fast(')
        end = text.index('\n}\n', start)
        assert text[start:end].count('Ch2k8PackBiased64(') == 16
        assert f'DEFINE_REX_FUNC(sub_{address})' in text


def test_catalog_counts_self_loop_and_excludes_adjacent_fast_copy(tmp_path):
    source = tmp_path/'test_recomp.0.cpp'
    source.write_text('''DEFINE_REX_FUNC(sub_12345678) {
loc_12345678:
\t// stvlx v0,r3,r4
\tif (condition) goto loc_12345678;
}
static void sub_12345678_fast() {
\t// stvlx v0,r3,r4
}
DEFINE_REX_FUNC(sub_12345690) {
\tsub_12345678(ctx, base);
}
''')
    rows = list(catalog(tmp_path, ['12345678']))
    assert rows[0]['stvlx_sites'] == 1
    assert rows[0]['backward_branches'] == 1
    assert rows[0]['callers'] == '0x12345690'


def test_hot_summary_weights_elapsed_time_by_total_work(tmp_path):
    path = tmp_path/'hot.csv'
    path.write_text('elapsed_ms,thread,function,optimized,calls,work_units,wall_ns\n'
                    '1000,1,0x84723778,0,2,10,100\n'
                    '2000,1,0x84723778,0,8,90,900\n'
                    '2000,1,0x84723778,1,10,100,700\n')
    result = summarize(path, 0, 3)['0x84723778']
    assert result['baseline']['ns_per_work_unit'] == 10
    assert result['optimized']['ns_per_work_unit'] == 7
    assert result['baseline']['calls'] == 10


def test_complete_generated_hot_functions_preserve_context_and_guest_writes(tmp_path):
    compiler = shutil.which('clang++')
    generated = ROOT/'port/generated/default'
    sdk = ROOT/'port/sdk/include'
    if not compiler or not generated.exists() or not sdk.exists():
        pytest.skip('Requires clang++ and local generated game/SDK')
    wanted = {f'sub_{a}' for a in TARGETS}
    bodies = {}
    fast = {}
    # Collect only required functions; no generated code is committed.
    for path in generated.glob('*_recomp.*.cpp'):
        text = path.read_text()
        for address in TARGETS:
            signature = f'static void sub_{address}_fast('
            if signature in text:
                start = text.index(signature)
                fast[address] = text[start:text.index('\n}\n', start)+3]
                signature = f'static void sub_{address}_unpack_fast('
                start = text.index(signature)
                fast[address+'_unpack'] = text[start:text.index('\n}\n', start)+3]
                signature = f'static void sub_{address}_store_fast('
                start = text.index(signature)
                fast[address+'_store'] = text[start:text.index('\n}\n', start)+3]
                signature = f'static void sub_{address}_ram_fast('
                start = text.index(signature)
                fast[address+'_ram'] = text[start:text.index('\n}\n', start)+3]
                signature = f'static void sub_{address}_geometry_fast('
                start = text.index(signature)
                fast[address+'_geometry'] = 'template<bool Count>\n'+text[start:text.index('\n}\n', start)+3]
                start = text.index(f'DEFINE_REX_FUNC(sub_{address}) {{')
                body = text[start:text.index('\n}\n', start)+3]
                bodies[f'sub_{address}'] = body
                wanted.update(re.findall(r'\t(\w+)\(ctx, base\);', body))
    wanted = {name for name in wanted if not name.endswith('_fast')}
    for path in generated.glob('*_recomp.*.cpp'):
        text = path.read_text()
        for name in wanted - bodies.keys():
            signature = f'DEFINE_REX_FUNC({name}) {{'
            if signature in text:
                start = text.index(signature)
                bodies[name] = text[start:text.index('\n}\n', start)+3]
    assert wanted <= bodies.keys()
    header = '#include "ch2k8_pch.h"\n#include "packed_vector_optimized.h"\n#include "vector_store_optimized.h"\n'
    declarations = '\n'.join(f'REX_EXTERN({name});' for name in bodies)
    support = '''
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <vector>
bool selected = false;
bool selected_unpack = false;
bool selected_store = false;
bool selected_ram = false;
bool selected_batch = true;
bool selected_profile = true;
bool inject_stack_load = false;
uint32_t injected_address = 0, injected_value = 0;
uint64_t last_wide = 0, last_bytes = 0;
inline uint32_t Load32ForTest(uint8_t *base, uint32_t address) {
 if(inject_stack_load && address==injected_address) return injected_value;
 auto host=base+uint64_t(address)+(address>=0xE0000000u?4096:0);
 return __builtin_bswap32(*reinterpret_cast<volatile uint32_t*>(host));
}
#undef REX_LOAD_U32
#define REX_LOAD_U32(address) Load32ForTest(base,uint32_t(address))
bool Ch2k8SelectFastVectorPack(unsigned) { return selected; }
bool Ch2k8SelectFastVectorUnpack(unsigned) { return selected_unpack; }
bool Ch2k8SelectFastVectorStore(unsigned) { return selected_store; }
bool Ch2k8SelectFastRamStore(unsigned) { return selected_ram; }
bool Ch2k8SelectGeometryBatch(unsigned) { return selected_batch; }
bool Ch2k8HotProfilingEnabled() { return selected_profile; }
Ch2k8HotScope::Ch2k8HotScope(unsigned,uint32_t,uint8_t*,bool,bool,bool,bool,const uint64_t* counts) : ram_counts_(counts) {}
Ch2k8HotScope::~Ch2k8HotScope() {last_wide=ram_counts_?ram_counts_[0]:0;last_bytes=ram_counts_?ram_counts_[1]:0;}
'''
    main = '''
int main() {
 constexpr size_t bytes=2*1024*1024;
 auto memory=static_cast<uint8_t*>(VirtualAlloc(nullptr,1ull<<32,MEM_RESERVE,PAGE_NOACCESS));
 if(!memory || !VirtualAlloc(memory,bytes,MEM_COMMIT,PAGE_READWRITE)) return 3;
 std::vector<uint8_t> initial(bytes), expected(bytes);
 PPCFunc* functions[]={sub_84723778,sub_84723CC0,sub_84724930};
 unsigned guarded_checks=0;
 for(unsigned f=0;f<3;++f) for(unsigned trial=0;trial<28;++trial) {
  uint32_t seed=0x6E624EB7+trial;
  for(auto &byte:initial) { seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;byte=trial<12 ? uint8_t(seed) : uint8_t(0x30|(seed&7)); }
  auto put=[&](uint32_t at,uint32_t value) {value=__builtin_bswap32(value);std::memcpy(initial.data()+at,&value,4);};
  const uint32_t job=0x10000,groups=1+trial%3,units=1+trial%4;
  put(job,groups<<1); put(job+4,(units<<19)|(units<<3));
  put(job+24,0x30000);put(job+32,0x30000);put(job+36,0x40000);
  put(job+116,0x60000+(trial<12 ? (trial%4)*4 : trial-12));
  for(uint32_t group=0;group<groups;++group) put(0x30004+group*12,(units<<16)|(group*128));
  PPCContext a{},b{};a.r1.u64=0x180000;a.r3.u64=job;a.lr=0x12345678;
  a.fpscr.csr=0x1F80;const auto initial_context=a;b=a;
  std::memcpy(memory,initial.data(),bytes);simde_mm_setcsr(0x1F80);selected=false;
  functions[f](a,memory);std::memcpy(expected.data(),memory,bytes);
  for(unsigned variant=0;variant<6;++variant) {
   b=initial_context;
   std::memcpy(memory,initial.data(),bytes);simde_mm_setcsr(0x1F80);selected=true;selected_unpack=variant!=0;selected_store=variant>=2;selected_ram=variant>=3;selected_batch=variant!=3;selected_profile=variant!=5;
   functions[f](b,memory);
   if(std::memcmp(&a,&b,sizeof(a)) || std::memcmp(expected.data(),memory,bytes)) {
    printf("Mismatch function=%u trial=%u variant=%u\\n",f,trial,variant);return 2;
   }
  }
  if(f==2 && trial>=12 && trial%4==0) {
   for(unsigned slot : {356u,364u}) for(uint32_t value : {3u,40945u,40960u,65536u,0xFFFFFFFCu,0xFFFFFFFFu}) {
    selected_profile=true;inject_stack_load=true;injected_address=0x180000-slot;injected_value=value;
    a=initial_context;b=initial_context;
    std::memcpy(memory,initial.data(),bytes);simde_mm_setcsr(0x1F80);selected=false;
    functions[f](a,memory);std::memcpy(expected.data(),memory,bytes);
    std::memcpy(memory,initial.data(),bytes);simde_mm_setcsr(0x1F80);
    selected=selected_unpack=selected_store=selected_ram=true;
    functions[f](b,memory);
    if(std::memcmp(&a,&b,sizeof(a)) || std::memcmp(expected.data(),memory,bytes) || !last_wide || !last_bytes) {
     printf("Guard mismatch trial=%u slot=%u value=%u wide=%llu bytes=%llu\\n",trial,slot,value,last_wide,last_bytes);return 4;
    }
    ++guarded_checks;inject_stack_load=false;
   }
  }
 }
 VirtualFree(memory,0,MEM_RELEASE);puts("504 complete function comparisons passed");
 printf("%u guarded reload comparisons passed\\n",guarded_checks);
}
'''
    source = tmp_path/'whole_functions.cpp'
    source.write_text(header + declarations + support + '\n'.join(fast.values()) +
                      '\n'.join(bodies.values()) + main)
    executable = tmp_path/'whole_functions.exe'
    compilation = subprocess.run([compiler, '-std=c++23', '-O2', '-msse4.1',
        '-DNOMINMAX', '-DSPDLOG_FMT_EXTERNAL', '-DSPDLOG_COMPILED_LIB',
        '-I', str(ROOT/'port/src'), '-I', str(sdk), '-I', str(generated),
        str(source), '-o', str(executable)], capture_output=True, text=True)
    assert compilation.returncode == 0, compilation.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '504 complete function comparisons passed' in result.stdout
    assert '48 guarded reload comparisons passed' in result.stdout
