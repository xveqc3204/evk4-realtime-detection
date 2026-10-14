from __future__ import annotations
import json
from pathlib import Path
import queue
import tempfile
import unittest
import sys

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rotor import Settings, PeriodFilter, PatchTracker, group_pixels, reduce_frequency, EVENT_DTYPE, load_settings
from event_io import periodic_events, Recorder, read_recording, DemoSource
from app import draw_frame,newest


class FrequencyTests(unittest.TestCase):
    def make(self,**kwargs):return PeriodFilter(Settings(**kwargs),128,96)
    def test_periodic_240_hz(self):
        f=self.make();ev=periodic_events();f.push(ev);_,freq=f.maps(int(ev['t'][-1]))
        self.assertEqual(np.count_nonzero(freq),16)
        np.testing.assert_allclose(freq[freq>0],240,rtol=.01)
    def test_event_burst_count_does_not_multiply_frequency(self):
        for burst in (1,3,8):
            f=self.make();ev=periodic_events(burst=burst);f.push(ev);_,m=f.maps(int(ev['t'][-1]))
            np.testing.assert_allclose(m[m>0],240,rtol=.01)
            self.assertEqual(np.count_nonzero(m),16)
    def test_on_off_is_one_cycle_not_two(self):
        f=self.make();ev=periodic_events(hz=400);f.push(ev);_,m=f.maps(int(ev['t'][-1]))
        np.testing.assert_allclose(m[m>0],400,rtol=.01)
    def test_out_of_band(self):
        f=self.make(min_hz=300,max_hz=900);ev=periodic_events(hz=120);f.push(ev)
        self.assertEqual(np.count_nonzero(f.maps(int(ev['t'][-1]))[1]),0)
    def test_notch(self):
        f=self.make(notches_hz=[240]);ev=periodic_events();f.push(ev)
        self.assertEqual(np.count_nonzero(f.maps(int(ev['t'][-1]))[1]),0)
    def test_single_polarity_flood_is_not_periodicity(self):
        ev=np.zeros(50000,EVENT_DTYPE);ev['t']=np.arange(len(ev))*4
        ev['x']=32;ev['y']=32;ev['on']=True
        f=self.make();f.push(ev)
        self.assertEqual(np.count_nonzero(f.maps(200000)[1]),0)
    def test_too_few_cycles(self):
        f=self.make();ev=periodic_events(duration_s=.008);f.push(ev)
        self.assertEqual(np.count_nonzero(f.maps(int(ev['t'][-1]))[1]),0)
    def test_frequency_expires_without_new_cycles(self):
        f=self.make();ev=periodic_events();f.push(ev)
        self.assertGreater(np.count_nonzero(f.maps(int(ev['t'][-1]))[1]),0)
        self.assertEqual(np.count_nonzero(f.maps(int(ev['t'][-1])+100000)[1]),0)
    def test_frequency_jump_requires_reacquisition(self):
        f=self.make();a=periodic_events(hz=200,start_us=0,duration_s=.1);f.push(a)
        b=periodic_events(hz=500,start_us=100000,duration_s=.05);f.push(b)
        _,m=f.maps(int(b['t'][-1]));np.testing.assert_allclose(m[m>0],500,rtol=.01)
    def test_reset_clears_every_pixel(self):
        f=self.make();ev=periodic_events();f.push(ev);f.reset()
        raw,m=f.maps(250000)
        self.assertEqual(np.count_nonzero(raw)+np.count_nonzero(m),0)
    def test_software_roi_keeps_raw_but_rejects_frequency_outside(self):
        f=self.make();f.set_roi((60,50,100,90));ev=periodic_events();f.push(ev)
        raw,m=f.maps(int(ev['t'][-1]))
        self.assertGreater(raw.sum(),0);self.assertEqual(np.count_nonzero(m),0)
    def test_invalid_coordinates(self):
        f=self.make();ev=np.array([(1,300,0,1),(2,1,1000,0)],dtype=EVENT_DTYPE)
        self.assertEqual(f.push(ev),2)
    def test_timestamp_regression_is_not_silently_used(self):
        f=self.make();ev=periodic_events();f.push(ev)
        with self.assertRaises(ValueError):f.push(ev)
    def test_random_timing_is_not_a_supported_patch(self):
        rng=np.random.default_rng(7);ev=np.zeros(20000,EVENT_DTYPE)
        ev['t']=rng.integers(0,250000,len(ev));ev['x']=rng.integers(30,34,len(ev))
        ev['y']=rng.integers(30,34,len(ev));ev['on']=rng.integers(0,2,len(ev)).astype(bool)
        ev.sort(order='t');f=self.make();f.push(ev)
        _,m=f.maps(int(ev['t'][-1]));regions,_,_=group_pixels(m,f.cfg,f.roi)
        self.assertEqual(regions,[])
    def test_fan_or_led_lookalike_is_a_known_false_positive(self):
        # Identical optical timing is deliberately NOT claimed to distinguish identity.
        f=self.make();ev=periodic_events(hz=240);f.push(ev)
        self.assertGreater(np.count_nonzero(f.maps(int(ev['t'][-1]))[1]),0)


