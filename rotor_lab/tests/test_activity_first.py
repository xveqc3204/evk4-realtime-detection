"""Tests of new rules, not measured drone detection performance."""
from pathlib import Path
from dataclasses import replace
import contextlib
import importlib.util
import io
import json
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np

from activity import (ActivitySettings,RawActivity,NeighborSupport,_raw_grid,
                       evidence_flags,load_activity_settings,FLAG_NAMES)
from rotor import PeriodFilter,Settings,EVENT_DTYPE
from event_io import periodic_events,Packet
import app,ui

ROOT=Path(__file__).resolve().parents[1]


def prepared(preset='sensitive',width=64,height=48):
    cfg=load_activity_settings(ROOT/'activity_presets.json',preset)
    obj=RawActivity(cfg,width,height);raw=np.full(width*height,-1,np.int64)
    for t in range(0,1_020_000,20_000):obj.update(raw,t,(0,0,width,height))
    return cfg,obj,raw


def hit(obj,raw,t,points):
    raw.fill(-1)
    for x,y in points:raw[y*obj.width+x]=t
    return obj.update(raw,t,(0,0,obj.width,obj.height))


def fake_raw(x=20,span=300,motion=10,confirmed=True,state='CONFIRMED_ACTIVITY'):
    return dict(status='RUN',tracks=[dict(id=1,center=[x,20],bbox=[x-8,12,x+16,36],
                    pixels=12,z=8.,confirmed=confirmed,state=state,span_ms=span,displacement_px=motion)])


def periodic(x=20,tid=1):
    return dict(id=tid,bbox=[x-2,16,x+2,24],center=[x,20],hz=240.,pixels=8,confirmed=True,state='CONFIRMED_PERIODIC')


class RawTests(unittest.TestCase):
    def test_two_pixels_sensitive_but_not_baseline(self):
        for preset,expected in [('baseline',False),('sensitive',True)]:
            c,o,raw=prepared(preset)
            for t in (1_040_000,1_060_000,1_080_000):r=hit(o,raw,t,[(20,20),(21,20)])
            f=evidence_flags(r,[],t,c)['flags']
            self.assertEqual(f['ACTIVITY'],expected)
            self.assertFalse(f['ROTOR_EVIDENCE']);self.assertFalse(f['DRONE_CANDIDATE'])
    def test_one_hot_pixel_is_never_cluster(self):
        c,o,raw=prepared()
        for t in range(1_040_000,1_600_000,20_000):r=hit(o,raw,t,[(20,20)])
        self.assertFalse(r['tracks'])
    def test_isolated_pixels_do_not_join(self):
        c,o,raw=prepared()
        for t in (1_040_000,1_060_000,1_080_000):r=hit(o,raw,t,[(2,2),(50,40)])
        self.assertFalse(r['tracks'])
    def test_cluster_across_tile_boundary(self):
        c,o,raw=prepared()
        for t in (1_040_000,1_060_000):r=hit(o,raw,t,[(7,20),(8,20)])
        self.assertTrue(evidence_flags(r,[],t,c)['flags']['ACTIVITY'])
    def test_tentative_box_before_activity(self):
        c,o,raw=prepared();r=hit(o,raw,1_040_000,[(20,20),(21,20)])
        self.assertEqual(r['tracks'][0]['state'],'PENDING')
        self.assertFalse(evidence_flags(r,[],1_040_000,c)['flags']['ACTIVITY'])
    def test_coast_is_not_fresh_activity(self):
        c,o,raw=prepared()
        for t in (1_040_000,1_060_000):hit(o,raw,t,[(20,20),(21,20)])
        r=hit(o,raw,1_080_000,[])
        self.assertEqual(r['tracks'][0]['state'],'COASTING')
        self.assertFalse(evidence_flags(r,[],1_080_000,c)['flags']['ACTIVITY'])
    def test_retention_expires(self):
        c,o,raw=prepared()
        hit(o,raw,1_040_000,[(20,20),(21,20)])
        r=hit(o,raw,1_300_000,[]);self.assertFalse(r['tracks'])
    def test_noise_flood_rejected(self):
        c,o,raw=prepared();raw.fill(1_040_000)
        r=o.update(raw,1_040_000,(0,0,64,48))
        self.assertEqual(r['status'],'GLOBAL_RAW_ACTIVITY');self.assertFalse(r['tracks'])
    def test_support_does_not_depend_on_raw_view_ms(self):
        c,o,raw=prepared();raw[20*64+20]=1_039_000;raw[20*64+21]=1_039_000
        counts,*_= _raw_grid(raw,64,48,(0,0,64,48),1_040_000,20_000,8)
        self.assertEqual(int(counts.sum()),2)
    def test_half_open_time_window(self):
        raw=np.array([80_000,80_001,100_000,100_001],np.int64)
        cnt,*_=_raw_grid(raw,4,1,(0,0,4,1),100_000,20_000,8)
        self.assertEqual(cnt.sum(),2)
    def test_identical_sensor_time_cannot_confirm(self):
        c,o,raw=prepared();r=hit(o,raw,1_040_000,[(20,20),(21,20)])
        for _ in range(4):r=hit(o,raw,1_040_000,[(20,20),(21,20)])
        self.assertFalse(r['tracks'])
    def test_roi_excludes_external_pixels(self):
        c,o,raw=prepared();raw[20*64+50]=1_040_000
        r=o.update(raw,1_040_000,(0,0,32,48));self.assertEqual(r['raw_pixels'],0)
    def test_odd_geometry(self):
        c,o,raw=prepared(width=67,height=51)
        for t in (1_040_000,1_060_000):r=hit(o,raw,t,[(65,49),(66,50)])
        self.assertEqual(r['tracks'][0]['bbox'],[64,48,67,51])
    def test_new_tracks_do_not_inherit_old_id(self):
        c,o,raw=prepared();r=hit(o,raw,1_040_000,[(20,20),(21,20)]);tid=r['tracks'][0]['id']
        o.reset();r=hit(o,raw,1_080_000,[(20,20),(21,20)])
        self.assertGreater(r['tracks'][0]['id'],tid)
    def test_stationary_foreground_is_not_learned_away(self):
        c,o,raw=prepared()
        for t in range(1_040_000,4_000_000,20_000):r=hit(o,raw,t,[(20,20),(21,20)])
        self.assertTrue(evidence_flags(r,[],t,c)['flags']['ACTIVITY'])
    def test_only_three_sensitive_parameters_differ(self):
        a=load_activity_settings(ROOT/'activity_presets.json','baseline').to_dict()
        b=load_activity_settings(ROOT/'activity_presets.json','sensitive').to_dict()
        self.assertEqual({k for k in a if a[k]!=b[k]}, {'z_threshold','min_pixels','confirm_hits'})
    def test_invalid_config_rejected(self):
        for kwargs in [dict(min_pixels=1),dict(z_threshold=float('nan')),dict(confirm_hits=1),dict(cell_px=0)]:
            with self.assertRaises(ValueError):replace(ActivitySettings(),**kwargs).validate()


