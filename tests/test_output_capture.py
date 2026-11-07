import shutil
import struct
import subprocess
from pathlib import Path

import pytest


def test_native_readback_bmp_preserves_stride_orientation_and_rgb(tmp_path):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('Requires clang++')
    root = Path(__file__).resolve().parents[1]
    header = tmp_path/'include/rex/ui/presenter.h'
    header.parent.mkdir(parents=True)
    header.write_text('''#include <vector>
#include <cstdint>
#include <cstddef>
namespace rex::ui {
struct RawImage { uint32_t width=2, height=2; size_t stride=12;
 std::vector<uint8_t> data={255,0,0,0, 0,255,0,0, 99,99,99,99,
                          0,0,255,0, 255,255,255,0}; };
class Presenter { public: bool CaptureGuestOutput(RawImage&) { return true; } };
}
''')
    main = tmp_path/'main.cpp'
    main.write_text('''#include <rex/ui/presenter.h>
bool Ch2k8SaveOutput(rex::ui::Presenter*,const char*);
int main(int argc,char**argv) { rex::ui::Presenter p;
 return Ch2k8SaveOutput(&p,argv[1]) ? 0 : 1; }
''')
    executable = tmp_path/'probe.exe'
    compilation = subprocess.run([compiler, '-std=c++23', '-I', str(tmp_path/'include'),
        str(main), str(root/'port/src/output_capture.cpp'), '-o', str(executable)],
        capture_output=True, text=True)
    assert compilation.returncode == 0, compilation.stderr
    output = tmp_path/'frame.bmp'
    subprocess.run([str(executable), str(output)], check=True)
    data = output.read_bytes()
    assert data[:2] == b'BM'
    assert struct.unpack_from('<I', data, 2)[0] == len(data) == 70
    assert struct.unpack_from('<ii', data, 18) == (2, -2)
    assert data[54:] == bytes([0,0,255,0, 0,255,0,0, 255,0,0,0, 255,255,255,0])
