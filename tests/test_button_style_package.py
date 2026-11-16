"""Prepared static package tests; not run by the implementation task.

Set CHMOD_BUTTON_STYLE_PACKAGE to an authored package to run the opt-in artifact
case. No DLL loading, game execution, network or saves.
"""
import hashlib,json,os,struct,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ButtonStyleContracts(unittest.TestCase):
    def test_inventory_matches_adapter_and_abi(self):
        registry=json.loads((ROOT/'sdk/hooks.json').read_text())
        hook=next(x for x in registry['package_hooks'] if x['id']=='presentation.button_style')
        self.assertEqual(hook['numeric_id'],5)
        self.assertEqual(set(hook['operations']),{'before','after','result'})
        self.assertFalse(hook['in_game_verified'])
        source=(ROOT/'port/src/mod_presentation.cpp').read_text()
        self.assertIn('REX_HOOK_RAW(sub_847DC530)',source)
        self.assertIn('__imp__sub_847DC530(ctx,base)',source)
        self.assertIn('allocate_callback',source)
        helper=(ROOT/'port/src/mod_option_menu.h').read_text()
        self.assertIn('AllocateThunk',helper)
        self.assertIn('REX_LOOKUP_FUNC',helper)
        mod=(ROOT/'sdk/examples/button-style/extension.cpp').read_text()
        self.assertNotIn('REX_STORE',mod)
        self.assertNotIn('847DC530',mod)

    @unittest.skipUnless(os.environ.get('CHMOD_BUTTON_STYLE_PACKAGE'),'explicit authored artifact required')
    def test_package_hashes_dds_and_coherent_pair(self):
        with zipfile.ZipFile(os.environ['CHMOD_BUTTON_STYLE_PACKAGE']) as z:
            self.assertEqual(len(z.namelist()),len(set(z.namelist())))
            m=json.loads(z.read('mod.json'))
            self.assertEqual(set(m['content']),{'assets','code'})
            self.assertEqual(len(m['extensions']),1)
            self.assertEqual(m['extensions'][0]['abi'],2)
            self.assertEqual(m['extensions'][0]['capabilities'],['hook.presentation.button_style'])
            self.assertEqual({a['record_index'] for a in m['assets']},{270,410})
            names={'mod.json'}
            for entry in m['assets']+m['extensions']:
                data=z.read(entry['file']);names.add(entry['file'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])
            self.assertEqual(names,set(z.namelist()))
            for asset in m['assets']:
                self.assertEqual(asset['selection'],'presentation.playstation')
                d=z.read(asset['file']);self.assertEqual(d[:4],b'DDS ')
                self.assertEqual(d[84:88],b'DXT5')
                height,width=struct.unpack_from('<II',d,12)
                size=256 if asset['record_index']==270 else 512
                self.assertEqual((width,height),(size,size))
                self.assertEqual(len(d),128+size*size)
if __name__=='__main__':unittest.main()
