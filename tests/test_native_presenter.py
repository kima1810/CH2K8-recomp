import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_native_presenter_sdk import patch_presenter,prepare_native_presenter


def test_unlocked_vblank_uses_the_retained_output(tmp_path,monkeypatch):
    sdk=ROOT/'work/third_party/rexglue-vulkan'
    if not (sdk/'.git').exists():pytest.skip('Requires pinned SDK')
    originals={name:subprocess.check_output(['git','-C',str(sdk),'show','HEAD:'+name],text=True)
        for name in ('src/ui/presenter.cpp','src/ui/d3d12/d3d12_presenter.cpp')}
    original=originals['src/ui/presenter.cpp']
    monkeypatch.setattr(subprocess,'check_output',lambda args,**k:originals[args[-1].removeprefix('HEAD:')])
    path=tmp_path/'src/ui/presenter.cpp';path.parent.mkdir(parents=True);path.write_text(original)
    d3d=tmp_path/'src/ui/d3d12/d3d12_presenter.cpp';d3d.parent.mkdir();d3d.write_text(originals['src/ui/d3d12/d3d12_presenter.cpp'])
    prepare_native_presenter(tmp_path);expected=path.read_bytes()
    prepare_native_presenter(tmp_path);assert path.read_bytes()==expected
    patched=patch_presenter(original)
    compiler=shutil.which('clang++')
    if not compiler:pytest.skip('Requires clang++')
    begin=patched.index('    bool wait_succeeded;')
    end=patched.index('    dxgi_ui_tick_lock.lock();',begin)
    block=patched[begin:end]
    source=tmp_path/'presenter.cpp'
    source.write_text(r'''
#include <memory>
#include <cassert>
bool destroyed=false,waited=false;
struct IDXGIOutput {
 ~IDXGIOutput(){destroyed=true;}
 int WaitForVBlank(){assert(!destroyed);waited=true;return 0;}
};
namespace Microsoft::WRL {template<class T>using ComPtr=std::shared_ptr<T>;}
std::shared_ptr<IDXGIOutput> dxgi_ui_tick_output_;
struct Lock {
 void unlock(){dxgi_ui_tick_output_.reset();assert(!destroyed);}
};
#define SUCCEEDED(value) ((value)>=0)
int main(){
 dxgi_ui_tick_output_=std::make_shared<IDXGIOutput>();Lock dxgi_ui_tick_lock;
'''+block+r'''
 assert(wait_succeeded && waited && destroyed);
}
''')
    executable=tmp_path/'presenter.exe'
    result=subprocess.run([compiler,'-std=c++20','-O2',str(source),'-o',str(executable)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(executable)]).returncode==0
    path.write_text(patched+'\n// unknown local edit\n')
    with pytest.raises(ValueError,match='Unreviewed'):prepare_native_presenter(tmp_path)
