"""The cyclic garbage collector must stay on the GUI thread once a worker
exists: collecting a cycle that holds Qt objects on a worker thread crashed
the Linux CI run inside a git subprocess call."""

import gc
import os
import threading
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from PySide6.QtWidgets import QApplication

    from compare_tool.qtviewer import worker
    HAVE_QT = True
except ImportError:  # pragma: no cover - viewer extra not installed
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestGuiThreadGc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_creating_a_worker_moves_collection_to_the_gui_thread(self):
        task = worker.TaskWorker(lambda: 42)
        self.assertFalse(gc.isenabled())
        self.assertIsNotNone(worker._gc_timer)
        self.assertTrue(worker._gc_timer.isActive())
        # idempotent: a second worker does not add a second timer
        timer = worker._gc_timer
        worker.TaskWorker(lambda: 0)
        self.assertIs(worker._gc_timer, timer)
        task.start()
        task.wait(5000)
        self.assertEqual(task.result, 42)

    def test_timer_collects_cycles_on_the_gui_thread(self):
        worker.TaskWorker(lambda: None)
        seen = []

        class Cycle:
            def __del__(self):
                seen.append(threading.current_thread() is threading.main_thread())

        a, b = Cycle(), Cycle()
        a.other, b.other = b, a
        del a, b
        # push generation 0 over its threshold the way allocation would
        threshold = gc.get_threshold()[0]
        junk = [[] for _ in range(threshold + 10)]
        for item in junk:
            item.append(item)
        del junk, item
        worker._collect_on_gui_thread()
        gc.collect()  # anything left in older generations, still on this thread
        self.assertTrue(seen)
        self.assertTrue(all(seen))


if __name__ == '__main__':
    unittest.main()