class EvidenceTests(unittest.TestCase):
    def test_raw_without_rotor_still_cues(self):
        e=evidence_flags(fake_raw(),[],1_000_000,ActivitySettings())
        self.assertEqual(e['flags'],dict(ACTIVITY=True,ROTOR_EVIDENCE=False,DRONE_CANDIDATE=False))
        self.assertEqual(e['unknown_reason'],'insufficient_rotor_evidence')
    def test_periodic_only_is_not_drone_candidate(self):
        e=evidence_flags(dict(status='RUN',tracks=[]),[periodic()],1_000_000,ActivitySettings())
        self.assertTrue(e['flags']['ROTOR_EVIDENCE']);self.assertFalse(e['flags']['DRONE_CANDIDATE'])
    def test_spatially_unrelated_periodicity_not_drone(self):
        e=evidence_flags(fake_raw(),[periodic(60)],1_000_000,ActivitySettings())
        self.assertFalse(e['flags']['DRONE_CANDIDATE'])
    def test_immature_match_not_drone(self):
        e=evidence_flags(fake_raw(span=40),[periodic()],1_000_000,ActivitySettings())
        self.assertFalse(e['flags']['DRONE_CANDIDATE'])
    def test_mature_motion_and_coincident_periodicity(self):
        e=evidence_flags(fake_raw(),[periodic()],1_000_000,ActivitySettings())
        self.assertTrue(all(e['flags'].values()))
        self.assertIn('image_displacement',e['objects'][0]['reasons'])
    def test_multiple_patches_can_corroborate_hover(self):
        e=evidence_flags(fake_raw(motion=0),[periodic(20,1),periodic(30,2)],1_000_000,ActivitySettings())
        self.assertTrue(e['flags']['DRONE_CANDIDATE'])
    def test_stationary_single_fan_patch_stays_unknown(self):
        e=evidence_flags(fake_raw(motion=0),[periodic()],1_000_000,ActivitySettings())
        self.assertFalse(e['flags']['DRONE_CANDIDATE'])
    def test_moving_light_can_still_be_lookalike(self):
        # This intentionally documents a remaining ambiguity, not a rejection claim.
        e=evidence_flags(fake_raw(),[periodic()],1_000_000,ActivitySettings())
        self.assertTrue(e['flags']['DRONE_CANDIDATE']);self.assertEqual(e['identity'],'POSSIBLE_DRONE')
    def test_coasting_raw_never_drone(self):
        e=evidence_flags(fake_raw(state='COASTING'),[periodic()],1_000_000,ActivitySettings())
        self.assertFalse(e['flags']['ACTIVITY']);self.assertFalse(e['flags']['DRONE_CANDIDATE'])
    def test_invalid_is_not_negative_evidence(self):
        e=evidence_flags({},[],None,ActivitySettings(),valid=False)
        self.assertTrue(all(v is None for v in e['flags'].values()))
        self.assertEqual(e['unknown_reason'],'unavailable_invalid_data')
    def test_rejected_periodicity_does_not_gate_activity(self):
        e=evidence_flags(fake_raw(),[periodic()],1_000_000,ActivitySettings(),rotor_status='GLOBAL_PERIODIC_ACTIVITY')
        self.assertTrue(e['flags']['ACTIVITY']);self.assertFalse(e['flags']['ROTOR_EVIDENCE'])
    def test_flags_json_has_only_requested_keys(self):
        e=evidence_flags(fake_raw(),[],1_000_000,ActivitySettings())
        self.assertEqual(set(e['flags']),set(FLAG_NAMES));json.dumps(e,allow_nan=False)


