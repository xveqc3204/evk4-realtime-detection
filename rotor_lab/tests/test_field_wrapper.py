"""Wrapper/analysis checks. Synthetic fixtures are not real flight results."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import field
from rotor import EVENT_DTYPE, Settings, PatchTracker


def answers(raw='yes',filt='yes',cue='yes',valid='yes'):
    return dict(raw_target_seen=raw,filtered_target_seen=filt,cue_on_target=cue,valid_presentation=valid)


class OutcomeTests(unittest.TestCase):
    def test_cue_needs_both_log_and_association(self):
        self.assertEqual(field.evaluate_outcome(True,answers(),True,None),'PERIODIC_CUE_ON_KNOWN_TARGET')
        self.assertEqual(field.evaluate_outcome(True,answers(),False,None),'REVIEW_CONFLICT')
    def test_white_pixels_without_confirmed_flag_are_activity(self):
        self.assertEqual(field.evaluate_outcome(True,answers(cue='no'),False,None),'ACTIVITY_ONLY')
    def test_raw_only_is_activity(self):
        self.assertEqual(field.evaluate_outcome(True,answers(filt='no',cue='no'),False,None),'ACTIVITY_ONLY')
    def test_known_absent_evidence_is_not_unknown(self):
        self.assertEqual(field.evaluate_outcome(True,answers(raw='no',filt='no',cue='no'),False,None),'NO_TARGET_EVIDENCE')
    def test_unknown_is_never_miss(self):
        self.assertEqual(field.evaluate_outcome(True,{},False,None),'UNREVIEWED')
    def test_invalid_source_is_not_miss(self):
        self.assertEqual(field.evaluate_outcome(False,answers(raw='no',filt='no',cue='no'),False,None),'INCOMPLETE_RUN')
    def test_target_outside_view_not_miss(self):
        self.assertEqual(field.evaluate_outcome(True,answers(valid='no'),False,None),'INVALID_PRESENTATION')
    def test_background_cue_does_not_become_target_cue(self):
        self.assertEqual(field.evaluate_outcome(True,answers(raw='yes',filt='no',cue='no'),True,None),'ACTIVITY_ONLY')
    def test_white_no_cue_case_in_screenshot_is_not_forced_positive(self):
        tracker=PatchTracker(Settings())
        out=tracker.update([dict(center=[50.,50.],bbox=[30,30,70,70],hz=247.,pixels=9754)],100_000)
        self.assertEqual(out[0]['state'],'PENDING')
        self.assertFalse(out[0]['confirmed'])


class MarkerAndRateTests(unittest.TestCase):
    def marks(self,a=6_000_000,b=16_000_000):
        return [dict(type='operator_target_present',sensor_t_us=a),dict(type='operator_target_absent',sensor_t_us=b)]
    def test_single_pair(self):self.assertEqual(field.marked_interval(self.marks())[0],(6_000_000,16_000_000))
    def test_missing_pair(self):self.assertIsNone(field.marked_interval([])[0])
    def test_repeated_present(self):self.assertIsNone(field.marked_interval(self.marks()+self.marks()[:1])[0])
    def test_reversed_pair(self):self.assertIsNone(field.marked_interval(self.marks(10,5))[0])
    def test_missing_timestamp(self):self.assertIsNone(field.marked_interval(self.marks(None,5))[0])
    def test_bounded_binary_search_duplicates_and_edges(self):
        e=np.zeros(5,EVENT_DTYPE);e['t']=[1,2,2,2,5]
        for t,i in [(0,0),(1,0),(2,1),(3,4),(5,4),(6,5)]:self.assertEqual(field.lower_bound(e,t),i)
    def test_rate_interval_excludes_end(self):
        e=np.zeros(4,EVENT_DTYPE);e['t']=[0,1_000_000,2_000_000,3_000_000]
        self.assertEqual(field.raw_rate(e,1_000_000,3_000_000),1.)
    def test_bad_numeric(self):
        for v in ('-2','0','nan','inf'):
            with self.assertRaises(Exception):field.positive(v)


class AnalysisTests(unittest.TestCase):
    def test_missing_verification_never_looks_valid(self):
        with tempfile.TemporaryDirectory() as d:
            r=field.analyze(Path(d))
            self.assertEqual(r['outcome'],'INCOMPLETE_RUN')
    def test_source_manifest_unchanged_core(self):
        import hashlib
        m=field.load(field.ROOT/'BASELINE_MANIFEST.json')
        # Original manifest is preserved. The explicit activity patch changes
        # rotor.py and ui.py, with native-filter equivalence tested separately.
        for name,value in m['unchanged'].items():
            path=field.ROOT/name
            if name in ('rotor.py','ui.py'):
                path=field.ROOT/'reference'/('rotor_v03.py' if name=='rotor.py' else 'ui_v03.py.txt')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),value,name)
    def test_gui_baseline_defaults(self):
        cfg=field.load(field.ROOT/'settings.json')
        self.assertEqual((cfg['min_hz'],cfg['max_hz']),(80.,1200.))
        self.assertEqual(cfg['confirm_ms'],60.)
    def test_cli_is_lens_then_range(self):
        with patch.object(field,'record',return_value=0) as fn:
            field.main(['25','10'])
        a=fn.call_args.args[0]
        self.assertEqual(a.lens,25);self.assertEqual(a.distance,10);self.assertEqual(a.duration,30)

class RoundTripResultTests(unittest.TestCase):
    def fixture(self, root):
        from event_io import Recorder
        field.write_json(root/'session.json',dict(source_info={'source':'synthetic','width':16,'height':16}))
        # Ordered sparse stream covering 0..20 seconds; fake test data only.
        ev=np.zeros(201,EVENT_DTYPE);ev['t']=np.arange(201)*100_000;ev['x']=5;ev['y']=5
        writer=Recorder(root/'events.evs',{'source_info':{'source':'synthetic','width':16,'height':16}});writer.submit(ev);writer.close()
        field.write_json(root/'summary.json',dict(status='SOURCE_ENDED',events_received=201,events_written=201,recording_requested=True,observed_input_loss=False))
        field.write_json(root/'application_summary.json',dict(source_exitcode=0,error=None))
        field.write_json(root/'trial.json',dict(lens_mm=25.,range_m=10.,focus_m=20.,settings_hash='fixture',paired_recording=False))
        (root/'markers.jsonl').write_text('\n'.join(json.dumps(r) for r in [dict(type='operator_target_present',sensor_t_us=6_000_000),dict(type='operator_target_absent',sensor_t_us=16_000_000)])+'\n')
        (root/'telemetry.jsonl').write_text('\n'.join(json.dumps(dict(type='decision',t_us=t,status='RUN',periodic_pixels=10 if t>=6_000_000 else 0,stable_pixels=10,rotor_candidate=t>=6_000_000)) for t in range(0,20_000_000,20_000))+'\n')
        field.verify(root)
    def test_record_and_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);field.write_json(p/'review.json',answers())
            r=field.analyze(p)
            self.assertEqual(r['outcome'],'PERIODIC_CUE_ON_KNOWN_TARGET')
            self.assertEqual(r['raw_events_s_present'],10.)
            self.assertEqual(r['raw_events_s_baseline'],10.)
            self.assertEqual(r['filtered_pixels_median_present'],10.)
            self.assertEqual(r['filtered_pixels_median_baseline'],0.)
            self.assertEqual(r['source'],'synthetic')
    def test_changed_source_invalidates_old_verification(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);field.write_json(p/'review.json',answers())
            with (p/'events.evs').open('ab') as f:f.write(b'broken')
            self.assertEqual(field.analyze(p)['outcome'],'INCOMPLETE_RUN')
    def test_plots_exclude_synthetic_and_unreviewed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);field.write_json(p/'review.json',answers())
            field.plots([field.analyze(p)],p)
            self.assertEqual(list(p.glob('*.png')),[])
    def test_stale_gui_flags_do_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p)
            rows=list(field.json_rows(p/'telemetry.jsonl'))
            for r in rows:r['status']='PROCESSING_OVERRUN'
            (p/'telemetry.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            field.verify(p);field.write_json(p/'review.json',answers())
            self.assertEqual(field.analyze(p)['outcome'],'REVIEW_CONFLICT')