class GroupAndTrackTests(unittest.TestCase):
    def test_two_separate_periodic_patches(self):
        cfg=Settings();m=np.zeros((96,128),np.float32);m[16:20,16:20]=240;m[70:74,80:84]=500
        regs,status,_=group_pixels(m,cfg,(0,0,128,96))
        self.assertEqual(status,'RUN');self.assertEqual(len(regs),2)
    def test_isolated_pixel_not_a_candidate(self):
        cfg=Settings();m=np.zeros((96,128),np.float32);m[10,10]=240
        self.assertEqual(group_pixels(m,cfg,(0,0,128,96))[0],[])
    def test_global_periodicity_suppresses_flag_candidates(self):
        cfg=Settings();m=np.full((96,128),240,np.float32)
        regs,status,frac=group_pixels(m,cfg,(0,0,128,96))
        self.assertEqual(regs,[]);self.assertEqual(status,'GLOBAL_PERIODIC_ACTIVITY');self.assertEqual(frac,1)
    def test_persistence_and_loss(self):
        tracker=PatchTracker(Settings());r=dict(center=[30,30],bbox=[28,28,34,34],hz=240,pixels=16)
        for t in (0,20000,40000):self.assertFalse(tracker.update([r],t)[0]['confirmed'])
        self.assertTrue(tracker.update([r],60000)[0]['confirmed'])
        self.assertEqual(tracker.update([],80000)[0]['state'],'COASTING')
        self.assertEqual(tracker.update([],200000),[])
    def test_unrelated_new_source_does_not_inherit_confirmation(self):
        tracker=PatchTracker(Settings());r=dict(center=[30,30],bbox=[28,28,34,34],hz=240,pixels=16)
        for t in (0,20000,40000,60000):tracker.update([r],t)
        other=dict(r,center=[700,400],bbox=[698,398,704,404])
        out=tracker.update([other],80000)
        self.assertEqual(len(out),2);self.assertFalse(out[1]['confirmed'])
    def test_track_reset_does_not_reuse_ids(self):
        tracker=PatchTracker(Settings());r=dict(center=[30,30],bbox=[28,28,34,34],hz=240,pixels=16)
        first=tracker.update([r],0)[0]['id'];tracker.reset()
        self.assertGreater(tracker.update([r],100000)[0]['id'],first)
    def test_display_pooling_preserves_one_actual_supported_pixel(self):
        m=np.zeros((5,7),np.float32);m[4,6]=240
        p=reduce_frequency(m);self.assertEqual(p.shape,(3,4));self.assertEqual(np.count_nonzero(p),1)


class IOAndUITests(unittest.TestCase):
    def test_settings_reject_unknown_names(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';p.write_text('{"min_frequency": 20}')
            with self.assertRaises(ValueError):load_settings(p)
    def test_invalid_settings_rejected(self):
        for kw in [dict(min_hz=200,max_hz=100),dict(cycles=0),dict(period_tolerance=float('nan'))]:
            with self.assertRaises(ValueError):Settings(**kw).validate()
    def test_decoded_recording_roundtrip_and_owning_copy(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events.evs';ev=periodic_events(duration_s=.01);expected=ev.copy()
            w=Recorder(p,dict(source_info=dict(width=128,height=96)))
            self.assertTrue(w.submit(ev));ev['x']=99
            result=w.close();self.assertIsNone(result['recording_error'])
            h,e=read_recording(p);np.testing.assert_array_equal(e,expected)
    def test_recording_accepts_existing_creation_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.evs';w=Recorder(p,{'created_unix':1234.0});w.close()
            self.assertEqual(read_recording(p)[0]['created_unix'],1234.0)
    def test_recording_budget_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            w=Recorder(Path(d)/'x.evs',{},max_bytes=10)
            self.assertFalse(w.submit(np.zeros(10,EVENT_DTYPE)))
            self.assertIsNotNone(w.close()['recording_error'])
    def test_empty_recording(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.evs';w=Recorder(p,{});w.close()
            self.assertEqual(len(read_recording(p)[1]),0)
    def test_partial_event_file_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.evs';w=Recorder(p,{});w.close()
            with p.open('ab') as fh:fh.write(b'bad')
            with self.assertRaises(ValueError):read_recording(p)
    def test_latest_queue_bounded(self):
        q=queue.Queue(maxsize=1);newest(q,'first');newest(q,'second')
        self.assertEqual(q.qsize(),1);self.assertEqual(q.get(),'second')
    def test_stale_frame_blanks_event_views(self):
        cfg=Settings();snap=dict(kind='frame',status='RUN',flag=True,published_monotonic=0,
                               raw=np.ones((360,640),np.uint8)*255,
                               frequency=np.ones((360,640),np.float32)*240,tracks=[])
        frame=draw_frame(snap,cfg,now=2)
        self.assertEqual(frame.shape,(900,1440,3));self.assertEqual(frame[200:500,100:600].sum(),0)
    def test_empty_frame_does_not_keep_old_boxes(self):
        cfg=Settings();snap=dict(kind='frame',status='RUN',flag=False,published_monotonic=0,
                               raw=np.zeros((360,640),np.uint8),frequency=np.zeros((360,640),np.float32),tracks=[])
        frame=draw_frame(snap,cfg,now=.1)
        self.assertEqual(frame[200:500,100:600].sum(),0)
    def test_full_software_pipeline_synthetic_patch_confirms_then_clears(self):
        cfg=Settings();f=PeriodFilter(cfg);tr=PatchTracker(cfg);seen=False;last=-1
        with DemoSource(duration=2,realtime=False) as source:
            for pkt in source:
                f.push(pkt.events)
                if pkt.t_us-last>=20000:
                    _,m=f.maps(pkt.t_us);r,status,_=group_pixels(m,cfg,f.roi)
                    tt=tr.update(r,pkt.t_us);seen|=any(t['confirmed'] for t in tt);last=pkt.t_us
        self.assertTrue(seen);self.assertFalse(any(t['confirmed'] for t in tt))


if __name__=='__main__':unittest.main(verbosity=2)
