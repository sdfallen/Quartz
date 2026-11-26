"""One SpeS per Windows session (live 25 Nov 2026: a second start ran a second backend)."""
import subprocess
import sys
import unittest
from pathlib import Path

from core import single_instance


class FakeKernel:
    def __init__(self):
        self.closed = []

    def CreateMutexW(self, attrs, owner, name):
        return 77

    def CloseHandle(self, handle):
        self.closed.append(handle)


class SingleInstanceTests(unittest.TestCase):
    def test_the_first_start_owns_the_mutex(self):
        kernel = FakeKernel()
        self.assertTrue(single_instance.acquire("x", kernel32=kernel, last_error=lambda: 0))
        self.assertEqual(kernel.closed, [])

    def test_a_second_start_steps_aside(self):
        kernel = FakeKernel()
        self.assertFalse(single_instance.acquire("x", kernel32=kernel, last_error=lambda: 183))
        self.assertEqual(kernel.closed, [77])

    def test_a_broken_mutex_never_blocks_the_start(self):
        class Broken:
            def CreateMutexW(self, *a):
                raise OSError("no")
        self.assertTrue(single_instance.acquire("x", kernel32=Broken(), last_error=lambda: 0))

    @unittest.skipUnless(sys.platform == "win32", "Windows mutex")
    def test_real_windows_mutex_is_seen_by_another_process(self):
        name = "Local\\SpeS-test-" + str(id(self))
        self.assertTrue(single_instance.acquire(name))
        root = Path(__file__).resolve().parents[1]
        code = ("import sys; sys.path.insert(0, %r); from core.single_instance import acquire; "
                "print(acquire(%r))" % (str(root), name))
        out = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.strip(), "False", out.stderr)

    def test_the_entry_point_checks_before_starting_anything(self):
        source = (Path(__file__).resolve().parents[1] / "quartz_entry.py").read_text(encoding="utf-8")
        guard = source.index("if not acquire():")
        self.assertLess(source.index("--quartz-overlay"), guard, "the overlay child is not a second SpeS")
        self.assertLess(guard, source.index("start_backend_thread()\n    app = start_gui()"))


if __name__ == "__main__":
    unittest.main()
