"""Compare decoded source layout semantics with a converted Xbox scorebug."""
import argparse
import json
import struct
import zipfile
from pathlib import Path
from scene_binary import R, U, meshes, take, string

def rows(data, count_field, pointer_field, stride, key_offset):
    table = R(data,pointer_field)
    result = {U(data,table+i*stride+key_offset):table+i*stride for i in range(U(data,count_field))}
    assert len(result) == U(data,count_field)
    return result

def texts(data):
    table = R(data,0x50)
    return {string(data,R(data,table+i*144+64)):table+i*144 for i in range(U(data,0x4c))}

def properties(data,text):
    table=R(data,text+80)
    result={}
    for i in range(U(data,table)):
        at=table+16+i*32
        kind,key=U(data,at+16),U(data,at+20)
        value=string(data,R(data,at)) if kind==3 and U(data,at) else take(data,at,16)
        result[key]=(kind,value)
    return result

def parameters(data,row):
    shaders=rows(data,0x28,0x2c,48,0)
    shader=shaders[U(data,row+8)]
    p=R(data,row+32)
    values={}
    count=U(data,shader+8)
    uniforms,samplers=R(data,shader+24),R(data,shader+28)
    for i in range(count>>16):
        at=uniforms+i*44
        offset=struct.unpack_from('>H',data,at+20)[0]
        values[('uniform',U(data,at))]=take(data,p+offset,16)
    for i in range(count&65535):
        at=samplers+i*36
        offset=struct.unpack_from('>H',data,at+16)[0]+12
        values[('sampler',U(data,at))]=take(data,p+offset,4)
    return values

def audit(source_cpu,source_gpu,cpu,gpu):
    checks={}
    assert string(source_cpu,R(source_cpu,0))==string(cpu,R(cpu,0))=='scorebug_bottombar'
    source_meshes={m['name']:m for m in meshes(source_cpu,True)}
    target_meshes={m['name']:m for m in meshes(cpu)}
    assert source_meshes.keys()==target_meshes.keys()
    count=0
    for name,source in source_meshes.items():
        target=target_meshes[name]
        src,_,size=source['streams'][0]
        dst,_,n=target['streams'][0]
        assert size==n and source['count']==target['count']
        for offset in range(0,size,36):
            assert source_gpu[src+offset:src+offset+32]==gpu[dst+offset:dst+offset+32],name
            assert source_gpu[src+offset+32:src+offset+36][::-1]==gpu[dst+offset+32:dst+offset+36],name
            count+=1
        sp,xp=source['part'],target['part']
        assert take(source_cpu,sp+16,80)==take(cpu,xp+16,80),name
        source_runs,target_runs=R(source_cpu,sp+128),R(cpu,xp+128)
        assert U(source_cpu,sp+124)==U(cpu,xp+124)
        assert take(source_cpu,source_runs,U(source_cpu,sp+124)*48)==take(cpu,target_runs,U(cpu,xp+124)*48),name
        assert U(source_cpu,sp+168)==U(cpu,xp+168),name
        size=U(source_cpu,sp+168)*2
        assert take(source_gpu,U(source_cpu,sp+172)-1,size)==take(gpu,U(cpu,xp+172)-1,size),name
        sb,xb=R(source_cpu,sp+100),R(cpu,xp+100)
        assert U(source_cpu,sp+96)==U(cpu,xp+96)
        for i in range(U(cpu,xp+96)):
            assert take(source_cpu,sb+i*48,32)==take(cpu,xb+i*48,32)
    checks.update(meshes=len(target_meshes),vertices=count,draw_runs=24)
    source_instances,target_instances=rows(source_cpu,60,64,144,68),rows(cpu,60,64,144,68)
    assert source_instances.keys()==target_instances.keys()
    for key,target in target_instances.items():
        source=source_instances[key]
        assert take(source_cpu,source,64)==take(cpu,target,64)
        model=next(m for m in source_meshes.values() if U(source_cpu,m['part']+4)==key)
        size=U(source_cpu,model['part']+96)*64
        assert take(source_cpu,R(source_cpu,source+116),size)==take(cpu,R(cpu,target+116),size)
    checks['instances']=len(target_instances)
    source_text,target_text=texts(source_cpu),texts(cpu)
    assert source_text.keys()==target_text.keys()
    for name,target in target_text.items():
        source=source_text[name]
        assert take(source_cpu,source,64)==take(cpu,target,64),name
        assert take(source_cpu,source+96,12)==take(cpu,target+96,12),name
        assert properties(source_cpu,source)==properties(cpu,target),name
    checks['text_nodes']=len(target_text)
    source_materials,target_materials=rows(source_cpu,48,56,40,0),rows(cpu,48,56,40,0)
    assert source_materials.keys()==target_materials.keys()
    for key,target in target_materials.items():
        assert parameters(source_cpu,source_materials[key])==parameters(cpu,target),hex(key)
    checks['materials']=len(target_materials)
    return checks

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('converted',type=Path)
    args=p.parse_args()
    with zipfile.ZipFile(args.archive) as z:
        wrapped=z.read(next(n for n in z.namelist() if n.endswith('.scne')))
    source_cpu=wrapped[20:20+U(wrapped,12)]
    source_gpu=wrapped[20+len(source_cpu):]
    cpu,gpu=[(args.converted/n).read_bytes() for n in ('scene.dat','scene_gpu.dat')]
    report=audit(source_cpu,source_gpu,cpu,gpu)
    (args.converted/'port-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
