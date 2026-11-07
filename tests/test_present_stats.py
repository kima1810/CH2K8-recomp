import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from summarize_present_stats import summarize


def test_present_scope_summary_keeps_threads_and_nested_times_separate(tmp_path):
    log=tmp_path/'runtime.log'
    log.write_text('''[2026-11-03 10:00:00.000] [info] start
[2026-11-03 10:00:01.000] [info] [ui] [t20] CH2K8_PRESENT stage=present calls=10 wall_ms=20 cpu_ms=0 max_ms=3 window_ms=1000
[2026-11-03 10:00:02.000] [info] [ui] [t20] CH2K8_PRESENT stage=present calls=20 wall_ms=60 cpu_ms=10 max_ms=8 window_ms=1000
[2026-11-03 10:00:02.000] [info] [ui] [t21] CH2K8_PRESENT stage=paint calls=10 wall_ms=1000 cpu_ms=200 max_ms=120 window_ms=1000
''')
    result=summarize(log,1.5)
    assert len(result['scopes'])==2
    assert result['scopes'][0]['calls']==20 and result['scopes'][0]['average_ms']==3
    assert result['scopes'][1]['stage']=='paint'
    assert 'overlap' in result['limits']
    log.write_text(log.read_text().replace('wall_ms=60','wall_ms=1e999'))
    with pytest.raises(ValueError,match='Invalid'):summarize(log)


def test_opt_in_scope_records_long_wait_and_disabled_path_does_not_log(tmp_path):
    compiler=shutil.which('clang++');sdk=ROOT/'port/sdk-vulkan/include'
    if not compiler or not sdk.exists():pytest.skip('Requires local compiler/SDK')
    source=tmp_path/'scope.cpp'
    source.write_text(r'''
#include <rex/logging.h>
#include <cassert>
#include <thread>
#include <chrono>
#undef REXLOG_INFO
unsigned logs=0;bool enabled=false;
void record(const char*,const char*,uint64_t calls,double wall,double cpu,double maximum,double window) {
 assert(calls==1 && wall>=1000 && maximum>=1000 && window>=1000);++logs;
}
#define REXLOG_INFO(...) record(__VA_ARGS__)
#include "native_present_stats.h"
bool& FLAGS_ch2k8_present_stats_storage_(){return enabled;}
int main(){
 using namespace rex::ui::ch2k8;
 {PresentScope disabled(PresentStage::Present);}
 assert(!logs);enabled=true;
 {PresentScope wait(PresentStage::Present);std::this_thread::sleep_for(std::chrono::milliseconds(1010));}
 assert(logs==1);enabled=false;
 {PresentScope disabled(PresentStage::Present);}
 assert(logs==1);
}
''')
    exe=tmp_path/'scope.exe'
    result=subprocess.run([compiler,'-std=c++23','-O2','-DNOMINMAX','-DSPDLOG_FMT_EXTERNAL',
        '-DSPDLOG_COMPILED_LIB','-I',str(ROOT/'port/sdk_patches'),'-I',str(sdk),str(source),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(exe)]).returncode==0


def test_vblank_pacer_rejects_false_ticks_without_catchup_bursts(tmp_path):
    compiler=shutil.which('clang++')
    if not compiler:pytest.skip('Requires clang++')
    source=tmp_path/'pacer.cpp'
    source.write_text(r'''
#include "native_vblank_pacer.h"
#include <cassert>
using P=rex::ui::ch2k8::VBlankPacer;
using namespace std::chrono;
int main(){
 for(unsigned rate:{0u,1u,24u,30u,50u,59u,60u,90u,120u,144u,165u,240u,360u,500u,1000u,1001u}) {
  const auto period=nanoseconds(1000000000ull/((rate<24 || rate>1000)?60:rate));
  P p;P::Time now{};p.Reset(rate,now);
  // Real blocking vblank waits and occasional early returns stay native.
  for(unsigned i=0;i<1000;++i) {
   assert(!p.Observe(now,now+nanoseconds(100)));now+=nanoseconds(100);
   assert(!p.Observe(now,now+period));now+=period;
  }
  assert(!p.timer());
  assert(!p.Observe(now,now+nanoseconds(100)));now+=nanoseconds(100);
  assert(!p.Observe(now,now+nanoseconds(100)));now+=nanoseconds(100);
  assert(p.Observe(now,now+nanoseconds(100)));now+=nanoseconds(100);
  assert(p.timer() && p.Deadline(now)==now+period);
  for(unsigned i=0;i<1000;++i) {
    auto deadline=p.Deadline(now);assert(deadline>now);
    now=deadline;p.Delivered(now);
    assert(p.Deadline(now)==now+period);
  }
  now+=period*10;assert(p.Deadline(now)==now+period);
  now+=period;p.Delivered(now);assert(p.Deadline(now)>now);
  p.Reset(60,now);assert(!p.timer());
 }
}
''')
    executable=tmp_path/'pacer.exe'
    result=subprocess.run([compiler,'-std=c++20','-O2','-I',str(ROOT/'port/sdk_patches'),str(source),'-o',str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(executable)]).returncode==0


def test_production_vblank_thread_handles_output_changes_and_shutdown(tmp_path):
    compiler=shutil.which('clang++')
    if not compiler:pytest.skip('Requires clang++')
    executable=tmp_path/'vblank.exe'
    result=subprocess.run([compiler,'-std=c++20','-O2','-I',str(ROOT/'port/sdk_patches'),
        str(ROOT/'tests/native_vblank_thread.cpp'),'-o',str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(executable)],timeout=10).returncode==0
