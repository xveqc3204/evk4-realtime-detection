"""Offline, non-camera tests for the EBS GUI connection indicator."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import operator_gui as gui

class OfflineLaunchTests(unittest.TestCase):
    def test_detects_evk4_by_usb_name(self):
        self.assertTrue(gui.parse_evk4_usb_listing('''USB:
  USB 3.1 Bus:
    EVK4:
      Manufacturer: Prophesee
'''))

    def test_ignores_other_usb_devices(self):
        self.assertFalse(gui.parse_evk4_usb_listing('USB:\n  Apple Keyboard:\n  Webcam:\n'))

    def test_macos_connected(self):
        def fake_run(command, **kwargs):
            self.assertEqual(command, ['system_profiler', 'SPUSBDataType'])
            return SimpleNamespace(returncode=0, stdout='  EVK4:\n    Manufacturer: Prophesee\n')
        self.assertEqual(gui.inspect_usb_connection(platform_name='darwin', runner=fake_run)[0], 'connected')

    def test_macos_disconnected(self):
        def fake_run(command, **kwargs):
            return SimpleNamespace(returncode=0, stdout='USB:\n  USB 3.0 Bus:\n')
        kind, detail = gui.inspect_usb_connection(platform_name='darwin', runner=fake_run)
        self.assertEqual(kind, 'disconnected')
        self.assertIn('Plug it in', detail)

    def test_macos_failed_probe_does_not_claim_disconnected(self):
        def fake_run(command, **kwargs):
            return SimpleNamespace(returncode=1, stdout='', stderr='not available')
        kind, detail = gui.inspect_usb_connection(platform_name='darwin', runner=fake_run)
        self.assertEqual(kind, 'unavailable')

    def test_offline_non_macos(self):
        self.assertEqual(gui.inspect_usb_connection(platform_name='linux')[0], 'unavailable')

    def test_offline_setup_no_camera_import(self):
        # GUI import and form validation do not require a physical camera or
        # import the camera driver. This does not test actual USB acquisition.
        self.assertNotIn('neuromorphic_drivers', gui.__dict__)
        form = dict(environment='Indoor', lens_mm='75', range_m='20', focus_m='20',
                    f_number='', illuminance_lux='', lighting='overhead',
                    aspect='front', profile='hover', repeat='1', duration='60')
        m = gui.metadata_from_form(form)
        self.assertEqual(m['range_m'],20.)
        self.assertEqual(m['requested_duration_s'],60)

if __name__=='__main__':
    unittest.main()
