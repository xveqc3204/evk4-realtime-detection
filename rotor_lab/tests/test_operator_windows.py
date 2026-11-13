"""Windows-specific GUI compatibility, no Windows or camera needed."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import operator_gui as gui


class WindowsCompatibility(TestCase):
    def test_windows_connected_using_camera_driver_discovery(self):
        def runner(cmd, **kwargs):
            self.assertEqual(cmd[1], '-c')
            self.assertIn('print_device_list', cmd[2])
            return SimpleNamespace(returncode=0, stdout='Prophesee EVK4 | USB 3.0 | serial')
        state, _ = gui.inspect_usb_connection(
            platform_name='win32', runner=runner, camera_python=Path('C:/Python310/python.exe'))
        self.assertEqual(state, 'connected')

    def test_windows_disconnected(self):
        def runner(cmd, **kwargs):
            return SimpleNamespace(returncode=0, stdout='No available devices')
        state, _ = gui.inspect_usb_connection(
            platform_name='win32', runner=runner, camera_python=Path('C:/Python310/python.exe'))
        self.assertEqual(state, 'disconnected')

    def test_windows_unavailable_when_driver_not_ready(self):
        self.assertEqual(gui.inspect_usb_connection(platform_name='win32')[0], 'unavailable')
        def runner(cmd, **kwargs):
            return SimpleNamespace(returncode=1, stdout='')
        self.assertEqual(gui.inspect_usb_connection(platform_name='win32', runner=runner,
            camera_python=Path('C:/Python310/python.exe'))[0], 'unavailable')

    def test_mac_usb_probe_unchanged(self):
        def runner(cmd, **kwargs):
            self.assertEqual(cmd, ['system_profiler', 'SPUSBDataType'])
            return SimpleNamespace(returncode=0, stdout=' EVK4:\n  Manufacturer: Prophesee')
        self.assertEqual(gui.inspect_usb_connection(platform_name='darwin', runner=runner)[0], 'connected')

    def test_camera_recording_flags_identical(self):
        f=dict(environment='Indoor',lens_mm='75',range_m='20',focus_m='20',
            f_number='',illuminance_lux='',lighting='test',aspect='front',profile='hover',
            repeat='1',duration='60')
        meta=gui.metadata_from_form(f)
        cmd=gui.recording_command(Path('/venv/bin/python'), Path('/tmp/test_run'),meta)
        self.assertEqual(cmd[1], str(gui.ROOT / 'app.py'))
        self.assertIn('--activity-preset',cmd)
        self.assertEqual(cmd[cmd.index('--activity-preset')+1], 'sensitive')
        self.assertEqual(cmd[cmd.index('--period-input')+1], 'native')
        self.assertEqual(cmd[cmd.index('--duration')+1], '60')

    def test_windows_environment_discovery_paths_present(self):
        import inspect
        s=inspect.getsource(gui.discover_camera_python)
        self.assertIn("'.venv/Scripts/python.exe'", s)
        self.assertIn('EVK4_PYTHON',s)

    def test_windows_does_not_send_posix_stop(self):
        import inspect
        s=inspect.getsource(gui.run_gui)
        self.assertIn("sys.platform == 'win32'",s)
        self.assertIn('press Q',s)

    def test_bat_launcher_and_docs_exist_in_addon(self):
        root=Path(__file__).resolve().parents[2]
        launcher=root / 'Start EBS Tests.bat'
        self.assertTrue(launcher.is_file())
        content=launcher.read_text()
        self.assertIn('py -3.10',content)
        self.assertIn('operator_gui.py',content)
        self.assertTrue((root/'docs/PLATFORM_SETUP.md').is_file())
