"""Package authored files only. No DLL loading, game launching or save access."""
import argparse, hashlib, json, os, re, tempfile, zipfile
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dll',required=True,type=Path)
    p.add_argument('--manifest',required=True,type=Path)
    p.add_argument('--payload-root',type=Path,help='Optional mixed-content source tree')
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists() or a.output.suffix.lower()!='.chmod':raise ValueError('Choose a new .chmod output')
    manifest=json.loads(a.manifest.read_text(encoding='utf-8-sig'))
    extensions=manifest.get('extensions',[])
    if len(extensions)!=1 or extensions[0].get('abi')!=2:raise ValueError('Supply one ABI 2 extension manifest')
    entry=extensions[0];relative=entry['file']
    if not re.fullmatch(r'code/[A-Za-z0-9_.-]+\.dll',relative):raise ValueError('Invalid extension path')
    if a.dll.is_symlink() or a.dll.stat().st_size>64*1024*1024:raise ValueError('DLL exceeds limits or is a link')
    dll=a.dll.read_bytes();entry['sha256']=hashlib.sha256(dll).hexdigest()
    files={}
    if a.payload_root:
        root=a.payload_root.resolve()
        for path in root.rglob('*'):
            if path.is_symlink():raise ValueError('Payload links reject')
            if not path.is_file():continue
            rel=path.relative_to(root).as_posix()
            if rel=='mod.json' or rel==relative:continue
            if not re.fullmatch(r'[A-Za-z0-9_./-]+',rel) or any(x in ('.','..') for x in rel.split('/')):raise ValueError('Unsafe payload path')
            if path.stat().st_size>64*1024*1024:raise ValueError('Payload exceeds file limit')
            files[rel]=path.read_bytes()
            if len(files)>8192 or sum(map(len,files.values()))>512*1024*1024:raise ValueError('Payload exceeds package limits')
    files[relative]=dll
    files['mod.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.chmod-',dir=a.output.parent);os.close(fd)
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            for path,data in sorted(files.items()):
                info=zipfile.ZipInfo(path,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,data)
        # Exclusive publication: never overwrite an existing user package.
        if os.name=='nt':os.rename(temp,a.output) # Windows rename refuses existing destinations.
        else:os.link(temp,a.output)
    finally:Path(temp).unlink(missing_ok=True)
    print(a.output)
if __name__=='__main__':main()
