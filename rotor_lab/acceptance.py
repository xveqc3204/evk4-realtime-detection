"""One local end-to-end SOFTWARE acceptance command, no EVK4 needed.

Unit/fault tests, compact stress suite, generic quad recording with snapshots,
full movie decode, and event replay. A success is not a field certification.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parent

def main():
    root=ROOT/'validation'/('local_'+time.strftime('%Y%m%d-%H%M%S')+'_'+uuid.uuid4().hex[:6])
    root.mkdir(parents=True)
    steps=[
        ('regression',[sys.executable,'-m','unittest','discover','-s','tests','-v']),
        ('compact_stress',[sys.executable,'stress_test.py','--out',str(root/'stress')]),
        ('record',[sys.executable,'app.py','record','--demo','--scenario','quad','--duration','2','--no-window','--photos-every','1','--run-dir',str(root/'capture')]),
        ('verify',[sys.executable,'verify_run.py',str(root/'capture')]),
        ('replay',[sys.executable,'app.py','replay',str(root/'capture'/'events.evs'),'--headless','--unpaced','--run-dir',str(root/'replay')]),
    ]
    results=[]
    for name,cmd in steps:
        print(f'CHECK: {name}',flush=True)
        with (root/(name+'.log')).open('w') as f:
            result=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        results.append(dict(step=name,exitcode=result.returncode))
        if result.returncode:
            print((root/(name+'.log')).read_text()[-5000:]);break
    passed=len(results)==len(steps) and all(r['exitcode']==0 for r in results)
    (root/'acceptance.json').write_text(json.dumps(dict(status='PASS' if passed else 'FAIL',steps=results,
        real_camera_tested=False,meaning='Local software/media verification only; then run check --camera and visually test the actual target.'),indent=2))
    print(('PASS' if passed else 'FAIL')+': '+str(root))
    return int(not passed)
if __name__=='__main__':raise SystemExit(main())
