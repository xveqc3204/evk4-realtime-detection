from __future__ import annotations
import csv
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from rotor import Settings,PeriodFilter,group_pixels,EVENT_DTYPE
from ui import polarity_image,filtered_image,clean_panels,is_fresh,History
from media import save_photo,MediaWriter
from report import forecast,export_report
from event_io import periodic_events


class NativeEvidenceTests(unittest.TestCase):
    def test_native_snapshot_polarities(self):
        f=PeriodFilter(Settings(),12,8)
        f.push(np.array([(1000,2,2,True),(2000,3,2,False)],EVENT_DTYPE))
        native=f.raw_native(2000)
        self.assertEqual(native.shape,(8,12));self.assertEqual(native[2,2],2);self.assertEqual(native[2,3],1)
    def test_preview_uses_latest_polarity_not_on_bias(self):
        f=PeriodFilter(Settings(),12,8)
        f.push(np.array([(1000,2,2,True),(2000,3,2,False)],EVENT_DTYPE))
        raw,_=f.maps(2000)
        self.assertEqual(raw[1,1],1)
    def test_raw_blue_yellow_palette(self):
        raw=np.array([[0,1,2]],np.uint8);img=polarity_image(raw)
        self.assertEqual(img[0,0].sum(),0)
        self.assertGreater(img[0,1,0],img[0,1,2])
        self.assertGreater(img[0,2,2],img[0,2,0])
    def test_filtered_is_binary_monochrome(self):
        img=filtered_image(np.array([[0,240,500]],np.float32))
        self.assertEqual(set(np.unique(img)),{0,255})
        np.testing.assert_equal(img[:,:,0],img[:,:,1]);np.testing.assert_equal(img[:,:,1],img[:,:,2])
    def test_isolated_periodic_pixel_removed_from_filtered_mask(self):
        freq=np.zeros((96,128),np.float32);freq[10,10]=240;freq[50:53,50:53]=500
        r,s,f,m=group_pixels(freq,Settings(),(0,0,128,96),return_map=True)
        self.assertEqual(m[10,10],0);self.assertEqual(np.count_nonzero(m),9)
        self.assertEqual(len(r),1)
    def test_pruned_mask_never_fills_boxes(self):
        freq=np.zeros((96,128),np.float32)
        for y,x in [(17,17),(17,18),(17,19),(18,17),(19,17),(19,19)]:freq[y,x]=240
        r,_,_,m=group_pixels(freq,Settings(),(0,0,128,96),return_map=True)
        self.assertEqual(len(r),1);self.assertEqual(np.count_nonzero(m),6);self.assertEqual(m[18,18],0)
    def test_global_activity_blanks_accepted_mask_not_raw(self):
        freq=np.full((96,128),240,np.float32)
        _,status,_,m=group_pixels(freq,Settings(),(0,0,128,96),return_map=True)
        self.assertEqual(status,'GLOBAL_PERIODIC_ACTIVITY');self.assertEqual(np.count_nonzero(m),0)
    def test_outlier_frequencies_removed_from_spatial_support(self):
        freq=np.zeros((96,128),np.float32);freq[30:34,30:34]=240;freq[30,30]=900
        _,_,_,m=group_pixels(freq,Settings(),(0,0,128,96),return_map=True)
        self.assertEqual(m[30,30],0);self.assertEqual(np.count_nonzero(m),15)
    def test_publication_cannot_make_old_evidence_fresh(self):
        s=dict(kind='frame',evaluated_monotonic=0,published_monotonic=10)
        self.assertFalse(is_fresh(s,Settings(),10.1))
    def test_monochrome_clean_view_blanks_after_silence(self):
        s=dict(kind='frame',evaluated_monotonic=0,frequency=np.full((5,5),240),raw=np.ones((5,5),np.uint8))
        raw,f=clean_panels(s,Settings(),now=2)
        self.assertEqual(raw.sum()+f.sum(),0)
    def test_different_sensor_geometries_supported(self):
        f=PeriodFilter(Settings(),53,35);f.push(periodic_events(points=[(52,34)],duration_s=.2))
        raw,m=f.maps(f.latest_t)
        self.assertEqual(raw.shape,(18,27));self.assertEqual(m.shape,(35,53));self.assertGreater(m[34,52],0)


class ExportTests(unittest.TestCase):
    def test_linear_image_projection_has_time_axis_not_depth(self):
        p=np.array([[t,20+30*t,100-4*t] for t in np.arange(0,.201,.02)])
        f=forecast(p,.1)
        self.assertIsNotNone(f)
        self.assertAlmostEqual(f['x'][-1],29);self.assertAlmostEqual(f['y'][-1],98.8)
        self.assertIn('not depth',f['meaning']);self.assertNotIn('z',f)
    def test_no_forecast_without_enough_evidence(self):
        self.assertIsNone(forecast([[0,1,1],[.02,2,2]]))
    def test_gui_history_never_invents_coasting_measurements(self):
        h=History();tr=dict(id=1,confirmed=True,state='COASTING',center=[20,20],hz=240)
        h.add(dict(kind='frame',t_us=1000,tracks=[tr]));self.assertEqual(len(h.points),0)
    def test_native_photo_has_frequency_array_csv_and_images(self):
        with tempfile.TemporaryDirectory() as d:
            raw=np.zeros((48,64),np.uint8);raw[10,10]=2
            freq=np.zeros((48,64),np.float32);freq[10:13,10:13]=240
            snap=dict(t_us=1000,kind='frame',evaluated_monotonic=1,tracks=[])
            b=dict(request_id='test',raw_native=raw,frequency_native=freq,cycle_only_frequency=freq.copy(),snapshot=snap)
            folder=save_photo(d,b)
            with np.load(folder/'pixel_data.npz') as data:
                np.testing.assert_equal(data['frequency_hz'],freq)
                self.assertEqual(int(data['sensor_t_us']),1000)
            rows=list(csv.DictReader((folder/'frequency_pixels.csv').open()))
            self.assertEqual(len(rows),9);self.assertTrue((folder/'raw_yellow_blue.png').exists())
    def test_empty_run_report_does_not_fabricate_tracks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'session.json').write_text(json.dumps(dict(source_info=dict(source='synthetic',width=128,height=96),settings=Settings().to_dict())))
            (p/'telemetry.jsonl').write_text('');(p/'summary.json').write_text('{"status":"SOURCE_ENDED"}')
            r=export_report(p)
            self.assertEqual(json.loads((r/'image_plane_forecasts.json').read_text()),{})
            m=json.loads((r/'manifest.json').read_text());self.assertEqual(m['third_axis'],'time_seconds_not_depth')
            self.assertEqual(m['track_ids_plotted'],[]);self.assertEqual(len(m['figures']),6)


if __name__=='__main__':unittest.main(verbosity=2)
