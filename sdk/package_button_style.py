"""Encode supplied PS3 JPEG atlases and package the SDK DLL. Never launches it.

Requires Pillow with BC3/DXT5 writing. No stock Xbox artwork is distributed.
White matte removal is a connected-background conversion, not recovered alpha.
"""
import argparse, hashlib, json, os, tempfile, zipfile
from collections import deque
from pathlib import Path

def matte(image):
    image=image.convert('RGBA');w,h=image.size;p=image.load();seen=set();queue=deque()
    # Atlas cells have a white surround. Seed every cell border, preserving
    # isolated white markings (Start/L1/etc.) inside dark button silhouettes.
    for y in range(h):
        for x in range(w):
            if x%(w//4) in (0,w//4-1) or y%(h//4) in (0,h//4-1):queue.append((x,y))
    while queue:
        x,y=queue.popleft()
        if not (0<=x<w and 0<=y<h) or (x,y) in seen:continue
        r,g,b,_=p[x,y]
        if (r+g+b)/3<150:continue
        seen.add((x,y));queue.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
    for x,y in seen:
        r,g,b,_=p[x,y];alpha=max(0,min(255,round((235-(r+g+b)/3)*255/65)))
        # Exterior antialias belongs to the dark outline, not JPEG chroma noise.
        p[x,y]=(0,0,0,alpha)
    # Isolated JPEG specks in the white surround are not button details.
    visited=set()
    for y in range(h):
        for x in range(w):
            if (x,y) in visited or p[x,y][3]<32:continue
            component=[];todo=[(x,y)];visited.add((x,y))
            while todo:
                cx,cy=todo.pop();component.append((cx,cy))
                for nx,ny in ((cx-1,cy),(cx+1,cy),(cx,cy-1),(cx,cy+1)):
                    if 0<=nx<w and 0<=ny<h and (nx,ny) not in visited and p[nx,ny][3]>=32:
                        visited.add((nx,ny));todo.append((nx,ny))
            if len(component)<12:
                for cx,cy in component:p[cx,cy]=(0,0,0,0)
    return image

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--buttons',type=Path,required=True);p.add_argument('--sticks',type=Path,required=True)
    p.add_argument('--dll',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--preview',type=Path,help='Optional private preview directory outside package')
    a=p.parse_args()
    from PIL import Image
    if a.output.exists() or a.output.suffix.lower()!='.chmod':raise ValueError('Choose a new .chmod output')
    if a.dll.stat().st_size>64*1024*1024:raise ValueError('DLL exceeds package limit')
    dll=a.dll.read_bytes();files={'code/chmod_button_style.dll':dll};assets=[]
    provenance=[]
    rows=[(a.buttons,256,270,1967269951,'0270_7542283f.txtr','2e375b3021f21c2581ebed27b87f1698abf14db1adc29afa439be0f124e442d5'),
          (a.sticks,512,410,2898710808,'0410_acc6d118.txtr','8a77ffd65a95df3d9c5359b6dcf731a7e206450b845a3fe6b3ae1536a5181bee')]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chmod-art-',dir=a.output.parent) as temp:
        for source,size,index,identity,folder,original in rows:
            if source.stat().st_size>8*1024*1024:raise ValueError('Artwork too large')
            image=Image.open(source)
            if image.size != ((256,256) if index==270 else (128,128)):raise ValueError('Unexpected supplied atlas dimensions')
            image=matte(image)
            if image.size!=(size,size):image=image.resize((size,size),Image.Resampling.LANCZOS)
            if a.preview:
                a.preview.mkdir(parents=True,exist_ok=True);image.save(a.preview/f'{index}.png')
            dds=Path(temp)/f'{index}.dds';image.save(dds,pixel_format='DXT5')
            payload=dds.read_bytes();name=f'assets/ps3-{index}.dds';files[name]=payload
            assets.append(dict(bank_hash=3680386632,record_index=index,record_id=identity,record_type=1547079785,
                               target=f'assets/global.iff/{folder}/texture.dds',source_sha256=original,
                               file=name,sha256=hashlib.sha256(payload).hexdigest(),selection='presentation.playstation'))
            provenance.append(dict(input=source.name,sha256=hashlib.sha256(source.read_bytes()).hexdigest(),output=name,alpha='connected white matte reconstruction',size=size))
    manifest=dict(schema_version=1,id='org.ch2k8.button-style',name='Xbox / PlayStation Button Style',author='CHMOD SDK; user-supplied PS3 artwork',version='0.1.0',
                  requires=dict(xex_sha256='71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36',recomp='ZMO-beta1',mod_api='1.3.0'),
                  content=['assets','code'],capabilities=['dds.replace','hook.presentation.button_style'],dependencies=[],incompatible=[],assets=assets,
                  extensions=[dict(file='code/chmod_button_style.dll',sha256=hashlib.sha256(dll).hexdigest(),abi=2,capabilities=['hook.presentation.button_style'],replacements=[])])
    files['mod.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.button-style-',dir=a.output.parent);os.close(fd)
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in sorted(files.items()):
                info=zipfile.ZipInfo(name,(2026,11,8,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,data)
        if os.name=='nt':os.rename(temporary,a.output) # Exclusive, atomic publication.
        else:os.link(temporary,a.output)
    finally:Path(temporary).unlink(missing_ok=True)
    if a.preview:(a.preview/'conversion.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(a.output)
if __name__=='__main__':main()
