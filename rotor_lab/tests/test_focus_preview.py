"""Software-only focus preview tests. No physical camera is required."""
import ast
from io import StringIO
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import focus_preview as fp
import operator_gui


class RawDisplayTests(unittest.TestCase):
    def events(self, rows):
        import numpy as np
        return np.array(rows, dtype=[('t', '<u8'), ('x', '<u2'), ('y', '<u2'), ('on', '?')])

    def test_native_resolution_and_colors(self):
        view = fp.RawView(4, 3)
        view.push(self.events([(100, 1, 1, True), (200, 2, 1, False)]))
        image = view.image(200)
        self.assertEqual(image.shape, (3, 4, 3))
        self.assertEqual(tuple(image[1, 1]), fp.YELLOW)
        self.assertEqual(tuple(image[1, 2]), fp.BLUE)

    def test_repeated_coordinates_choose_latest_polarity(self):
        view = fp.RawView(3, 3)
        view.push(self.events([(100, 1, 1, True), (102, 1, 1, False),
                               (103, 1, 1, True), (104, 1, 1, False)]))
        self.assertEqual(tuple(view.image(104)[1, 1]), fp.BLUE)

    def test_idle_pixels_expire(self):
        view = fp.RawView(3, 3)
        view.push(self.events([(1, 1, 1, True)]))
        self.assertTrue(view.image(33_001).any())
        self.assertFalse(view.image(33_002).any())

    def test_bounds_and_empty_packets(self):
        view = fp.RawView(3, 3)
        self.assertEqual(view.push(None), 0)
        self.assertEqual(view.push(self.events([])), 0)
        self.assertEqual(view.push(self.events([(100, 50, 1, True)])), 0)
        self.assertFalse(view.image(100).any())

    def test_reset_clears_prior_pixels(self):
        view = fp.RawView(3, 3)
        view.push(self.events([(5000, 1, 1, True)]))
        view.push(self.events([(100, 2, 2, False)]))
        image = view.image(100)
        self.assertFalse(image[1, 1].any())
        self.assertEqual(tuple(image[2, 2]), fp.BLUE)

    def test_irregular_activity_not_frequency_filtered(self):
        view = fp.RawView(4, 3)
        view.push(self.events([(10, 1, 1, True), (333, 2, 1, True), (4000, 3, 1, False)]))
        self.assertEqual((view.image(4000).any(axis=2)).sum(), 3)

    def test_bad_geometry_and_bad_schema_rejected(self):
        import numpy as np
        with self.assertRaises(ValueError): fp.RawView(0, 720)
        with self.assertRaises(ValueError): fp.RawView(20000, 720)
        with self.assertRaises(ValueError): fp.RawView(3, 3).push(np.zeros(2))


class FakeCV:
    WINDOW_NORMAL = 0
    WND_PROP_VISIBLE = 4
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 16
    error = RuntimeError
    def __init__(self, key=ord('q'), visible=1):
        self.key, self.visible = key, visible
        self.opened = self.destroyed = False
        self.frames = 0
    def namedWindow(self, *args): self.opened = True
    def resizeWindow(self, *args): pass
    def putText(self, *args): pass
    def imshow(self, *args): self.frames += 1
    def waitKey(self, *args): return self.key
    def getWindowProperty(self, *args): return self.visible
    def destroyAllWindows(self): self.destroyed = True


class FakeDevice:
    def __init__(self, delay=0.0):
        self.closed = False
        self.delay_value = delay
        self.cleared = 0
    def __enter__(self): return self
    def __exit__(self, *exc): self.closed = True
    def properties(self): return SimpleNamespace(width=32, height=24)
    def clear_backlog(self, **kw): self.cleared += 1
    def __iter__(self):
        import numpy as np
        ev = np.array([(1000, 2, 3, True)], dtype=[('t', '<u8'), ('x', '<u2'), ('y', '<u2'), ('on', '?')])
        for _ in range(3):
            status = SimpleNamespace(ring=SimpleNamespace(current_t=1000, backlog=0),
                                     delay=lambda: self.delay_value)
            yield status, SimpleNamespace(polarity_events=ev)


