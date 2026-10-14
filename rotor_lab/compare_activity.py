"""Replay one identical event file through baseline and sensitive raw settings.

Original events/settings are read only. Outputs are new. Accuracy is not
inferred from file names, synthetic labels, or the historical periodic flag.
Optional annotations contain explicit sensor-time intervals and optional boxes.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import numpy as np
from rotor import Settings
from activity import FLAG_NAMES

ROOT=Path(__file__).resolve().parent


def read_json(path,default=None):
    return json.loads(path.read_text()) if path.exists() else ({} if default is None else default)


def read_rows(path):
    with path.open() as fh:
        for line in fh:
            if line.strip():yield json.loads(line)


def iou(a,b):
    x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]))
    intersection=x*y;union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0.


def annotations(path):
    if path is None:return []
    values=read_json(path)
    if not isinstance(values,list):raise ValueError('Annotations must be a list of intervals')
    last=-1
    for r in values:
        a,b=r['start_us'],r['end_us']
        if isinstance(a,bool) or isinstance(b,bool) or not isinstance(a,(int,float)) or not isinstance(b,(int,float)):
            raise ValueError('Interval boundaries must be numeric sensor microseconds')
        if not np.isfinite([a,b]).all() or a<0 or not a<b or a<last:
            raise ValueError('Annotations must be sorted, finite, non-overlapping intervals')
        if not isinstance(r['target_present'],bool):raise ValueError('target_present must be true or false')
        box=r.get('bbox')
        if box is not None and (len(box)!=4 or not np.isfinite(box).all() or not (box[0]<box[2] and box[1]<box[3])):
            raise ValueError('bbox must be [x0,y0,x1,y1], native sensor pixels')
        last=b
    return values


def score(rows,truth):
    """Time-weighted interval metrics; unknown gaps never count as negatives.

    Bboxes in annotations are supplied ground-truth regions, NOT generated.
    Use short intervals for moving boxes. IoU>=0.1 is a declared association
    criterion, not claimed localization accuracy. Mean IoU is reported too.
    """
    result=[]
    for flag in FLAG_NAMES:
        d=dict(flag=flag,annotated_present_s=0.,present_valid_s=0.,scene_cue_s=0.,
               spatially_scored_s=0.,associated_s=0.,absent_valid_s=0.,false_cue_s=0.,false_cue_episodes=0,
               unavailable_s=0.,id_switches=0,iou_values=[])
        for interval in truth:
            a,b=interval['start_us'],interval['end_us'];present=interval['target_present']
            if present:d['annotated_present_s']+=(b-a)/1e6
            previous=False;last_id=None;last_end=None
            covered=0.
            for i,r in enumerate(rows[:-1]):
                # Cap held results at 40 ms. Longer scheduling/data gaps are
                # unavailable, not interpolated detections or misses.
                start=max(a,r['t_us']);end=min(b,rows[i+1]['t_us'],r['t_us']+40000)
                if end<=start:continue
                dt=(end-start)/1e6;value=r.get('flags',{}).get(flag)
                if value is None or r.get('status')!='RUN':continue
                covered+=dt
                if last_end is None or start>last_end:previous=False;last_id=None
                last_end=end
                if present:
                    d['present_valid_s']+=dt
                    if value:d['scene_cue_s']+=dt
                    if interval.get('bbox') is not None:
                        d['spatially_scored_s']+=dt
                        matches=[(iou(o['bbox'],interval['bbox']),o['track_id']) for o in r.get('objects',[]) if o['flags'].get(flag)]
                        overlap,tid=max(matches,default=(0.,None))
                        d['iou_values'].append(overlap)
                        if overlap>=.1:
                            d['associated_s']+=dt
                            if last_id is not None and tid!=last_id:d['id_switches']+=1
                            last_id=tid
                        else:last_id=None
                else:
                    d['absent_valid_s']+=dt
                    if value:
                        d['false_cue_s']+=dt
                        if not previous:d['false_cue_episodes']+=1
                previous=bool(value)
            d['unavailable_s']+=max(0,(b-a)/1e6-covered)
        d['mean_box_iou']=float(np.mean(d.pop('iou_values'))) if d['iou_values'] else None
        d.pop('iou_values',None)
        d['scene_cue_fraction_during_presence']=d['scene_cue_s']/d['present_valid_s'] if d['present_valid_s'] else None
        d['associated_coverage_fraction']=d['associated_s']/d['spatially_scored_s'] if d['spatially_scored_s'] else None
        d['false_cue_episodes_per_minute']=d['false_cue_episodes']*60/d['absent_valid_s'] if d['absent_valid_s'] else None
        result.append(d)
    return result


def export(runs,out,truth,source_loss=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    by_preset={}; summaries=[];csvrows=[]
    for name,run in runs.items():
        rows=[r for r in read_rows(run/'telemetry.jsonl') if r.get('type')=='decision']
        by_preset[name]=rows
        for r in rows:
            row=dict(preset=name,t_us=r['t_us'],status=r['status'],unknown_reason=r.get('unknown_reason'),
                     raw_pixels=r.get('raw_activity',{}).get('raw_pixels'),periodic_pixels=r.get('periodic_pixels'),
                     map_and_group_ms=r.get('map_and_group_ms'),driver_delay_ms=r.get('delay_ms'))
            row.update(r.get('flags',{}));csvrows.append(row)
        valid=[r for r in rows if r.get('status')=='RUN']
        reasons={}
        for r in rows:
            key=r.get('unknown_reason') or 'possible_drone'
            reasons[key]=reasons.get(key,0)+1
        summaries.append(dict(preset=name,decisions=len(rows),unknown_reason_counts=reasons,
                     compute_p95_ms=float(np.percentile([r['map_and_group_ms'] for r in rows],95)) if rows else None,
                     annotation_metrics=score(rows,truth) if truth and not source_loss else None))
    if csvrows:
        with (out/'comparison.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(csvrows[0]));w.writeheader();w.writerows(csvrows)
    for flag in FLAG_NAMES:
        fig,ax=plt.subplots(figsize=(9,3.8))
        for name,rows in by_preset.items():
            vals=[np.nan if r.get('flags',{}).get(flag) is None else int(r['flags'][flag]) for r in rows]
            ax.step([r['t_us']/1e6 for r in rows],vals,where='post',label=name)
        ax.set(xlabel='Sensor time (s)',ylabel=flag,yticks=[0,1],ylim=(-.1,1.15))
        ax.legend();ax.grid(alpha=.2);fig.tight_layout()
        for ext in ('png','svg'):fig.savefig(out/f'{flag.lower()}.{ext}',dpi=180)
        plt.close(fig)
    notes=['Same event file and rotor settings for both replays. Only the named raw preset changes.',
           'Graphs are algorithm outputs, not drone accuracy. No ground truth is inferred.',
           'Raw counts are distinct native pixels active over 20 ms, not the 33 ms visual trail.',
           'Input loss cannot be recovered by replay. No latency, recall or prop resolution claim is implied.',
           'IoU scoring requires supplied boxes. Presence-only markers provide only scene cue coverage.',
           'Replay compute time is not live USB or end-to-end latency.']
    if source_loss:notes.append('ORIGINAL RECORDING REPORTS DATA LOSS: accuracy metrics withheld; outputs are exploratory.')
    if not truth:notes.append('No annotations supplied: missed detections, false cues, box accuracy and ID switches not evaluated.')
    (out/'comparison_summary.json').write_text(json.dumps(dict(runs=summaries,notes=notes),indent=2))
    (out/'READ_ME.txt').write_text('\n'.join(notes)+'\n')
    return summaries


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('recording');p.add_argument('--period-input',choices=['native','neighbor'],default='native')
    p.add_argument('--out');p.add_argument('--annotations')
    a=p.parse_args(argv);path=Path(a.recording).expanduser().resolve()
    if path.is_dir():path=path/'events.evs'
    if not path.is_file():p.error('Original events.evs not found. A movie is not replay input.')
    out=Path(a.out).expanduser().resolve() if a.out else ROOT/'captures'/('compare_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(parents=True,exist_ok=False)
    from event_io import read_recording
    header,ev=read_recording(path)
    if not len(ev):p.error('The recording contains no events')
    del ev
    session=read_json(path.parent/'session.json',header)
    saved=session.get('settings',header.get('settings'))
    if saved is None:p.error('Source rotor settings missing from session/header. Supply the original session.json.')
    cfg=Settings(**saved).validate();config_path=out/'rotor_settings.json'
    config_path.write_text(json.dumps(cfg.to_dict(),indent=2))
    truth=annotations(Path(a.annotations).expanduser()) if a.annotations else []
    source_loss=bool(read_json(path.parent/'summary.json').get('observed_input_loss',False))
    runs={}
    for preset in ('baseline','sensitive'):
        run=out/preset
        cmd=[sys.executable,str(ROOT/'app.py'),'replay',str(path),'--config',str(config_path),
             '--activity-preset',preset,'--period-input',a.period_input,'--headless','--unpaced','--run-dir',str(run)]
        print('Running',preset,flush=True)
        with (out/f'{preset}.log').open('w') as log:
            done=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if done.returncode:raise RuntimeError(f'{preset} failed. See {out/preset}.log')
        runs[preset]=run
    stat=path.stat()
    (out/'source.json').write_text(json.dumps(dict(path=str(path),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,
                                  period_input=a.period_input,source_reported_loss=source_loss),indent=2))
    export(runs,out,truth,source_loss)
    print('Comparison saved:',out)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,RuntimeError) as exc:raise SystemExit(str(exc))
