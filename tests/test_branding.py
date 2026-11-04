from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from core import branding
from scripts.import_brand_icon import import_assets
from scripts.verify_branding import ico_entries

ROOT=Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def test_committed_assets_match_the_generator(self):
        import hashlib, json
        from scripts.build_brand_assets import build
        manifest=json.loads((ROOT/'assets/branding/brand-manifest.json').read_text(encoding='utf-8'))
        for name,key in (('quartz-q.svg','svg_sha256'),('quartz-q.png','png_sha256'),('quartz-q.ico','ico_sha256')):
            self.assertEqual(hashlib.sha256((ROOT/'assets/branding'/name).read_bytes()).hexdigest(),manifest[key])
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(build(directory),manifest)
    def test_small_icon_frames_are_generated_not_downscaled(self):
        from scripts.build_brand_assets import ICO_SIZES,SOLID_TONE
        with Image.open(ROOT/'assets/branding/quartz-q.ico') as icon:
            self.assertEqual(sorted(icon.ico.sizes()),[(s,s) for s in ICO_SIZES])
            small=icon.ico.getimage((16,16)).convert('RGBA')
        tone=[int(SOLID_TONE[i:i+2],16) for i in (1,3,5)]
        opaque=[small.getpixel((x,y))[:3] for x in range(16) for y in range(16) if small.getpixel((x,y))[3]==255]
        self.assertTrue(opaque)
        for pixel in opaque: self.assertLessEqual(max(abs(a-b) for a,b in zip(pixel,tone)),2)
    def test_in_app_mark_uses_the_same_geometry(self):
        from scripts.build_brand_assets import facets,TAIL,_points
        from ui.shell import SHELL_MARKUP
        for polygon in [*facets(),TAIL]: self.assertIn(_points(polygon),SHELL_MARKUP)
    def test_required_sizes_present_and_decodable(self):
        path=ROOT/'assets/branding/quartz-q.ico'
        sizes={tuple(e['size']) for e in ico_entries(path)}
        self.assertTrue({(s,s) for s in (16,32,48,128,256)}.issubset(sizes))
        with Image.open(path) as image:
            for size in sizes: self.assertEqual(image.ico.getimage(size).size,size)
    def test_brand_preferred_in_source_and_frozen_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'assets/branding').mkdir(parents=True)
            with patch.object(branding,'asset_root',return_value=root):
                self.assertEqual(branding.application_icon(),root/'quartz.ico')
                (root/'assets/branding/quartz-q.ico').touch()
                self.assertEqual(branding.application_icon(),root/'assets/branding/quartz-q.ico')
    def test_import_preserves_provided_extra_sizes_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=import_assets(ROOT/'715d52a3-0f49-49c1-9fe1-b6733ea89145.png',root,ROOT/'download.ico')
            self.assertTrue(result['supplied_ico_preserved']); self.assertEqual(len(result['sizes']),7)
            before=(root/'quartz-q.ico').read_bytes()
            with self.assertRaises(FileExistsError): import_assets(ROOT/'quartz.png',root)
            self.assertEqual((root/'quartz-q.ico').read_bytes(),before)
    def test_mismatched_ico_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); ico=root/'wrong.ico'; target=root/'out'
            Image.new('RGBA',(256,256),'red').save(ico,sizes=[(s,s) for s in (16,32,48,128,256)])
            with self.assertRaises(ValueError): import_assets(ROOT/'715d52a3-0f49-49c1-9fe1-b6733ea89145.png',target,ico)
            self.assertFalse(target.exists())
    def test_gui_header_embeds_small_local_q_mark(self):
        import gui
        self.assertIn('aria-label="Quartz"',gui._HTML)
        self.assertIn('brand-icon"',gui._HTML)
        self.assertNotIn('fonts.googleapis.com',gui._HTML)
    @unittest.skipUnless(os.name=='nt','Windows shell-link file test')
    def test_shortcut_created_read_back_and_backed_up_before_update(self):
        import pythoncom
        from scripts.install_brand_shortcuts import deliver_link
        pythoncom.CoInitialize()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory); exe=root/'Quartz.exe';exe.touch()
                backup=root/'backup';backup.mkdir();path=root/'Quartz.lnk'
                icon=(ROOT/'assets/branding/quartz-q.ico').resolve()
                first=deliver_link(path,backup,exe,icon)
                self.assertEqual(first['status'],'CREATED');self.assertEqual(first['after']['app_id'],branding.APP_ID)
                original=path.read_bytes();second=deliver_link(path,backup,exe,icon)
                self.assertEqual(second['status'],'UPDATED');self.assertEqual(Path(second['backup']).read_bytes(),original)
        finally: pythoncom.CoUninitialize()
    @unittest.skipUnless(os.name=='nt','Windows shell-link file test')
    def test_unrelated_shortcut_is_not_retargeted(self):
        import pythoncom
        from scripts.install_brand_shortcuts import deliver_link
        pythoncom.CoInitialize()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory); exe=root/'Quartz.exe';exe.touch();other=root/'Other.exe';other.touch()
                backup=root/'backup';backup.mkdir();path=root/'Quartz.lnk';icon=(ROOT/'assets/branding/quartz-q.ico').resolve()
                deliver_link(path,backup,other,icon);original=path.read_bytes()
                result=deliver_link(path,backup,exe,icon)
                self.assertEqual(result['status'],'SKIPPED_UNRELATED');self.assertEqual(path.read_bytes(),original)
        finally: pythoncom.CoUninitialize()


if __name__=='__main__': unittest.main()