class CameraLoopTests(unittest.TestCase):
    def test_q_releases_camera_and_creates_no_files(self):
        device, cv = FakeDevice(), FakeCV()
        driver = SimpleNamespace(open=MagicMock(return_value=device))
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            try:
                os.chdir(d)
                fp.run_preview(threading.Event(), driver=driver, cv=cv)
                self.assertEqual(list(Path(d).rglob('*')), [])
            finally: os.chdir(old)
        driver.open.assert_called_once_with(iterator_timeout=0.01, iterator_maximum_raw_packets=8)
        self.assertTrue(device.closed)
        self.assertTrue(cv.destroyed)
        self.assertEqual(cv.frames, 1)

    def test_close_button_releases_camera(self):
        device, cv = FakeDevice(), FakeCV(key=-1, visible=0)
        fp.run_preview(threading.Event(), driver=SimpleNamespace(open=lambda **k: device), cv=cv)
        self.assertTrue(device.closed)
        self.assertTrue(cv.destroyed)

    def test_stop_before_camera_ready_exits_cleanly(self):
        device, cv = FakeDevice(), FakeCV()
        stop = threading.Event(); stop.set()
        fp.run_preview(stop, driver=SimpleNamespace(open=lambda **k: device), cv=cv)
        self.assertTrue(device.closed)
        self.assertFalse(cv.opened)

    def test_delayed_preview_only_clears_its_own_queue(self):
        device, cv = FakeDevice(delay=0.2), FakeCV()
        fp.run_preview(threading.Event(), driver=SimpleNamespace(open=lambda **k: device), cv=cv)
        self.assertEqual(device.cleared, 1)
        self.assertTrue(device.closed)

    def test_camera_error_cleans_window(self):
        device, cv = FakeDevice(), FakeCV()
        def fail(*args): raise RuntimeError('test disconnect')
        cv.waitKey = fail
        with self.assertRaisesRegex(RuntimeError, 'test disconnect'):
            fp.run_preview(threading.Event(), driver=SimpleNamespace(open=lambda **k: device), cv=cv)
        self.assertTrue(device.closed)
        self.assertTrue(cv.destroyed)


class ControllerTests(unittest.TestCase):
    def test_focus_launch_does_not_call_app_or_write_logs(self):
        p = MagicMock()
        p.poll.return_value = None
        p.stderr = StringIO('')
        p.stdin = StringIO()
        with patch.object(fp.subprocess, 'Popen', return_value=p) as spawn:
            f = fp.FocusSession(); f.start(Path(sys.executable))
        argv = spawn.call_args.args[0]
        self.assertEqual(argv[1], '-B')
        self.assertTrue(argv[2].endswith('focus_preview.py'))
        self.assertNotIn('app.py', ' '.join(argv))
        self.assertNotIn('--record', argv)
        kw = spawn.call_args.kwargs
        self.assertEqual(kw['env']['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertEqual(kw['stdout'], fp.subprocess.DEVNULL)
        self.assertEqual(kw['stderr'], fp.subprocess.PIPE)
        f.stop(); self.assertEqual(p.stdin.getvalue(), 'stop\n')
        self.assertTrue(f.closing)

    def test_double_start_refused(self):
        f = fp.FocusSession(); f.proc = MagicMock()
        f.proc.poll.return_value = None
        with self.assertRaises(RuntimeError): f.start(Path(sys.executable))

    def test_already_finished_stop_safe(self):
        f = fp.FocusSession(); f.stop()
        self.assertIsNone(f.collect_exit())

    def test_focus_has_no_dataset_or_detector_imports(self):
        tree = ast.parse((ROOT / 'focus_preview.py').read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.update(a.name.split('.')[0] for a in node.names)
            if isinstance(node, ast.ImportFrom): imports.add((node.module or '').split('.')[0])
        self.assertFalse(imports & {'app', 'rotor', 'activity', 'event_io', 'media', 'numba'})
        text = (ROOT / 'focus_preview.py').read_text()
        for forbidden in ('VideoWriter(', 'imwrite(', '.write_text(', '.write_bytes(', '.mkdir('):
            self.assertNotIn(forbidden, text)

    def test_controller_gates_recording_and_probe_on_focus(self):
        tree = ast.parse((ROOT / 'operator_gui.py').read_text())
        functions = {n.name:n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for name in ('start', 'refresh_connection', 'exit_app'):
            self.assertIn('focus.running', ast.unparse(functions[name]))
        self.assertIn('probe[\'busy\']', ast.unparse(functions['toggle_focus']))
        self.assertIn('focus.collect_exit()', ast.unparse(functions['poll']))

    def test_recording_arguments_unchanged_and_not_focus_related(self):
        form=dict(environment='Indoor',lens_mm='75',range_m='20',focus_m='20',f_number='',
                  illuminance_lux='',lighting='',aspect='front',profile='hover',repeat='1',duration='60')
        meta=operator_gui.metadata_from_form(form)
        args=operator_gui.recording_command(Path('/python'),Path('/data/test'),meta)
        self.assertIn('record',args)
        self.assertEqual(args[args.index('--duration')+1], '60')
        self.assertEqual(args[args.index('--period-input')+1], 'native')
        self.assertNotIn('focus_preview.py',' '.join(args))


if __name__ == '__main__':
    unittest.main()
