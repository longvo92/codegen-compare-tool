import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from compare_tool.fileio import write_text_atomic


class WriteTextAtomicTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_writes_content_and_creates_parents_on_request(self):
        target = self.dir / 'a' / 'b' / 'out.txt'
        self.assertEqual(write_text_atomic(target, 'héllo\nworld\n', parents=True), target)
        self.assertEqual(target.read_bytes(), 'héllo\nworld\n'.encode('utf-8'))
        self.assertEqual(os.listdir(target.parent), ['out.txt'])

    def test_missing_parent_raises_by_default(self):
        target = self.dir / 'missing' / 'out.txt'
        with self.assertRaises(OSError):
            write_text_atomic(target, 'x')
        self.assertFalse((self.dir / 'missing').exists())

    def test_replaces_existing_file(self):
        target = self.dir / 'out.txt'
        target.write_text('old', encoding='utf-8')
        write_text_atomic(target, 'new')
        self.assertEqual(target.read_text(encoding='utf-8'), 'new')

    def test_failure_keeps_original_and_cleans_temp(self):
        target = self.dir / 'out.txt'
        target.write_text('old', encoding='utf-8')
        with mock.patch('compare_tool.fileio.os.replace', side_effect=OSError('boom')):
            with self.assertRaises(OSError):
                write_text_atomic(target, 'new')
        self.assertEqual(target.read_text(encoding='utf-8'), 'old')
        self.assertEqual(os.listdir(self.dir), ['out.txt'])


if __name__ == '__main__':
    unittest.main()
