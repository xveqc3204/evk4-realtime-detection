"""Verify a saved experiment. File integrity is not detection accuracy."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from event_io import read_recording


def verify_run(path):
    path=Path(path);issues=[];warnings=[];details={}
    def load(name,required=True):
        p=path/name
        if not p.exists():
            if required:issues.append(f'Missing {name}')
            return {}
        try:return json.loads(p.read_text())
        except (OSError,ValueError) as e:issues.append(f'{name}: {e}');return {}
    session=load('session.json');summary=load('summary.json');app=load('application_summary.json')
    if summary.get('status') not in ('STOPPED','SOURCE_ENDED'):issues.append(f"Run state: {summary.get('status','missing')}")
    for k in ('error','photo_error'):
        if app.get(k):issues.append(f'Application {k}: {app[k]}')
    if app.get('source_exitcode') not in (0,None):issues.append('Source process exited abnormally')
    for k in ('error','recording_error'):
        if summary.get(k):issues.append(str(summary[k]))
    if summary.get('observed_input_loss'):issues.append('Observed input loss; keep files, mark this trial incomplete')
    if summary.get('invalid_coordinates',0):issues.append('Invalid event coordinates were observed')
    if (path/'FORCED_STOP.txt').exists():issues.append('Forced stop; file completeness unknown')
    evpath=path/'events.evs'
    if summary.get('recording_requested') or evpath.exists():
        try:
            h,e=read_recording(evpath);details['recorded_events']=len(e)
            if len(e)!=summary.get('events_written'):issues.append('Event count disagrees with summary')
            if summary.get('events_received')!=len(e):issues.append('Received/written event count mismatch')
            if not len(e):issues.append('No events recorded')
            # Bounded verification scans. Timestamp gaps alone are not proof of loss.
            previous=None;W=h.get('source_info',{}).get('width',1280);H=h.get('source_info',{}).get('height',720)
            for i in range(0,len(e),500000):
                part=e[i:i+500000];t=part['t']
                if len(t) and ((previous is not None and int(t[0])<previous) or np.any(t[1:]<t[:-1])):
                    issues.append('Out-of-order timestamps in event recording');break
                if len(t):previous=int(t[-1])
                if np.any(part['x']>=W) or np.any(part['y']>=H):issues.append('Coordinates exceed recorded geometry');break
        except Exception as exc:issues.append(f'Event file: {exc}')
    else:warnings.append('No event recording. Movie alone cannot be replayed through the detector.')
    if (path/'media.json').exists():
        import cv2
        media=load('media.json')
        if media.get('error'):issues.append(media['error'])
        if media.get('dropped_gui_frames'):warnings.append(f"Skipped {media['dropped_gui_frames']} GUI frames; use timestamps")
        csvpath=path/'video_frames.csv'
        rows=list(csv.DictReader(csvpath.open())) if csvpath.exists() else []
        if len(rows)!=media.get('encoded_frames'):issues.append('Video timestamp count mismatch')
        decoded={}
        for name,file in media.get('files',{}).items():
            cap=cv2.VideoCapture(str(path/file));n=0
            while cap.isOpened():
                ok,frame=cap.read()
                if not ok:break
                n+=1
            cap.release();decoded[name]=n
            if n!=len(rows) or n==0:issues.append(f'{name}: decoded {n} frames, expected {len(rows)}')
        details['decoded_video_frames']=decoded
        if 'rgb_preview' in media.get('files',{}):
            if not rows or 'rgb_valid' not in rows[0]:
                warnings.append('Legacy RGB recording has no explicit frame-validity field; visually inspect before comparison.')
            else:
                valid=sum(r.get('rgb_valid') in ('True','1','true') for r in rows)
                details['valid_rgb_frames']=valid
                if valid==0:issues.append('No fresh RGB frames. Fallback black frames are not low-light evidence.')
                elif valid<len(rows):warnings.append(f'{len(rows)-valid} video frames have no fresh RGB reference')
    for ph in (path/'photos').glob('*') if (path/'photos').exists() else []:
        try:
            with np.load(ph/'pixel_data.npz') as d:
                raw=d['raw_polarity'];freq=d['frequency_hz']
                if raw.shape!=freq.shape:issues.append(f'{ph.name}: photo geometry mismatch')
                if not np.isfinite(freq).all():issues.append(f'{ph.name}: nonfinite frequencies')
        except Exception as e:issues.append(f'{ph.name}: {e}')
    result=dict(status='PASS' if not issues else 'FAIL',issues=issues,warnings=warnings,details=details,
        meaning='Checks files, timestamps and reported losses. Does not certify missed detections, sensor-level losslessness, or drone identity.')
    (path/'verification.json').write_text(json.dumps(result,indent=2))
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_dir');a=p.parse_args(argv)
    r=verify_run(a.run_dir);print(json.dumps(r,indent=2));return int(r['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
