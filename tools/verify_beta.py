"""Developer reference for beta inventory/PE regression tests.

Distributed packages use verify_beta.ps1 and do not ship this module.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

SYSTEM_DLLS = set(('advapi32 bcrypt cfgmgr32 combase comdlg32 crypt32 cryptbase dbgcore dbghelp '
                  'd3d12 d3dcompiler_47 dxgi dwmapi gdi32 imm32 iphlpapi kernel32 kernelbase '
                  'mswsock ncrypt normaliz ntdll ole32 oleaut32 powrprof psapi propsys rpcrt4 sechost '
                  'secur32 setupapi shell32 shlwapi shcore user32 userenv uxtheme version '
                  'winhttp wininet winmm wintrust ws2_32 wtsapi32 ucrtbase').split())


def pe_imports(path):
    data = path.read_bytes()
    if data[:2] != b'MZ': raise ValueError(f'Invalid Windows binary: {path.name}')
    pe = struct.unpack_from('<I', data, 60)[0]
    if data[pe:pe+4] != b'PE\0\0': raise ValueError(f'Invalid PE signature: {path.name}')
    machine, count = struct.unpack_from('<HH', data, pe+4)
    if machine != 0x8664: raise ValueError(f'Non-x64 binary: {path.name}')
    optional = pe+24
    size = struct.unpack_from('<H', data, pe+20)[0]
    if struct.unpack_from('<H', data, optional)[0] != 0x20b: raise ValueError('Expected PE32+')
    sections = [struct.unpack_from('<IIII', data, optional+size+i*40+8) for i in range(count)]
    def offset(rva):
        for virtual_size, address, raw_size, pointer in sections:
            if address <= rva < address+max(virtual_size, raw_size): return pointer+rva-address
        raise ValueError(f'Invalid PE RVA in {path.name}')
    def name(rva):
        start = offset(rva)
        return data[start:data.index(b'\0', start)].decode('ascii').lower()
    names = []
    for directory, stride, field in ((1,20,12), (13,32,4)):
        rva = struct.unpack_from('<I', data, optional+112+directory*8)[0]
        if not rva: continue
        position = offset(rva)
        while any(data[position:position+stride]):
            names.append(name(struct.unpack_from('<I', data, position+field)[0]))
            position += stride
    return names


def verify(root):
    root = Path(root).resolve()
    inventory = root/'SHA256SUMS.txt'
    listed = set()
    for line in inventory.read_text(encoding='ascii').splitlines():
        digest, relative = line.split('  ', 1)
        path = (root/relative.replace('\\','/')).resolve()
        if not path.is_relative_to(root): raise ValueError('Inventory escapes package')
        if path in listed: raise ValueError('Duplicate inventory path')
        listed.add(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest: raise ValueError(f'Checksum mismatch: {relative}')
    for path in root.rglob('*'):
        if path.is_file() and path != inventory and path.resolve() not in listed:
            raise ValueError(f'Unlisted package file: {path.relative_to(root)}')
    for name in ('ch2k8.exe', 'rexruntime.dll', 'rexgpu-xenos.dll', 'ch2k8_tools.exe',
                 'tools/launch_ch2k8.ps1', 'tools/verify_beta.ps1', 'tools/beta_diagnostics.ps1', 'gamecontrollerdb.txt'):
        if not (root/name).is_file(): raise ValueError(f'Missing beta component: {name}')
    binaries = []
    for path in sorted(root.rglob('*')):
        if path.suffix.lower() not in ('.exe','.dll','.pyd'): continue
        imports = pe_imports(path)
        available = {p.name.lower() for p in path.parent.iterdir() if p.is_file()}
        for dll in imports:
            if dll in available or dll.startswith(('api-ms-win-', 'ext-ms-win-')) or dll.removesuffix('.dll') in SYSTEM_DLLS: continue
            raise ValueError(f'Unbundled dependency: {path.relative_to(root)} -> {dll}')
        binaries.append(dict(path=path.relative_to(root).as_posix(), imports=imports))
    return dict(verified=True, files=len(listed), binaries=binaries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2))