class NeighborTests(unittest.TestCase):
    def test_isolated_pixel_cannot_support_itself(self):
        e=periodic_events(240,.2,[(8,8)])
        n=NeighborSupport(32,32);self.assertFalse(n.mask(e).any())
    def test_neighbor_in_causal_time(self):
        e=np.array([(100,4,4,True),(200,5,4,True),(2000,6,4,True)],dtype=EVENT_DTYPE)
        n=NeighborSupport(32,32)
        np.testing.assert_array_equal(n.mask(e),[False,True,False])
    def test_mask_false_retains_raw_events(self):
        e=periodic_events(240,.2,[(8,8)])
        f=PeriodFilter(Settings(),32,32);f.push(e,np.zeros(len(e),bool))
        self.assertEqual(f.latest_t,int(e['t'][-1]));self.assertGreaterEqual(f.last_event[8*32+8],0)
        self.assertFalse(f.maps(f.latest_t)[1].any())
    def test_nontrivial_pattern_preserves_raw_arrays(self):
        e=periodic_events(240,.2,[(8,8),(9,8)])
        f=PeriodFilter(Settings(),32,32);g=PeriodFilter(Settings(),32,32)
        f.push(e);g.push(e,np.arange(len(e))%2==0)
        np.testing.assert_array_equal(f.last_event,g.last_event);np.testing.assert_array_equal(f.raw_on,g.raw_on)
    def test_invalid_mask(self):
        f=PeriodFilter(Settings(),32,32);e=np.zeros(2,dtype=EVENT_DTYPE)
        for m in [np.zeros(1,bool),np.zeros(2,float),np.zeros((1,2),bool)]:
            with self.assertRaises(ValueError):f.push(e,m)
    def test_filter_toggle_does_not_erase_raw(self):
        f=PeriodFilter(Settings(),32,32);e=periodic_events(240,.2,[(8,8)])
        f.push(e);raw=f.last_event.copy();t=f.latest_t;f.reset_periods()
        np.testing.assert_array_equal(raw,f.last_event);self.assertEqual(f.latest_t,t)
    def test_native_mode_equivalent_to_archived_filter(self):
        path=ROOT/'reference/rotor_v03.py'
        spec=importlib.util.spec_from_file_location('reference_rotor_v03',path)
        old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
        a=old.PeriodFilter(old.Settings(),32,32);b=PeriodFilter(Settings(),32,32)
        e=periodic_events(240,.3,[(8,8),(9,8),(10,8)],jitter=.01)
        for start in range(0,len(e),37):
            chunk=e[start:start+37];a.push(chunk);b.push(chunk)
            ar,af=a.maps(a.latest_t);br,bf=b.maps(b.latest_t)
            np.testing.assert_array_equal(ar,br);np.testing.assert_array_equal(af,bf)


class UITests(unittest.TestCase):
    def test_three_flags_render(self):
        snap=dict(kind='frame',status='RUN',evaluated_monotonic=100,flags=dict(ACTIVITY=True,ROTOR_EVIDENCE=False,DRONE_CANDIDATE=False),
                  raw=np.zeros((24,32),np.uint8),frequency=np.zeros((24,32),np.float32),tracks=[],activity_tracks=[],width=64,height=48,
                  identity='UNKNOWN',unknown_reason='insufficient_rotor_evidence',reason_detail='No associated period evidence')
        f=ui.draw_frame(snap,Settings(),now=100)
        self.assertEqual(f.shape,(900,1440,3));self.assertTrue(f.any())
    def test_raw_history_does_not_require_frequency(self):
        h=ui.History();r=fake_raw()['tracks'][0]
        h.add(dict(kind='frame',t_us=100000,activity_tracks=[r]))
        self.assertEqual(len(h.points[1]),1)

if __name__=='__main__':unittest.main()
