"""Small experiment wrapper around the archived v0.3 GUI and period filter.

Frequency settings are unchanged. The app adds a separate raw-activity cue.
No test box, motion veto, or new sensor integration is added.
Measurements below are OFFLINE and whole-view, not automatic target segmentation.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ['app.py','rotor.py','ui.py','event_io.py','media.py','settings.json','requirements.txt','field.py','activity.py','activity_presets.json']
QUESTIONS = {
    'valid_presentation':'Was the known target inside the camera view for the marked interval?',
    'raw_target_seen':'Was activity belonging to the target visible in the yellow/blue view?',
    'filtered_target_seen':'Were white frequency-supported pixels visible ON the target?',
    'cue_on_target':'Did ROTOR EVIDENCE=1 occur with a fresh confirmed patch ON the target?'
}


def load(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text())


def write_json(path: Path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    temp.replace(path)


def json_rows(path: Path):
    if path.exists():
        with path.open() as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def resolve_run(value='latest') -> Path:
    if value=='latest':
        link=ROOT/'captures/LAST_TRIAL.txt'
        if not link.exists():
            raise ValueError('No trial yet. Supply the exact run-folder path.')
        value=link.read_text().strip()
    p=Path(value).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f'Run folder not found: {p}')
    return p


def marked_interval(rows):
    """One 1/2 pair only. No silent replacement of missing/wrong annotations."""
    starts=[r.get('sensor_t_us') for r in rows if r.get('type')=='operator_target_present']
    ends=[r.get('sensor_t_us') for r in rows if r.get('type')=='operator_target_absent']
    if len(starts)!=1 or len(ends)!=1:
        return None,'Need exactly one target-present (1) and target-absent (2) marker.'
    a,b=starts[0],ends[0]
    if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not a<b:
        return None,'Markers need increasing sensor timestamps.'
    return (int(a),int(b)),None


def lower_bound(events, t):
    """Binary search without copying a multi-GB noncontiguous timestamp field."""
    lo,hi=0,len(events)
    while lo<hi:
        mid=(lo+hi)//2
        if int(events[mid]['t'])<t: lo=mid+1
        else: hi=mid
    return lo


def raw_rate(events,a,b):
    if b<=a: return None
    return (lower_bound(events,b)-lower_bound(events,a))*1e6/(b-a)


def evaluate_outcome(valid, review, any_logged_cue, annotation_issue):
    if not valid: return 'INCOMPLETE_RUN'
    if annotation_issue: return 'UNREVIEWED'
    vals=[review.get(k) for k in QUESTIONS]
    if any(v not in ('yes','no') for v in vals): return 'UNREVIEWED'
    present,raw,filt,cue=vals
    if present=='no': return 'INVALID_PRESENTATION'
    if cue=='yes':
        if not any_logged_cue or filt!='yes': return 'REVIEW_CONFLICT'
        return 'PERIODIC_CUE_ON_KNOWN_TARGET'
    if raw=='yes' or filt=='yes': return 'ACTIVITY_ONLY'
    return 'NO_TARGET_EVIDENCE'


def analyze(run: Path):
    """Read existing recordings. Never run/change the live estimator here."""
    import numpy as np
    from event_io import read_recording
    meta=load(run/'trial.json');session=load(run/'session.json');s=load(run/'summary.json')
    v=load(run/'verification.json');rev=load(run/'review.json')
    rows=list(json_rows(run/'telemetry.jsonl'))
    marks=list(json_rows(run/'markers.jsonl'))
    interval,annotation_issue=marked_interval(marks)
    decisions=[r for r in rows if r.get('type')=='decision' and isinstance(r.get('t_us'),(int,float))]
    valid=bool(v.get('status')=='PASS' and not s.get('observed_input_loss') and
               not s.get('recording_error') and s.get('events_received',0)>0)
    # Verification must correspond to the current files, not a copied earlier PASS.
    integrity_stamp=load(run/'verification_stamp.json')
    for name,stamp in integrity_stamp.items():
        p=run/name
        if not p.exists() or [p.stat().st_size,p.stat().st_mtime_ns]!=stamp: valid=False
    if not integrity_stamp: valid=False
    data=dict(run=run.name, lens_mm=meta.get('lens_mm'),range_m=meta.get('range_m'),
              focus_m=meta.get('focus_m'),f_number=meta.get('f_number'),lux=meta.get('lux'),
              aspect=meta.get('aspect','not_recorded'),profile=meta.get('profile','not_recorded'),
              repeat=meta.get('repeat'),operator_notes=meta.get('operator_notes',''),
              target=meta.get('target','unspecified'),source=session.get('source_info',{}).get('source'),
              settings_hash=meta.get('settings_hash'),activity_preset=session.get('activity_preset','not_recorded'),
              period_input=session.get('period_input','native'),activity_settings_hash=meta.get('activity_settings_hash'),verification=v.get('status','NOT_VERIFIED'),
              annotation_issue=annotation_issue,observed_input_loss=s.get('observed_input_loss'),
              source_clears=s.get('source_clears'),
              raw_target_seen=rev.get('raw_target_seen','unknown'),
              filtered_target_seen=rev.get('filtered_target_seen','unknown'),
              cue_on_target=rev.get('cue_on_target','unknown'),
              raw_events_s_present=None,raw_events_s_baseline=None,
              filtered_pixels_median_present=None,filtered_pixels_median_baseline=None,
              valid_decision_fraction=None,logged_cue_in_target_interval=False,
              max_stable_pixels_present=None,max_filtered_pixels_present=None,
              first_logged_cue_after_marker_s=None)
    if interval:
        a,b=interval
        part=[r for r in decisions if a<=r['t_us']<b]
        good=[r for r in part if r.get('status')=='RUN']
        base=[r for r in decisions if a-5_000_000<=r['t_us']<a and r.get('status')=='RUN']
        data['target_interval_s']=(b-a)/1e6
        data['valid_decision_fraction']=len(good)/len(part) if part else None
        for flag in ('ACTIVITY','ROTOR_EVIDENCE','DRONE_CANDIDATE'):
            data['logged_'+flag.lower()+'_in_target_interval']=any(
                r.get('flags',{}).get(flag) is True for r in good)
        data['unknown_reason_counts']={reason:sum(r.get('unknown_reason')==reason for r in good)
            for reason in sorted({r.get('unknown_reason') for r in good if r.get('unknown_reason')})}
        cues=[r for r in good if r.get('rotor_candidate')]
        data['logged_cue_in_target_interval']=bool(cues)
        data['first_logged_cue_after_marker_s']=(cues[0]['t_us']-a)/1e6 if cues else None
        if good:
            data['filtered_pixels_median_present']=float(np.median([r.get('periodic_pixels',0) for r in good]))
            data['max_stable_pixels_present']=max(r.get('stable_pixels',0) for r in good)
            data['max_filtered_pixels_present']=max(r.get('periodic_pixels',0) for r in good)
        if base:
            data['filtered_pixels_median_baseline']=float(np.median([r.get('periodic_pixels',0) for r in base]))
        if not part: annotation_issue='No recorded decisions in the target interval.'
        if valid:
            _,ev=read_recording(run/'events.evs')
            if len(ev):
                # Require a full five seconds before the marker within the recorded source time.
                if a < int(ev[0]['t'])+5_000_000:
                    annotation_issue='Less than five seconds of recorded baseline precedes target marker.'
                if b>int(ev[-1]['t']):
                    annotation_issue='Target-absent marker is beyond the recorded events.'
                data['raw_events_s_present']=raw_rate(ev,a,b)
                data['raw_events_s_baseline']=raw_rate(ev,max(int(ev[0]['t']),a-5_000_000),a)
            del ev
    if any(r.get('type')=='roi' for r in rows):
        annotation_issue='Analysis ROI changed during this run. Do not mix it with full-field trials.'
    data['annotation_issue']=annotation_issue
    data['outcome']=evaluate_outcome(valid,rev,data['logged_cue_in_target_interval'],annotation_issue)
    data['metric_scope']='Whole sensor view; pixel counts are not target-segmented. Visibility and cue association are operator-reviewed.'
    data['timing_note']='Markers use last displayed sensor time. First cue after marker is not total latency or verified cue-on-target onset.'
    write_json(run/'trial_result.json',data)
    return data


def verify(run: Path):
    from verify_run import verify_run
    result=verify_run(run)
    # Formal wrapper always requests all three movies and original events.
    if load(run/'trial.json').get('paired_recording'):
        media=load(run/'media.json')
        expected={'dashboard','raw_events','filtered_events'}
        if not expected.issubset(media.get('files',{})):
            result['issues'].append('Missing one or more paired dashboard/raw/filtered movies.')
        if not (run/'events.evs').exists():result['issues'].append('Missing original event recording.')
        result['status']='FAIL' if result['issues'] else 'PASS'
    write_json(run/'verification.json',result)
    files=['events.evs','summary.json','application_summary.json','session.json','media.json','video_frames.csv','telemetry.jsonl','markers.jsonl']
    stamp={n:[(run/n).stat().st_size,(run/n).stat().st_mtime_ns] for n in files if (run/n).exists()}
    write_json(run/'verification_stamp.json',stamp)
    return result


def review(run: Path):
    verification=verify(run)
    print('Recording verification:',verification['status'])
    for issue in verification['issues']:print('  ',issue)
    metrics=analyze(run)
    print('Fresh logged cue in marked target interval:',metrics['logged_cue_in_target_interval'])
    if metrics['annotation_issue']:print('ANNOTATION:',metrics['annotation_issue'])
    answers={}
    print('\nUse y = yes, n = no, u = unsure. Judge evidence ON the target, not elsewhere.')
    for key,text in QUESTIONS.items():
        while True:
            try:value=input(text+' [y/n/u]: ').strip().lower()
            except (EOFError,KeyboardInterrupt):
                print('\nReview left unfinished. Recording is retained.');return
            if value in ('y','n','u'):
                answers[key]={'y':'yes','n':'no','u':'unknown'}[value];break
    answers['reviewed_unix']=time.time()
    old=run/'review.json'
    if old.exists():shutil.copy2(old,run/('review_previous_'+uuid.uuid4().hex[:6]+'.json'))
    write_json(old,answers)
    result=analyze(run)
    print('RESULT:',result['outcome'])
    if result['outcome']=='REVIEW_CONFLICT':print('Observed cue conflicts with the recorded flag or filtered visibility. Keep this unresolved and inspect the movie/logs.')


def plots(records, out: Path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    usable=[r for r in records if r['outcome'] in ('PERIODIC_CUE_ON_KNOWN_TARGET','ACTIVITY_ONLY','NO_TARGET_EVIDENCE') and r.get('source')=='live']
    # Separate settings/focus/lux/aperture groups. Never silently pool unlike tests.
    groups={}
    for r in usable:
        key=(r['lens_mm'],r.get('focus_m'),r.get('f_number'),r.get('lux'),r.get('settings_hash'),r.get('target'),r.get('aspect','not_recorded'),r.get('profile','not_recorded'),r.get('activity_preset'),r.get('period_input'),r.get('activity_settings_hash'))
        groups.setdefault(key,[]).append(r)
    for gi,(key,rs) in enumerate(sorted(groups.items(),key=lambda pair:str(pair[0]))):
        rs.sort(key=lambda r:(r['range_m'],r['run']))
        lens,focus,ap,lux,_,target,aspect,profile,rawpreset,periodinput,_=key
        prefix=f'lens_{lens:g}_group_{gi+1}'
        title=f'{target} | {lens:g} mm lens | focus {focus:g} m | raw {rawpreset}, period {periodinput}\n{aspect} / {profile} | f/{ap or "not recorded"} | lux {lux or "not recorded"}'
        x=[r['range_m'] for r in rs]
        fig,ax=plt.subplots(figsize=(8,4.8))
        for field,label,marker in [('raw_target_seen','Raw target visible','o'),('filtered_target_seen','Filtered target visible','s'),('cue_on_target','Target-associated periodic cue','x')]:
            ax.scatter(x,[1 if r[field]=='yes' else 0 for r in rs],label=label,marker=marker,s={'o':130,'s':65,'x':36}[marker],alpha=.75)
        ax.set(xlabel='Measured range (m)',ylabel='Operator-reviewed result',yticks=[0,1],yticklabels=['No','Yes'],ylim=(-.2,1.3),title=title)
        ax.set_xticks(sorted(set(x)));ax.legend(loc='center',fontsize=9);ax.grid(axis='y',alpha=.2)
        fig.text(.5,.01,'Each symbol is one run. Overlap is possible. No fitted detection probability.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.05,1,1))
        for ext in ('png','svg'):fig.savefig(out/f'{prefix}_visibility.{ext}',dpi=200)
        plt.close(fig)
        for pf,bf,ylabel,suffix in [
            ('raw_events_s_present','raw_events_s_baseline','Whole-view raw events / second','raw_rate'),
            ('filtered_pixels_median_present','filtered_pixels_median_baseline','Median supported native pixels, whole view','filtered_support')]:
            fig,ax=plt.subplots(figsize=(8,4.8))
            for field,label,marker in [(pf,'Target-present interval','o'),(bf,'Preceding target-absent baseline','x')]:
                pts=[(r['range_m'],r[field]) for r in rs if r.get(field) is not None]
                if pts:ax.scatter([p[0] for p in pts],[p[1] for p in pts],label=label,marker=marker,s=50)
            ax.set(xlabel='Measured range (m)',ylabel=ylabel,title=title);ax.legend(fontsize=9);ax.grid(alpha=.2)
            fig.text(.5,.01,'Whole-view descriptive measurement, not a segmented drone or confidence score.',ha='center',fontsize=9)
            fig.tight_layout(rect=(0,.05,1,1))
            for ext in ('png','svg'):fig.savefig(out/f'{prefix}_{suffix}.{ext}',dpi=200)
            plt.close(fig)


def summarize():
    records=[]
    for path in sorted((ROOT/'captures').glob('*/trial.json')):
        try:records.append(analyze(path.parent))
        except Exception as exc:
            records.append(dict(run=path.parent.name,outcome='ANALYSIS_ERROR',error=str(exc)))
    out=ROOT/'captures/results';out.mkdir(parents=True,exist_ok=True)
    keys=sorted({k for r in records for k in r})
    with (out/'results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(records)
    write_json(out/'results.json',records)
    # Clear only this wrapper's earlier plot products, not data or source recordings.
    for pattern in ('lens_*_group_*.png','lens_*_group_*.svg'):
        for path in out.glob(pattern):path.unlink()
    plots(records,out)
    (out/'READ_ME.txt').write_text(
        'Only reviewed, verified LIVE runs appear in plots. All runs remain in the CSV.\n'
        'A single run is not a probability estimate. Focus/aperture/lux/settings are separated.\n'
        'Raw and filtered target visibility are operator judgments, not separate classifiers.\n'
        'Counts and rates are whole-view unless source ROI says otherwise. Do not call their ratio filter retention.\n'
        'Candidate means periodic evidence, not autonomous drone identity. Invalid data is never scored as a miss.\n')
    print('Results:',out)
    return out


def positive(s):
    v=float(s)
    if not math.isfinite(v) or v<=0:raise argparse.ArgumentTypeError('Must be a positive finite number')
    return v


def positive_int(s):
    try: value=int(s)
    except (ValueError,TypeError): raise argparse.ArgumentTypeError('Repeat must be a positive integer')
    if value < 1: raise argparse.ArgumentTypeError('Repeat must be a positive integer')
    return value


def record(args):
    if args.duration<20:raise ValueError('Use at least 20 seconds to leave room for baseline and target interval.')
    out=ROOT/'captures'/f'L{args.lens:g}_R{args.distance:g}_{args.aspect}_{args.profile}_REP{args.repeat}_{time.strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}'
    if shutil.disk_usage(ROOT).free < 8_000_000_000:raise ValueError('Less than 8 GB free. Make space before recording. More may be required at high event rates.')
    # Save provenance outside the run until app.py creates the new folder.
    source_bytes={n:(ROOT/n).read_bytes() for n in SOURCE_FILES}
    hashes={n:hashlib.sha256(body).hexdigest() for n,body in source_bytes.items()}
    meta=dict(activity_preset=getattr(args,'activity_preset','sensitive'),period_input=getattr(args,'period_input','native'),
              activity_settings_hash=hashes['activity_presets.json'],lens_mm=args.lens,range_m=args.distance,focus_m=args.focus_m,
              f_number=args.f_number,lux=args.lux,target=args.target,duration_requested_s=args.duration,
              aspect=args.aspect,profile=args.profile,repeat=args.repeat,operator_notes=args.notes,
              settings_hash=hashes['settings.json'],source_sha256=hashes,
              paired_recording=True,created_unix=time.time(),basis='Archived v0.3 plus guarded activity-first patch; original rotor thresholds retained',
              focus_policy='Operator sets focus once per lens. Software does not focus the lens.',
              identity='Known test target. Independent activity, rotor-evidence and possible-drone flags are unverified.')
    captures=ROOT/'captures';captures.mkdir(exist_ok=True)
    write_json(captures/(out.name+'_planned.json'),meta)
    print(f'Lens {args.lens:g} mm | measured range {args.distance:g} m | declared fixed focus {args.focus_m:g} m',flush=True)
    print(f'Aspect: {args.aspect} | profile: {args.profile} | repeat: {args.repeat}',flush=True)
    print('Target ABSENT for at least 6 seconds after live imagery begins. Press 1 at target entry; 2 at exit.',flush=True)
    print('Keep target in view about 10 seconds. S = native photo. Q = stop early.',flush=True)
    cmd=[sys.executable,str(ROOT/'app.py'),'record','--duration',str(args.duration),'--photos-every','5',
         '--activity-preset',getattr(args,'activity_preset','sensitive'),'--period-input',getattr(args,'period_input','native'),
         '--config',str(ROOT/'settings.json'),'--run-dir',str(out),'--notes',json.dumps(meta)]
    try:rc=subprocess.call(cmd,cwd=ROOT)
    except KeyboardInterrupt:rc=130
    if out.exists():
        write_json(out/'trial.json',meta)
        (captures/'LAST_TRIAL.txt').write_text(str(out)+'\n')
        # Keep actual source copy; current folder may change after the experiment.
        archived=out/'code_used';archived.mkdir(exist_ok=True)
        for n,body in source_bytes.items():(archived/n).write_bytes(body)
        if (out/'summary.json').exists():review(out);summarize()
        else:print('Run did not finish. Preserve it as incomplete:',out)
    return rc


def bundle(run: Path):
    """Small evidence package only. Original events/videos stay untouched."""
    dest=Path.home()/'Downloads';dest.mkdir(exist_ok=True)
    target=dest/f'EBS_logs_{run.name}_{uuid.uuid4().hex[:6]}.zip'
    candidates=[]
    for p in run.iterdir():
        if p.is_file() and p.suffix.lower() in ('.json','.jsonl','.csv','.txt') and p.stat().st_size<30_000_000:
            candidates.append(p)
    candidates+=list((run/'code_used').glob('*')) if (run/'code_used').exists() else []
    for directory in sorted((run/'photos').glob('*'))[:2]:
        if directory.is_dir():candidates.extend(p for p in directory.iterdir() if p.is_file() and p.stat().st_size<30_000_000)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in candidates:z.write(p,run.name+'/'+p.relative_to(run).as_posix())
        z.writestr('CONTENTS.txt','Small logs and first two native photo sets only. No event/video file. Current source is not substituted for historic code. Review before sharing.\n')
    print('Small evidence ZIP:',target)
    print('Original events.evs and raw/dashboard video remain in:',run)


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    commands={'live','demo','check','summary','review','replay','bundle','record','test','compare'}
    if argv and argv[0] not in commands and not argv[0].startswith('-'):argv.insert(0,'record')
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command')
    for n in ['live','demo','check','summary','test']:
        cp=sub.add_parser(n)
        if n in ('live','demo'):
            cp.add_argument('--activity-preset',choices=['baseline','sensitive'],default='sensitive')
            cp.add_argument('--period-input',choices=['native','neighbor'],default='native')
    for n in ['review','bundle']:
        c=sub.add_parser(n);c.add_argument('run',nargs='?',default='latest')
    c=sub.add_parser('compare');c.add_argument('path');c.add_argument('--period-input',choices=['native','neighbor'],default='native');c.add_argument('--annotations')
    c=sub.add_parser('replay');c.add_argument('path')
    c.add_argument('--activity-preset',choices=['baseline','sensitive'],default='sensitive')
    c.add_argument('--period-input',choices=['native','neighbor'],default='native')
    c=sub.add_parser('record');c.add_argument('lens',type=positive);c.add_argument('distance',type=positive)
    c.add_argument('--focus-m',type=positive,default=20.0);c.add_argument('--duration',type=positive,default=30.)
    c.add_argument('--f-number',type=positive);c.add_argument('--lux',type=positive);c.add_argument('--target',default='known test drone')
    c.add_argument('--aspect',choices=['front','oblique','side','rear'],default='front',help='Operator-declared aircraft orientation; not estimated by the camera')
    c.add_argument('--profile',choices=['hover','crossing'],default='hover')
    c.add_argument('--repeat',type=positive_int,default=1)
    c.add_argument('--notes',default='')
    c.add_argument('--activity-preset',choices=['baseline','sensitive'],default='sensitive')
    c.add_argument('--period-input',choices=['native','neighbor'],default='native')
    a=p.parse_args(argv)
    if a.command=='compare':
        cmd=[sys.executable,str(ROOT/'compare_activity.py'),a.path,'--period-input',a.period_input]
        if a.annotations:cmd+=['--annotations',a.annotations]
        return subprocess.call(cmd,cwd=ROOT)
    if a.command=='record':return record(a)
    if a.command=='summary':summarize();return 0
    if a.command=='review':review(resolve_run(a.run));summarize();return 0
    if a.command=='bundle':bundle(resolve_run(a.run));return 0
    if a.command=='check':cmd=['doctor.py','--camera','--seconds','5']
    elif a.command=='test':cmd=['-m','unittest','discover','-s','tests','-v']
    elif a.command=='demo':cmd=['app.py','demo','--duration','4']
    elif a.command=='replay':
        path=Path(a.path).expanduser()
        if path.is_dir():path=path/'events.evs'
        cmd=['app.py','replay',str(path.resolve())]
    else:cmd=['app.py','live']
    if cmd and cmd[0]=='app.py':
        cmd+=['--activity-preset',getattr(a,'activity_preset','sensitive'),'--period-input',getattr(a,'period_input','native')]
    return subprocess.call([sys.executable,*cmd],cwd=ROOT)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError) as exc:raise SystemExit(f'Experiment stopped: {exc}')
