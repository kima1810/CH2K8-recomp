"""Refresh the recomp's public SDK snapshot from the canonical Studio checkout.
No game/save access; does not execute builds, DLLs, tests or Git operations.
"""
import argparse,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('studio',type=Path);a=p.parse_args()
repo=Path(__file__).resolve().parents[1];source=a.studio.resolve()/'sdk'
if not (source/'include/chmod/abi.h').is_file():raise ValueError('Select Studio SDK source')
for file in source.rglob('*'):
    if file.is_symlink():raise ValueError('SDK links reject')
    if file.is_file():
        rel=file.relative_to(source)
        if file.suffix not in {'.h','.hpp','.cpp','.json','.md','.py','.txt'}:raise ValueError('Unexpected SDK binary: '+str(rel))
        target=repo/'sdk'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
shutil.copyfile(source/'hooks.json',repo/'docs/formats/hook_registry.json')
files={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.rglob('*')) if p.is_file()}
(repo/'docs/formats/sdk-snapshot.json').write_text(json.dumps(dict(source='https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp/tree/feat/chmod-extension-sdk/sdk',files=files),indent=2)+'\n')
