"""Alternate complete original and optimized geometry jobs on identical inputs.

Requires local generated game code and the installed SDK; no game assets are
read. Derived harnesses, binaries and measurements remain in ignored out/.
"""
import argparse
import csv
import io
import json
import re
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGETS=('84723778','84723CC0','84724930')


def harness():
    generated=ROOT/'port/generated/default'
    sources=[p.read_text() for p in generated.glob('*_recomp.*.cpp')]
    kernels=[];helpers=set()
    for address in TARGETS:
        text=next(s for s in sources if f'static void sub_{address}_geometry_fast(' in s)
        for suffix in ('ram_fast','geometry_fast'):
            start=text.index(f'static void sub_{address}_{suffix}(')
            body=text[start:text.index('\n}\n',start)+3]
            helpers.update(re.findall(r'\t(\w+)\(ctx, base\);',body))
            kernels.append(('template<bool Count>\n' if suffix=='geometry_fast' else '')+body)
    support=[]
    for helper in sorted(helpers):
        text=next(s for s in sources if f'DEFINE_REX_FUNC({helper}) {{' in s)
        start=text.index(f'DEFINE_REX_FUNC({helper}) {{')
        support.append(text[start:text.index('\n}\n',start)+3])
    declarations='\n'.join(f'REX_EXTERN({name});' for name in sorted(helpers))
    prefix=r'''
#include "ch2k8_pch.h"
#include "packed_vector_optimized.h"
#include "vector_store_optimized.h"
#include <chrono>
#include <cstdio>
#include <cstring>
#include <vector>
volatile uint64_t observed_counts;
// Keep the original counter side effects visible, as they are across the
// production profiling API. The uncounted template removes only the new ones.
__declspec(noinline) Ch2k8HotScope::Ch2k8HotScope(unsigned,uint32_t,uint8_t*,bool,bool,bool,bool,const uint64_t* counts):ram_counts_(counts){}
__declspec(noinline) Ch2k8HotScope::~Ch2k8HotScope(){observed_counts=ram_counts_?ram_counts_[0]+ram_counts_[1]:0;}
'''
    wrappers=[]
    for i,address in enumerate(TARGETS):
        wrappers.append(f'void Original{i}(PPCContext& ctx,uint8_t* base){{sub_{address}_ram_fast(ctx,base);}}\n'
                        f'void Optimized{i}(PPCContext& ctx,uint8_t* base){{sub_{address}_geometry_fast<false>(ctx,base);}}\n')
    main=r'''
int main(){
 constexpr size_t bytes=2*1024*1024;
 auto memory=static_cast<uint8_t*>(VirtualAlloc(nullptr,1ull<<32,MEM_RESERVE,PAGE_NOACCESS));
 if(!memory||!VirtualAlloc(memory,bytes,MEM_COMMIT,PAGE_READWRITE))return 2;
 std::vector<uint8_t> initial(bytes),expected(bytes);
 uint32_t seed=1234567;for(auto& byte:initial){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;byte=uint8_t(seed);}
 auto put=[&](uint32_t at,uint32_t value){value=__builtin_bswap32(value);std::memcpy(initial.data()+at,&value,4);};
 constexpr uint32_t job=0x10000,groups=4,units=256;
 put(job,groups<<1);put(job+4,(units<<19)|(units<<3));put(job+24,0x30000);put(job+32,0x30000);put(job+36,0x40000);put(job+116,0x60000);
 for(uint32_t group=0;group<groups;++group)put(0x30004+group*12,(units<<16)|(group*128));
 PPCFunc* functions[3][2]={{Original0,Optimized0},{Original1,Optimized1},{Original2,Optimized2}};
 // Compare complete context and guest RAM before taking any timing samples.
 for(unsigned f=0;f<3;++f){
  PPCContext a{},b{};a.r1.u64=0x180000;a.r3.u64=job;a.fpscr.csr=0x1F80;b=a;
  std::memcpy(memory,initial.data(),bytes);simde_mm_setcsr(0x1F80);functions[f][0](a,memory);
  std::memcpy(expected.data(),memory,bytes);
  std::memcpy(memory,initial.data(),bytes);simde_mm_setcsr(0x1F80);functions[f][1](b,memory);
  if(std::memcmp(&a,&b,sizeof(a))||std::memcmp(expected.data(),memory,bytes))return 3;
 }
 puts("function,trial,baseline_ns,optimized_ns");
 for(unsigned f=0;f<3;++f)for(unsigned trial=0;trial<10;++trial){
  double elapsed[2];for(unsigned k=0;k<2;++k){
   unsigned variant=k^(trial&1);std::memcpy(memory,initial.data(),bytes);
   PPCContext ctx{};ctx.r1.u64=0x180000;ctx.fpscr.csr=0x1F80;simde_mm_setcsr(0x1F80);
   unsigned count=f==2?32:256;auto start=std::chrono::steady_clock::now();
   for(unsigned repeat=0;repeat<count;++repeat){ctx.r3.u64=job;functions[f][variant](ctx,memory);}
   elapsed[variant]=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/count;
  }
  printf("%u,%u,%.6f,%.6f\n",f,trial,elapsed[0],elapsed[1]);
 }
 VirtualFree(memory,0,MEM_RELEASE);
}
'''
    return prefix+declarations+'\n'+'\n'.join(kernels+support+wrappers)+main


def benchmark(compiler,output):
    output.mkdir(parents=True,exist_ok=False)
    cpp=output/'geometry_jobs.cpp';executable=output/'geometry_jobs.exe'
    cpp.write_text(harness())
    flags=['-std=c++23','-O2','-DNDEBUG','-fwrapv','-fno-strict-aliasing',
           '-ffp-model=strict','-msse4.1','-DNOMINMAX','-DSPDLOG_FMT_EXTERNAL','-DSPDLOG_COMPILED_LIB',
           '-I',str(ROOT/'port/src'),'-I',str(ROOT/'port/sdk-vulkan/include'),
           '-I',str(ROOT/'port/generated/default')]
    subprocess.run([compiler,*flags,str(cpp),'-o',str(executable)],check=True)
    checked=subprocess.run([str(executable)],capture_output=True,text=True,check=True,timeout=45)
    (output/'timings.csv').write_text(checked.stdout)
    rows=list(csv.DictReader(io.StringIO(checked.stdout)))
    result={'compiler':compiler,'flags':flags,'complete_context_and_memory_match':True,
            'limits':'Identical synthetic jobs, not gameplay FPS; warm alternating pairs, no game assets.'}
    for i,address in enumerate(TARGETS):
        trials=[r for r in rows if int(r['function'])==i and int(r['trial'])>0]
        result[address]={'baseline_ns':statistics.median(float(r['baseline_ns']) for r in trials),
                         'optimized_ns':statistics.median(float(r['optimized_ns']) for r in trials),
                         'median_paired_reduction_percent':statistics.median(
                             100*(1-float(r['optimized_ns'])/float(r['baseline_ns'])) for r in trials)}
    (output/'summary.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',default=shutil.which('clang++'))
    parser.add_argument('--output',type=Path,default=ROOT/'out'/('geometry-jobs-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')))
    args=parser.parse_args()
    if not args.compiler:parser.error('clang++ is required')
    print(json.dumps(benchmark(args.compiler,args.output.resolve()),indent=2))
