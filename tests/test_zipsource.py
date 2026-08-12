"""Zip-as-source: an artifact drop.zip becomes one of the two compared
folders. The bar is the same as gitsource: read-only, cached, and a zip that
cannot be read is loud, never a silently empty folder."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from compare_tool import zipsource
from compare_tool.zipsource import ZipError


class TestZipSource(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dest = self.tmp / 'dest'
        self.dest.mkdir()

    def _make_zip(self, name, files):
        """files: {arcname: text}. Returns the zip path."""
        path = self.tmp / name
        with zipfile.ZipFile(path, 'w') as zf:
            for arc, text in files.items():
                zf.writestr(arc, text)
        return path

    def test_is_zip_by_content_not_extension(self):
        z = self._make_zip('build.bin', {'a.c': 'x'})  # no .zip suffix
        self.assertTrue(zipsource.is_zip(z))
        plain = self.tmp / 'note.txt'
        plain.write_text('hello')
        self.assertFalse(zipsource.is_zip(plain))
        self.assertFalse(zipsource.is_zip(self.dest))  # a directory is not a zip

    def test_extracts_flat_archive(self):
        z = self._make_zip('drop.zip', {'gen/model.c': 'void f(void){}',
                                        'gen/model.h': 'extern int x;'})
        out = zipsource.extract(z, self.dest)
        # a single top-level 'gen' folder is descended into
        self.assertEqual(out.name, 'gen')
        self.assertEqual((out / 'model.c').read_text(), 'void f(void){}')

    def test_no_wrapper_stays_at_root(self):
        z = self._make_zip('flat.zip', {'model.c': 'a', 'model.h': 'b'})
        out = zipsource.extract(z, self.dest)
        self.assertTrue((out / 'model.c').is_file())
        self.assertTrue((out / 'model.h').is_file())

    def test_extraction_is_cached(self):
        z = self._make_zip('drop.zip', {'gen/a.c': '1'})
        first = zipsource.extract(z, self.dest)
        # tamper with the extracted copy; a cached second call must not redo it
        (first / 'a.c').write_text('changed')
        second = zipsource.extract(z, self.dest)
        self.assertEqual(first, second)
        self.assertEqual((second / 'a.c').read_text(), 'changed')

    def test_a_rebuilt_zip_is_re_extracted(self):
        z = self._make_zip('drop.zip', {'gen/a.c': 'one'})
        first = zipsource.extract(z, self.dest)
        # a genuinely new build: same name, new bytes and mtime -> new folder
        import os
        import time
        time.sleep(0.01)
        with zipfile.ZipFile(z, 'w') as zf:
            zf.writestr('gen/a.c', 'two')
        os.utime(z, None)
        second = zipsource.extract(z, self.dest)
        self.assertNotEqual(first.parent, second.parent)
        self.assertEqual((second / 'a.c').read_text(), 'two')

    def test_corrupt_zip_is_loud(self):
        bad = self.tmp / 'broken.zip'
        bad.write_bytes(b'PK\x03\x04 not really a zip')
        with self.assertRaises(ZipError):
            zipsource.extract(bad, self.dest)

    def test_missing_file_is_loud(self):
        with self.assertRaises(ZipError):
            zipsource.extract(self.tmp / 'nope.zip', self.dest)

    def test_empty_zip_is_loud(self):
        empty = self.tmp / 'empty.zip'
        with zipfile.ZipFile(empty, 'w'):
            pass
        with self.assertRaises(ZipError):
            zipsource.extract(empty, self.dest)

    def test_zip_slip_entry_is_dropped(self):
        evil = self.tmp / 'evil.zip'
        with zipfile.ZipFile(evil, 'w') as zf:
            zf.writestr('gen/ok.c', 'safe')
            zf.writestr('../escaped.c', 'ATTACK')
        out = zipsource.extract(evil, self.dest)
        # the escaping entry never landed next to the temp dir
        self.assertFalse((self.dest.parent / 'escaped.c').exists())
        self.assertFalse((self.dest / 'escaped.c').exists())
        # and the legitimate content is still there
        self.assertTrue(any(p.name == 'ok.c' for p in out.rglob('*.c')))


if __name__ == '__main__':
    unittest.main()
