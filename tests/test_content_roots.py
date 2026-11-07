import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_content_sdk import prepare_content


def test_aggregate_enumeration_visits_each_physical_root_once(tmp_path):
    compiler=shutil.which('clang++')
    if not compiler:pytest.skip('clang++ required')
    cpp=tmp_path/'roots.cpp';exe=tmp_path/'roots.exe'
    cpp.write_text('''#include "content_roots.h"
#include <cassert>
int main() {
 ch2k8::ContentRoots common;
 assert(common.First(0,UINT32_MAX,0x54540818));
 assert(!common.First(0,UINT32_MAX,0x54540818));
 assert(!common.First(0,0x54540818,0x54540818));
 ch2k8::ContentRoots user;
 assert(user.First(123,UINT32_MAX,0x54540818));
 assert(user.First(0,UINT32_MAX,0x54540818));
 assert(!user.First(123,0x54540818,0x54540818));
 assert(!user.First(0,0x54540818,0x54540818));
 assert(user.First(123,0x54540800,0x54540818));
 assert(user.First(0,0x54540800,0x54540818));
 assert(user.First(456,0x54540818,0x54540818));
}''')
    subprocess.run([compiler,'-std=c++20','-I',str(ROOT/'port/src'),str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)


def test_content_patch_rejects_unknown_layout_without_writing(tmp_path):
    path=tmp_path/'src/kernel/xam/xam_content_aggregate.cpp';path.parent.mkdir(parents=True);path.write_text('unknown')
    with pytest.raises(ValueError,match='Unrecognized'):prepare_content(tmp_path)
    assert path.read_text()=='unknown'


def test_pinned_content_patch_is_idempotent(tmp_path):
    source=ROOT/'work/third_party/rexglue-vulkan'
    if not source.is_dir():pytest.skip('Local pinned SDK required')
    relative=Path('src/kernel/xam/xam_content_aggregate.cpp');path=tmp_path/relative;path.parent.mkdir(parents=True)
    original=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+relative.as_posix()])
    path.write_bytes(original);(tmp_path/'include/rex/system/xam').mkdir(parents=True)
    prepare_content(tmp_path);first=path.read_bytes();prepare_content(tmp_path);assert path.read_bytes()==first
    text=first.decode();assert 'enumeration_roots.First(xuid, title_id' in text and 'enumeration_roots.First(0, title_id' in text
