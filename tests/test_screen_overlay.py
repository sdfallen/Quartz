import io
import threading
import unittest
from unittest.mock import Mock,patch
from core.screen_overlay import ScreenControlOverlay


class OverlayIsolationTests(unittest.TestCase):
    def test_tk_never_runs_in_host_and_repeat_show_reuses_child(self):
        process=Mock();process.stdin=io.StringIO();process.stdout=io.StringIO('');process.poll.return_value=None
        hud=ScreenControlOverlay()
        with patch('core.screen_overlay.subprocess.Popen',return_value=process) as launch, \
                patch('core.screen_overlay.threading.Thread') as thread, \
                patch.object(hud,'_run_tk_loop') as tk:
            hud.show('Codex',force=True);hud.show('Gemini',force=True)
            launch.assert_called_once();tk.assert_not_called()
            self.assertIn('--quartz-overlay',launch.call_args.args[0])
            self.assertEqual(thread.call_args.kwargs['target'],hud._read_child)
            self.assertIn('label',process.stdin.getvalue())
            hud.hide();self.assertFalse(hud.active)

    def test_unexpected_child_exit_stops_task_without_host_exit(self):
        hud=ScreenControlOverlay();callback=Mock()
        process=Mock();process.stdout=io.StringIO('');process.stdin=io.StringIO()
        hud._process=process;hud._active=True;hud._stop_callback=callback
        hud._read_child(process)
        callback.assert_called_once();self.assertFalse(hud.active)

    def test_old_child_cannot_clear_new_overlay_or_stop_new_task(self):
        hud=ScreenControlOverlay();callback=Mock()
        old=Mock();old.stdout=io.StringIO('STOP\n');old.stdin=io.StringIO()
        current=Mock();hud._process=current;hud._active=True;hud._stop_callback=callback
        hud._read_child(old)
        self.assertIs(hud._process,current);self.assertTrue(hud.active);callback.assert_not_called()
