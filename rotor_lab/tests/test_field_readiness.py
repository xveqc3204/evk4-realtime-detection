"""Regression tests for data validity, worker faults and reproducibility."""
from __future__ import annotations
import contextlib
import io
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import numpy as np
from app import worker
from rotor import Settings, PeriodFilter, PatchTracker, group_pixels, EVENT_DTYPE
from event_io import Packet, periodic_events, FileSource, Recorder
from synthetic import QuadSpec, render_events, luminance_frame


class PeriodRegressionTests(unittest.TestCase):
    def test_readonly_input_does_not_recompile_after_warmup(self):
        from rotor import _consume
        f=PeriodFilter(Settings(),80,64);f.compile();n=len(_consume.signatures)
        e=periodic_events(duration_s=.05);e.flags.writeable=False
        f.push(e)
        self.assertEqual(len(_consume.signatures),n)
    def test_strided_input_does_not_recompile_after_warmup(self):
        from rotor import _consume
        f=PeriodFilter(Settings(),80,64);f.compile();n=len(_consume.signatures)
        e=periodic_events(duration_s=.05);f.push(e[::2])
        self.assertEqual(len(_consume.signatures),n)
        self.assertTrue(e.flags.writeable)
    def test_warmup_leaves_no_synthetic_pixel_state(self):
        f=PeriodFilter(Settings(),80,64);f.compile()
        self.assertEqual(f.latest_t,-1);self.assertEqual(f.maps(1000)[0].sum(),0)
    def test_multidimensional_events_are_rejected(self):
        f=PeriodFilter(Settings(),80,64)
        with self.assertRaises(ValueError):f.push(np.zeros((2,2),EVENT_DTYPE))
    def test_timestamp_integer_overflow_is_rejected(self):
        f=PeriodFilter(Settings(),80,64)
        with self.assertRaises(ValueError):f.push(np.array([(2**63,1,1,True)],EVENT_DTYPE))

    def test_raw_trail_setting_cannot_change_frequency_decision(self):
        # At 90 Hz, per-pixel periodic evidence remains valid after a 5 ms
        # raw trail expires. Old code incorrectly erased the frequency map.
        ev=periodic_events(hz=90,duration_s=.18,points=[(20,20),(21,20)],burst=1)
        filters=[PeriodFilter(Settings(view_ms=ms),48,40) for ms in [5,33,100]]
        for f in filters:f.push(ev)
        now=int(ev['t'][-1])+8000
        a,b,c=[f.maps(now)[1] for f in filters]
        self.assertGreater(np.count_nonzero(a),0)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(b,c)
    def test_event_kernel_independent_of_packet_split(self):
        ev=periodic_events(duration_s=.15,burst=4,jitter=.025)
        a=PeriodFilter(Settings(),80,64);b=PeriodFilter(Settings(),80,64)
        a.push(ev)
        for part in np.array_split(ev,197):b.push(part)
        np.testing.assert_array_equal(a.maps(a.latest_t)[1],b.maps(b.latest_t)[1])
    def test_equal_timestamp_burst_packet_boundary(self):
        ev=periodic_events(duration_s=.12,burst=2)
        ev['t']=(ev['t']//50)*50;ev.sort(order='t',kind='stable')
        a=PeriodFilter(Settings(),80,64);b=PeriodFilter(Settings(),80,64);a.push(ev)
        for i in range(0,len(ev),13):b.push(ev[i:i+13])
        np.testing.assert_array_equal(a.maps(a.latest_t)[1],b.maps(b.latest_t)[1])
    def test_empty_sensor_time_expires_filter_and_tracker(self):
        f=PeriodFilter(Settings(),80,64);ev=periodic_events();f.push(ev)
        tr=PatchTracker(f.cfg)
        r,_,_=group_pixels(f.maps(f.latest_t)[1],f.cfg,f.roi)
        for t in [250000,270000,290000,310000]:tr.update(r,t)
        r,_,_=group_pixels(f.maps(500000)[1],f.cfg,f.roi)
        self.assertEqual(tr.update(r,500000),[])
    def test_close_different_frequency_regions_remain_unverified(self):
        # Current grouping can merge adjacent sources; do not fabricate a
        # physical drone identity or assume each output is one rotor.
        f=np.zeros((64,80),np.float32);f[20:24,20:24]=240;f[24:28,24:28]=700
        r,_,_,m=group_pixels(f,Settings(),(0,0,80,64),True)
        self.assertTrue(all('drone' not in x for x in r))
        self.assertTrue(np.all((m==0)|(m==f)))
    def test_frequency_change_never_reuses_old_numeric_estimate(self):
        f=PeriodFilter(Settings(),80,64);f.push(periodic_events(hz=240,duration_s=.12))
        f.push(periodic_events(hz=600,duration_s=.12,start_us=130000))
        m=f.maps(f.latest_t)[1];self.assertGreater(np.count_nonzero(m),0)
        np.testing.assert_allclose(m[m>0],600,rtol=.02)
    def test_roi_reset_removes_old_frequencies(self):
        f=PeriodFilter(Settings(),80,64);f.push(periodic_events())
        f.set_roi((0,0,10,10));self.assertEqual(f.maps(300000)[1].sum(),0)
    def test_backward_timestamp_inside_packet_raises(self):
        f=PeriodFilter(Settings(),80,64)
        e=np.array([(100,1,1,True),(50,1,1,False)],EVENT_DTYPE)
        with self.assertRaises(ValueError):f.push(e)
    def test_excessive_regions_return_explicit_status(self):
        m=np.zeros((128,192),np.float32)
        for y in range(4,128,24):
            for x in range(4,192,24):m[y:y+3,x:x+3]=240
        r,status,_,supported=group_pixels(m,Settings(max_regions=4,global_tile_fraction=1),(0,0,192,128),True)
        self.assertEqual(status,'TOO_MANY_REGIONS');self.assertEqual(supported.sum(),0)


class ReplayAndSyntheticTests(unittest.TestCase):
    def test_quad_event_generator_is_repeatable(self):
        spec=QuadSpec(duration_s=.06,start_s=.01,stop_s=.05)
        np.testing.assert_array_equal(render_events(spec),render_events(spec))
    def test_quad_is_four_arm_geometry_not_a_trained_template(self):
        s=QuadSpec();c=s.centers(.2)
        self.assertEqual(c.shape,(4,2));self.assertEqual(luminance_frame(s,.2).shape,(144,192))
    def test_subthreshold_optics_have_no_target_events(self):
        s=QuadSpec(duration_s=.06,start_s=.01,stop_s=.05,contrast=.1,noise_events_s=0)
        self.assertEqual(len(render_events(s)),0)
    def test_file_source_preserves_events_with_large_initial_time(self):
        e=periodic_events(duration_s=.05);e['t']+=9000000000
        with tempfile.TemporaryDirectory() as d:
            w=Recorder(Path(d)/'a.evs',{'source_info':{'width':80,'height':64}});w.submit(e);w.close()
            with FileSource(Path(d)/'a.evs',False) as source:
                got=np.concatenate([p.events for p in source]);self.assertEqual(source.width,80)
            np.testing.assert_array_equal(e,got)
    def test_recording_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'x.evs';w=Recorder(path,{});w.close()
            with self.assertRaises(FileExistsError):Recorder(path,{})


class FakeSource:
    def __init__(self,fault):
        self.width=128;self.height=96;self.fault=fault;self.clears=0
        self.info=dict(source='mock_camera',width=128,height=96,name='SOFTWARE TEST')
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def clear(self):self.clears+=1
    def __iter__(self):
        ev=periodic_events(duration_s=.3,start_us=10000)
        i=0
        for end in range(20000,320001,20000):
            j=np.searchsorted(ev['t'],end,'left');yield Packet(ev[i:j],end,0.01,0);i=j
        if self.fault=='overflow':yield Packet(None,340000,0.01,0,True)
        if self.fault=='backlog':yield Packet(None,340000,0.01,300)
        if self.fault=='delay':yield Packet(None,340000,1000,0)
        if self.fault=='backwards':yield Packet(ev[:20],400000,.01,0)
        if self.fault=='silence':
            time.sleep(.065);yield Packet(None,None,None,0)
        if self.fault=='disconnect':raise RuntimeError('Injected camera disconnection')
        if self.fault=='quiet':yield Packet(np.zeros(0,EVENT_DTYPE),600000,.01,0)


class WorkerFaultTests(unittest.TestCase):
    def run_fault(self,kind):
        with tempfile.TemporaryDirectory() as d:
            source=FakeSource(kind)
            opts=dict(demo=False,replay=None,record=True,run_dir=d,duration=0,notes='fault test',roi=None)
            cfg=Settings(max_delay_ms=200,silence_ms=50)
            with patch('app.LiveSource',return_value=source),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                worker(opts,cfg.to_dict(),queue.Queue(1),queue.Queue(8),threading.Event())
            summary=json.loads((Path(d)/'summary.json').read_text())
            rows=[json.loads(x) for x in (Path(d)/'telemetry.jsonl').read_text().splitlines()]
            return source,summary,rows
    def check_clear(self,kind,reason):
        source,s,r=self.run_fault(kind)
        flags=[x for x in r if x['type']=='rotor_candidate']
        self.assertTrue(any(x['value'] for x in flags))
        self.assertFalse(flags[-1]['value'])
        self.assertTrue(any(x.get('reason')==reason for x in r))
        return source,s,r
    def test_usb_overflow_resets_flag_and_marks_recording(self):
        source,s,_=self.check_clear('overflow','input_overflow_or_backlog')
        self.assertEqual(source.clears,1);self.assertTrue(s['observed_input_loss']);self.assertFalse(s['no_observed_recording_loss'])
    def test_backlog_resets_flag(self):
        source,s,_=self.check_clear('backlog','input_overflow_or_backlog');self.assertEqual(source.clears,1)
    def test_old_driver_data_is_not_a_fresh_detection(self):
        source,s,_=self.check_clear('delay','input_overflow_or_backlog');self.assertEqual(source.clears,1)
    def test_timestamp_regression_clears_flag(self):
        _,s,_=self.check_clear('backwards','invalid_or_out_of_order_events');self.assertEqual(s['timestamp_resets'],1)
    def test_input_silence_clears_flag(self):self.check_clear('silence','no_recent_data')
    def test_quiet_watermark_clears_without_new_events(self):self.check_clear('quiet','no_recent_periodic_support')
    def test_disconnect_clears_flag_and_reports_error(self):
        _,s,r=self.run_fault('disconnect');self.assertEqual(s['status'],'ERROR')
        self.assertFalse([x for x in r if x['type']=='rotor_candidate'][-1]['value'])
        self.assertIn('disconnection',s['error'])


if __name__=='__main__':unittest.main(verbosity=2)
