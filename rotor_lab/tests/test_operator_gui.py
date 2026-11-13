"""GUI recording wrapper checks. No real camera required."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from operator_gui import (metadata_from_form, unique_run_id, recording_command,
                          make_dataset_root, refresh_index, finalize_trial,
                          run_integrity, request_graceful_stop)


class GUIRecordingTests(unittest.TestCase):
    def form(self):
        return dict(environment='Indoor', lens_mm='75', range_m='20',
                    focus_m='20', f_number='2.8', illuminance_lux='1000',
                    lighting='Overhead diffuse light', aspect='front',
                    profile='hover', repeat='1', duration='60', notes='Test')

    def test_labels_not_classification(self):
        meta = metadata_from_form(self.form())
        self.assertEqual(meta['environment'], 'Indoor')
        self.assertEqual(meta['requested_duration_s'], 60)
        self.assertEqual(meta['period_input'], 'native')
        self.assertEqual(meta['activity_preset'], 'sensitive')
        self.assertNotIn('confidence', meta)

    def test_optional_measurements_are_not_fabricated(self):
        form = self.form()
        form['illuminance_lux'] = ''
        form['f_number'] = ''
        meta = metadata_from_form(form)
        self.assertIsNone(meta['illuminance_lux'])
        self.assertIsNone(meta['f_number'])

    def test_validated_controls(self):
        for name, value in [('environment', 'Garage'), ('lens_mm', '-2'),
                             ('range_m','nan'), ('duration','invalid'),
                             ('repeat','0'), ('duration','86401')]:
            form = self.form();form[name]=value
            with self.subTest(name=name), self.assertRaises(ValueError):
                metadata_from_form(form)

    def test_time_tag_and_uniqueness(self):
        meta=metadata_from_form(self.form())
        a=unique_run_id(meta)
        b=unique_run_id(meta)
        self.assertNotEqual(a,b)
        self.assertIn('__INDOOR__L75__R20__front__hover__REP1',a)

    def test_recording_uses_existing_camera_script(self):
        meta=metadata_from_form(self.form())
        cmd=recording_command(Path('/venv/bin/python'), Path('/tmp/take'),meta)
        self.assertEqual(cmd[2], 'record')
        self.assertIn('--config',cmd)
        self.assertIn('--run-dir',cmd)
        self.assertIn('--photos-every',cmd)
        self.assertEqual(cmd[cmd.index('--duration')+1], '60')
        self.assertNotIn('--band',cmd)
        self.assertNotIn('--notch',cmd)
        self.assertNotIn('--roi',cmd)
        self.assertNotIn('--rgb',cmd)
        self.assertIn('--activity-preset',cmd)
        self.assertIn('native',cmd)

    def test_manual_stop_uses_existing_live_recording_flags(self):
        f=self.form();f['duration']='0'
        meta=metadata_from_form(f)
        cmd=recording_command(Path('/venv/bin/python'), Path('/tmp/take'),meta)
        self.assertEqual(cmd[2], 'live')
        self.assertIn('--record',cmd)
        self.assertIn('--video',cmd)
        self.assertNotIn('--duration',cmd)

    def test_dataset_layout_and_index(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'Data'
            make_dataset_root(dest)
            self.assertTrue((dest/'Documents').is_dir())
            run=dest/'Tests'/'20261112__INDOOR_L75_R20'
            run.mkdir()
            (run/'events.evs').write_bytes(b'event bytes')
            (run/'dashboard.mp4').write_bytes(b'video bytes')
            (run/'raw_events.mp4').write_bytes(b'video bytes')
            (run/'filtered_events.mp4').write_bytes(b'video bytes')
            (run/'summary.json').write_text(json.dumps(dict(status='STOPPED',
                no_observed_recording_loss=True, events_written=25,
                observed_input_loss=False, source_clears=0)))
            (run/'application_summary.json').write_text(json.dumps(dict(error=None)))
            f=self.form();m=metadata_from_form(f)
            m['start_local']='2026-11-12T12:00:00-07:00'
            done=finalize_trial(dest,run,m,0,False)
            self.assertEqual(done['recording_status'],'RECORDED_UNREVIEWED')
            with (dest/'INDEX.csv').open() as fh:
                rows=list(csv.DictReader(fh))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['environment'],'Indoor')
            self.assertEqual(rows[0]['events_written'],'25')
            self.assertEqual(rows[0]['original_events'],'events.evs')
            self.assertEqual(rows[0]['filtered_events'],'filtered_events.mp4')
            self.assertEqual(rows[0]['folder'],'Tests/20261112__INDOOR_L75_R20')
            self.assertTrue((run/'trial.json').is_file())

    def test_operator_log_moves_inside_take(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            make_dataset_root(d)
            r=d/'Tests'/'recorded';r.mkdir()
            log=d/'_operator_recorded.log';log.write_text('original subprocess log')
            m=metadata_from_form(self.form())
            finalize_trial(d,r,m,0,True,operator_log=log)
            self.assertFalse(log.exists())
            self.assertEqual((r/'operator.log').read_text(),'original subprocess log')

    def test_data_loss_is_not_a_detection_miss(self):
        with tempfile.TemporaryDirectory() as td:
            run=Path(td)
            (run/'events.evs').write_bytes(b'e')
            (run/'dashboard.mp4').write_bytes(b'v')
            (run/'summary.json').write_text(json.dumps(dict(status='STOPPED',
                no_observed_recording_loss=False, observed_input_loss=True,
                source_clears=1, events_written=500)))
            self.assertEqual(run_integrity(run)['recording_status'],'DATA_GAP')

    def test_stop_sends_sigint_not_terminate(self):
        p=Mock()
        p.poll.return_value=None
        self.assertTrue(request_graceful_stop(p))
        p.send_signal.assert_called_once_with(signal.SIGINT)
        p.poll.return_value=0
        self.assertFalse(request_graceful_stop(p))
        self.assertEqual(p.send_signal.call_count,1)

    def test_unfinished_record_is_preserved_and_indexed(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            make_dataset_root(d)
            r=d/'Tests'/'failed';r.mkdir()
            m=metadata_from_form(self.form())
            out=finalize_trial(d,r,m,2,True)
            self.assertEqual(out['recording_status'],'NO_SUMMARY')
            self.assertTrue((r/'trial.json').is_file())
            self.assertTrue((d/'INDEX.csv').is_file())


if __name__=='__main__':
    unittest.main()
