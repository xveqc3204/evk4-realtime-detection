"""Saved-product checks, including missing RGB reference validity."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from media import MediaWriter
from verify_run import verify_run
from ui import CANVAS_W,CANVAS_H,draw_frame
from rotor import Settings


class CaptureIntegrityTests(unittest.TestCase):
    def prepare(self,p):
        (p/'session.json').write_text('{}')
        (p/'summary.json').write_text(json.dumps(dict(status='SOURCE_ENDED',recording_requested=False)))
        (p/'application_summary.json').write_text(json.dumps(dict(source_exitcode=0,error=None)))
    def test_missing_run_metadata_fails(self):
        with tempfile.TemporaryDirectory() as d:self.assertEqual(verify_run(d)['status'],'FAIL')
    def test_reported_input_loss_fails_verification(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.prepare(p)
            (p/'summary.json').write_text(json.dumps(dict(status='STOPPED',observed_input_loss=True)))
            self.assertEqual(verify_run(p)['status'],'FAIL')
    def test_missing_rgb_not_accepted_as_low_light_image(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.prepare(p);m=MediaWriter(p,20,rgb=True)
            images=dict(dashboard=np.zeros((CANVAS_H,CANVAS_W,3),np.uint8),
                        raw_events=np.zeros((360,640,3),np.uint8),
                        filtered_events=np.zeros((360,640,3),np.uint8),
                        rgb_preview=np.zeros((360,640,3),np.uint8))
            for i in range(3):m.submit(images,dict(gui_sequence=i,rgb_valid=False))
            self.assertIsNone(m.close()['error'])
            result=verify_run(p)
            self.assertEqual(result['status'],'FAIL')
            self.assertTrue(any('RGB' in x for x in result['issues']))
    def test_missing_rgb_is_visible_in_gui(self):
        # Text in an otherwise empty third panel makes absence explicit.
        f=draw_frame(dict(kind='status',status='WAITING_FOR_EVENTS'),Settings(),with_rgb=True,now=1)
        self.assertGreater(f[300:390,1000:1400].sum(),0)

if __name__=='__main__':unittest.main(verbosity=2)
