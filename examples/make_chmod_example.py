"""Developer-only generator: no copyrighted assets or real game identities.

Uses the independently tested synthetic Xbox importer fixture. Players install
packages through the launcher and do not need Python.
"""
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'tools')]
from test_native_asset_tools import fixture_disc, IDENTITY
from loose_assets import import_disc


def create(output):
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        root=Path(temp)
        fixture_disc(root/'disc', 'texture')
        import_disc(root/'disc', root/'game', direct=True)
        entry=json.loads((root/'game/assets.json').read_text())['entries'][0]
        layout=json.loads((root/'game'/entry['folder']/'asset.json').read_text())
        record=layout['records'][0]
        target=entry['folder']+'/'+record['folder']+'/texture.dds'
        original=(root/'game'/target).read_bytes()
        artwork=bytearray(original)
        artwork[128:136]=bytes.fromhex('00f8e00700000000')  # User-authored BC1 block.
        sha=lambda data: hashlib.sha256(data).hexdigest()
        manifest=dict(schema_version=1,id='example.synthetic-art',name='Synthetic DDS example',
                      author='CH2K8 contributors',version='1.0.0',
                      requires=dict(xex_sha256=IDENTITY,recomp='ZMO-beta1',mod_api='1.0.0'),
                      content=['assets'],capabilities=['dds.replace'],dependencies=[],incompatible=[],
                      assets=[dict(bank_hash=entry['hash'],record_index=record['index'],record_id=record['id'],
                                   record_type=record['type'],target=target,source_sha256=sha(original),
                                   file='assets/authored.dds',sha256=sha(artwork))])
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as package:
            # Fixed timestamps make the example reproducible.
            for name,data in [('mod.json',json.dumps(manifest,indent=2).encode()),('assets/authored.dds',bytes(artwork))]:
                item=zipfile.ZipInfo(name,(2026,11,7,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
                package.writestr(item,data)


if __name__ == '__main__':
    create(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).with_name('synthetic-art.chmod'))
