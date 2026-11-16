"""Package a compiled user-authored DLL; does not load it or open the game."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def package(dll,output):
    payload=Path(dll).read_bytes()
    manifest={
        'schema_version':1,'id':'example.native-weight','name':'Native weight getter example',
        'author':'CH2K8 contributors','version':'1.0.0',
        'requires':{'xex_sha256':'71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36',
                    'recomp':'ZMO-beta1','mod_api':'1.2.0'},
        'content':['code'],'capabilities':['hook.player.weight.read'],
        'dependencies':[],'incompatible':[],'assets':[],
        'extensions':[{'file':'code/weight_read.dll','sha256':hashlib.sha256(payload).hexdigest(),
                       'abi':1,'hook':'player.weight.read'}]
    }
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in [('mod.json',json.dumps(manifest,indent=2).encode()),('code/weight_read.dll',payload)]:
            entry=zipfile.ZipInfo(name,(2026,11,8,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,data)


if __name__=='__main__':
    package(sys.argv[1],Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).resolve().parents[1]/'native-weight-example.chmod')
