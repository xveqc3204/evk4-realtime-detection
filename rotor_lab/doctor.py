"""Local pre-field checks. Run before leaving internet access and the lab.

No check here certifies drone recall, low-light performance, range or power.
A --camera check opens the actual EVK4, records briefly, then verifies the file.
Close other EVK4 processes first. A failing check should stop a data campaign.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parent


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--camera',action='store_true');p.add_argument('--seconds',type=float,default=15)
    a=p.parse_args(argv)
    if not 5<=a.seconds<=60:p.error('--seconds must be between 5 and 60')
    errors=[];warnings=[];results={'platform':platform.platform(),'python':sys.version,'checks':{},'versions':{}}
    for name in ['numpy','numba','opencv-python','matplotlib','neuromorphic_drivers']:
        try:results['versions'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f'Missing {name}. Run bash run.sh while online to install dependencies.')
    free=shutil.disk_usage(ROOT).free/1e9;results['free_disk_gb']=round(free,2)
    if free<5:errors.append('Less than 5 GB free. Free space before recording.')
    elif free<20:warnings.append('Less than 20 GB free. Use short trials and check the event rate.')
    try:
        from rotor import PeriodFilter,load_settings
        f=PeriodFilter(load_settings(ROOT/'settings.json'),32,24);f.compile()
        results['checks']['period_kernel_compiles']=True
    except Exception as exc:errors.append(f'Period estimator: {exc}')
    try:
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            file=str(Path(d)/'write_check.avi')
            w=cv2.VideoWriter(file,cv2.VideoWriter_fourcc(*'MJPG'),20,(320,180))
            if not w.isOpened():raise RuntimeError('No MJPG video writer')
            for _ in range(3):w.write(np.zeros((180,320,3),np.uint8))
            w.release();cap=cv2.VideoCapture(file);n=0
            while cap.isOpened():
                ok,_=cap.read()
                if not ok:break
                n+=1
            cap.release()
            if n!=3:raise RuntimeError(f'Decoded {n}/3 test frames')
        results['checks']['video_write_read']=True
    except Exception as exc:errors.append(f'Video codec check: {exc}')
    if a.camera and not errors:
        run=ROOT/'captures'/('preflight_'+time.strftime('%Y%m%d-%H%M%S')+'_'+uuid.uuid4().hex[:6])
        cmd=[sys.executable,str(ROOT/'app.py'),'live','--headless','--record','--duration',str(a.seconds),'--run-dir',str(run),'--notes','Local camera preflight, not target-validation evidence']
        print('Opening EVK4. Move a high-contrast object through the view. No GUI is opened.',flush=True)
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=(os.name=='posix'))
        try:output,_=proc.communicate(timeout=a.seconds+90)
        except subprocess.TimeoutExpired:
            if os.name=='posix':os.killpg(proc.pid,signal.SIGTERM)
            else:proc.terminate()
            try:output,_=proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name=='posix':os.killpg(proc.pid,signal.SIGKILL)
                else:proc.kill()
                output,_=proc.communicate()
            errors.append('Camera preflight timed out')
        print(output[-8000:])
        results['camera_run']=str(run)
        if proc.returncode:errors.append('Camera app exited with an error')
        if (run/'summary.json').exists():
            s=json.loads((run/'summary.json').read_text());results['camera_summary']=s
            if not s.get('events_received'):errors.append('No live events received')
            for key in ['source_clears','overflow_packets','timestamp_resets','processing_overruns']:
                if s.get(key):errors.append(f'Preflight recorded {key}={s[key]}')
            from verify_run import verify_run
            v=verify_run(run);results['file_verification']=v
            errors.extend(v['issues'])
        else:errors.append('Camera run did not produce summary.json')
    results.update(status='PASS' if not errors else 'FAIL',errors=errors,warnings=warnings,
        actual_camera_checked=bool(a.camera and 'camera_summary' in results),
        meaning='Software/acquisition check only. Next, verify the actual target visibly and retain raw events regardless of detection success.')
    path=ROOT/'validation';path.mkdir(exist_ok=True)
    (path/'local_preflight.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2));return int(bool(errors))

if __name__=='__main__':raise SystemExit(main())
