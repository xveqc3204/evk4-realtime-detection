from pathlib import Path
import contextlib
import io
import json
import queue
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
import app
from event_io import Packet
from rotor import EVENT_DTYPE,Settings
from compare_activity import score,annotations,iou


class MinimalSource:
    width=64; height=48
    info={'source':'test_only','width':64,'height':48}
    def __enter__(self):return self
    def __exit__(self,*exc):return False
    def clear(self):pass
    def __iter__(self):
        for t in range(5000,1805000,5000):
            # A two-pixel nonperiodic target with only ON events. It cannot
            # pass the unchanged ON/OFF periodicity estimator.
            ev=np.zeros(0,dtype=EVENT_DTYPE)
            if 1100000<=t<1500000:
                ev=np.array([(t,20,20,True),(t,21,20,True)],dtype=EVENT_DTYPE)
            yield Packet(ev,t)


def run_worker(preset='sensitive',cmds=None):
    with tempfile.TemporaryDirectory() as d:
        opts=dict(demo=False,replay=None,duration=0,record=False,video=False,run_dir=d,notes='',roi=None,
                  activity_preset=preset,period_input='native')
        q=queue.Queue(8)
        for command in cmds or []:q.put(command)
        # No physical timing assertion is made. Disable only the mocked
        # source's wall-time budget for deterministic integration checking.
        with patch.object(app,'LiveSource',return_value=MinimalSource()),contextlib.redirect_stdout(io.StringIO()):
            app.worker(opts,Settings(max_delay_ms=100000).to_dict(),queue.Queue(1),q,threading.Event())
        rows=[json.loads(x) for x in (Path(d)/'telemetry.jsonl').read_text().splitlines()]
        cues=[json.loads(x) for x in (Path(d)/'cues.jsonl').read_text().splitlines()]
        s=json.loads((Path(d)/'summary.json').read_text())
        meta=json.loads((Path(d)/'session.json').read_text())
        return rows,cues,s,meta


class IntegrationTests(unittest.TestCase):
    def test_raw_only_positive_in_complete_worker(self):
        rows,cues,s,meta=run_worker()
        decisions=[r for r in rows if r['type']=='decision']
        self.assertTrue(any(r['flags']['ACTIVITY'] for r in decisions))
        self.assertFalse(any(r['flags']['ROTOR_EVIDENCE'] for r in decisions))
        self.assertFalse(any(r['flags']['DRONE_CANDIDATE'] for r in decisions))
        self.assertFalse(s['observed_input_loss'])
        self.assertEqual(meta['activity_preset'],'sensitive')
    def test_conservative_baseline_does_not_detect_two_pixel_test(self):
        rows,cues,s,_=run_worker('baseline')
        self.assertFalse(any(r['flags']['ACTIVITY'] for r in rows if r['type']=='decision'))
    def test_cue_contains_native_coordinates_and_all_flags(self):
        _,cues,_,_=run_worker()
        cue=next(r for r in cues if r['type']=='cue' and r['flags']['ACTIVITY'])
        self.assertEqual(cue['coordinates'],'native_image_pixels');self.assertTrue(cue['track_id'].startswith('A'))
        self.assertIsInstance(cue['sensor_t_us'],int);self.assertEqual(len(cue['bbox']),4)
        self.assertEqual(set(cue['flags']),{'ACTIVITY','ROTOR_EVIDENCE','DRONE_CANDIDATE'})
    def test_shutdown_withdraws_cues(self):
        _,cues,_,_=run_worker()
        self.assertEqual(cues[-1]['type'],'status')
        self.assertTrue(all(v is None for v in cues[-1]['flags'].values()))
    def test_blocked_preview_queue_cannot_block_worker(self):
        _,_,s,_=run_worker()
        self.assertGreater(s['preview_skips'],0);self.assertNotEqual(s['status'],'ERROR')
    def test_control_change_logged_and_config_saved(self):
        rows,_,_,_=run_worker(cmds=[{'type':'activity_preset'},{'type':'period_input'}])
        changes=[r for r in rows if r['type']=='settings_changed']
        self.assertEqual(len(changes),2);self.assertEqual(changes[-1]['period_input'],'neighbor')


class ComparisonTests(unittest.TestCase):
    def test_iou(self):self.assertEqual(iou([0,0,10,10],[0,0,10,10]),1)
    def test_invalid_annotations(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';p.write_text('[{"start_us": 10, "end_us": 0, "target_present": true}]')
            with self.assertRaises(ValueError):annotations(p)
    def test_missing_truth_produces_no_accuracy(self):
        result=score([],[])
        self.assertTrue(all(r['associated_coverage_fraction'] is None for r in result))
    def test_present_only_labels_are_not_spatial_recall(self):
        rows=[dict(t_us=t,status='RUN',flags={k:True for k in ('ACTIVITY','ROTOR_EVIDENCE','DRONE_CANDIDATE')},objects=[])
              for t in (0,20000,40000)]
        result=score(rows,[dict(start_us=0,end_us=40000,target_present=True)])
        self.assertEqual(result[0]['scene_cue_fraction_during_presence'],1.)
        self.assertIsNone(result[0]['associated_coverage_fraction'])
    def test_invalid_is_not_miss(self):
        rows=[dict(t_us=t,status='ERROR',flags={},objects=[]) for t in (0,20000,40000)]
        result=score(rows,[dict(start_us=0,end_us=40000,target_present=True)])
        self.assertEqual(result[0]['present_valid_s'],0)
        self.assertAlmostEqual(result[0]['unavailable_s'],.04)
    def test_count_false_episodes_not_frames(self):
        rows=[dict(t_us=i*20000,status='RUN',flags={k:v for k in ('ACTIVITY','ROTOR_EVIDENCE','DRONE_CANDIDATE')},objects=[])
              for i,v in enumerate((False,True,True,False,True,False))]
        result=score(rows,[dict(start_us=0,end_us=100000,target_present=False)])
        self.assertEqual(result[0]['false_cue_episodes'],2)
    def test_spatial_support_scored_separately(self):
        o=dict(track_id='A1',bbox=[0,0,10,10],flags={'ACTIVITY':True})
        rows=[dict(t_us=t,status='RUN',flags={'ACTIVITY':True},objects=[o]) for t in (0,20000,40000)]
        result=score(rows,[dict(start_us=0,end_us=40000,target_present=True,bbox=[0,0,10,10])])
        self.assertEqual(result[0]['associated_coverage_fraction'],1.)
        self.assertEqual(result[0]['mean_box_iou'],1.)

if __name__=='__main__':unittest.main()

class SyntheticPacketTests(unittest.TestCase):
    def test_cached_demo_timestamps_preserve_all_events_and_boundaries(self):
        from synthetic import QuadSource
        ev=np.array([(1,0,0,True),(4999,1,0,False),(5000,1,1,True),
                     (9999,0,1,False)],dtype=EVENT_DTYPE)
        with patch('synthetic.render_events',return_value=ev.copy()):
            with QuadSource(duration=.01,realtime=False) as src:
                self.assertTrue(src._times.flags.c_contiguous)
                packets=list(src)
                self.assertEqual([len(p.events) for p in packets],[2,2])
                got=np.concatenate([p.events for p in packets])
                np.testing.assert_array_equal(got['t'],ev['t'])
                np.testing.assert_array_equal(got['x'],ev['x']+544)
                np.testing.assert_array_equal(got['y'],ev['y']+288)
