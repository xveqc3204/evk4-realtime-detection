"""Reproducible synthetic characterization. Never a real-drone certification.

Deterministic assertions are separated from envelope measurements and known
lookalikes. Raster tests generate events from rotating silhouettes rather than
calling the period filter's inverse. All metrics use known synthetic truth.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
import csv
import importlib.metadata
import json
from pathlib import Path
import platform
import time
import numpy as np
from rotor import EVENT_DTYPE, Settings, PeriodFilter, PatchTracker, group_pixels
from synthetic import QuadSpec, render_events
from event_io import periodic_events


def evaluate(ev,width,height,duration_s,cfg=None,truth=None,start=.06,stop=.62):
    cfg=cfg or Settings();p=PeriodFilter(cfg,width,height);p.compile();tracker=PatchTracker(cfg)
    n_eval=n_active=n_positive=tail_positive=0;first=None;peak=0;freq_errors=[];precisions=[]
    active_ids=set();post=False;max_regions=0;records=[];kernel=[];groups=[]
    idx=0;beg=time.perf_counter()
    for end in range(int(cfg.update_ms*1000),int(duration_s*1e6)+1,int(cfg.update_ms*1000)):
        j=int(np.searchsorted(ev['t'],end,'left'));a=time.perf_counter();p.push(ev[idx:j]);idx=j
        kernel.append((time.perf_counter()-a)*1000);a=time.perf_counter()
        raw,freq=p.maps(end);r,status,_,m=group_pixels(freq,cfg,p.roi,True)
        if status=='RUN':tt=tracker.update(r,end)
        else:tracker.reset();tt=[]
        flag=any(t['confirmed'] and t['state']!='COASTING' for t in tt)
        groups.append((time.perf_counter()-a)*1000)
        n_eval+=1;n_positive+=int(flag);peak=max(peak,int(np.count_nonzero(m)));max_regions=max(max_regions,len(r))
        ts=end/1e6
        if flag and first is None:first=ts
        # Exclude setup and expiry from the active-window occupancy metric.
        if start+.15<=ts<stop:
            n_active+=1
            if flag:active_ids.update(t['id'] for t in tt if t['confirmed'] and t['state']!='COASTING')
            if truth is not None and truth.visible(ts):
                centers=truth.centers(ts)
                for region in r:
                    k=int(np.argmin(np.linalg.norm(centers-np.array(region['center']),axis=1)))
                    expected=truth.hz[k]+truth.ramp_hz_s*(ts-truth.start_s)
                    freq_errors.append(abs(region['hz']-expected)/expected)
                yy,xx=np.nonzero(m)
                if len(xx):
                    d2=np.min(np.array([(xx+.5-x)**2+((yy+.5-y)/max(truth.vertical_scale,.03))**2 for x,y in centers]),axis=0)
                    precisions.append(float(np.mean(d2<=(truth.radius_px+2.0)**2)))
        if ts>=stop+.12:tail_positive+=int(flag)
        records.append(dict(t_s=ts,flag=flag,regions=len(r),supported=int(np.count_nonzero(m)),status=status))
    active=[r for r in records if start+.15<=r['t_s']<stop]
    elapsed=time.perf_counter()-beg
    return dict(events=len(ev),duration_s=duration_s,evaluations=n_eval,
        flag_windows=n_positive,active_flag_fraction=sum(r['flag'] for r in active)/max(1,len(active)),
        first_flag_delay_ms=None if first is None else round((first-start)*1000,3),
        flags_after_quiet_tail=tail_positive,max_supported_pixels=peak,max_regions=max_regions,
        fresh_confirmed_patch_ids=len(active_ids),
        median_frequency_relative_error=None if not freq_errors else float(np.median(freq_errors)),
        median_spatial_support_precision=None if not precisions else float(np.median(precisions)),
        kernel_p95_ms=float(np.percentile(kernel,95)),map_group_p95_ms=float(np.percentile(groups,95)),
        wall_processing_s=elapsed,processing_mev_s=len(ev)/max(elapsed,1e-9)/1e6,
        observed_statuses=sorted(set(r['status'] for r in records)))


def noise(seed,n=25000,localized=True):
    rng=np.random.default_rng(seed);e=np.zeros(n,EVENT_DTYPE)
    e['t']=rng.integers(0,800000,n)
    e['x']=rng.integers(80,96,n) if localized else rng.integers(0,192,n)
    e['y']=rng.integers(60,76,n) if localized else rng.integers(0,144,n)
    e['on']=rng.integers(0,2,n).astype(bool);e.sort(order='t',kind='stable')
    return e


def cases(full):
    # Assert only the behaviors the algorithm is designed to support.
    for hz in ([120,240,600] if not full else [90,120,180,240,360,600,900,1100]):
        for seed in ([1] if not full else [1,2,3]):
            yield (f'period_{hz}_seed{seed}','assert_positive','analytic',dict(hz=hz,seed=seed))
    for hz in ([40,1800] if not full else [20,40,60,1500,1800,2400]):
        yield(f'outside_band_{hz}','assert_negative','analytic',dict(hz=hz,seed=5))
    for seed in range(1,4 if not full else 13):
        yield(f'noise_seed{seed}','assert_negative','noise',dict(seed=seed))
    yield('hot_pixel_one_polarity','assert_negative','hot',{})
    yield('single_periodic_pixel','assert_negative','single',{})
    yield('global_periodic_light','assert_global_rejection','global',{})
    yield('local_blink_lookalike','known_confounder','analytic',dict(hz=240,seed=8))
    yield('notched_local_blink','assert_negative','notch',dict(hz=240,seed=8))
    yield('four_rotors_stationary','assert_quad','raster',{})
    if not full:return
    for seed in [2,3,4]:
        yield(f'quad_seed{seed}','assert_quad','raster',dict(seed=seed))
    for speed in [10,40,100,250,600]:
        yield(f'quad_speed_{speed}','characterize','raster',dict(vx_px_s=speed,center_x=60))
    for radius in [0.8,1.5,2.5,4,6,12]:
        yield(f'quad_radius_{radius}','characterize','raster',dict(radius_px=radius,blade_width_px=max(.6,min(1.4,radius/3))))
    for keep in [.9,.7,.5,.25,.1]:
        yield(f'quad_event_retention_{keep}','characterize','raster',dict(keep_probability=keep))
    for contrast in [.7,.35,.2,.1]:
        yield(f'quad_log_contrast_{contrast}','characterize','raster',dict(contrast=contrast))
    for jitter in [10,40,120]:
        yield(f'quad_timestamp_jitter_{jitter}us','characterize','raster',dict(timestamp_jitter_us=jitter))
    for noise_rate in [20000,100000,400000]:
        yield(f'quad_noise_rate_{noise_rate}','characterize','raster',dict(noise_events_s=noise_rate))
    for squish in [.5,.2,.07]:
        yield(f'quad_projection_{squish}','characterize','raster',dict(vertical_scale=squish))
    for ramp in [100,400]:
        yield(f'quad_frequency_ramp_{ramp}','characterize','raster',dict(ramp_hz_s=ramp))
    yield('quad_occlusion_180ms','characterize','raster',dict(occlusion=(.30,.48)))
    yield('quad_two_rotors_hidden','characterize','raster',dict(disabled_rotors=(1,3)))
    yield('quad_three_rotors_hidden','characterize','raster',dict(disabled_rotors=(1,2,3)))
    yield('quad_yaw','characterize','raster',dict(yaw_rate_rad_s=2.0))
    yield('single_rotor_fan_lookalike','known_confounder','raster',dict(disabled_rotors=(1,2,3)))


def run_case(name,expectation,kind,params):
    cfg=Settings();truth=None
    if kind=='raster':
        truth=replace(QuadSpec(),**params);ev=render_events(truth)
    elif kind=='noise':ev=noise(params['seed'])
    elif kind=='hot':
        ev=np.zeros(100000,EVENT_DTYPE);ev['t']=np.arange(len(ev))*7;ev['x']=90;ev['y']=70;ev['on']=True
    else:
        points=[(x,y) for y in range(60,65) for x in range(80,85)]
        if kind=='single':points=[(80,60)]
        if kind=='global':points=[(x,y) for y in range(4,144,8) for x in range(4,192,8)]
        ev=periodic_events(hz=params.get('hz',240),seed=params.get('seed',1),start_us=60000,duration_s=.56,points=points,burst=2)
        if kind=='notch':cfg.notches_hz=(240,)
    result=evaluate(ev,192,144,.8,cfg,truth)
    if expectation=='assert_positive':ok=result['active_flag_fraction']>=.8 and result['flags_after_quiet_tail']==0
    elif expectation=='assert_quad':ok=(result['active_flag_fraction']>=.8 and result['max_regions']>=4 and result['flags_after_quiet_tail']==0 and result['median_frequency_relative_error']<.05 and result['median_spatial_support_precision']>.9)
    elif expectation=='assert_negative':ok=result['flag_windows']==0
    elif expectation=='assert_global_rejection':ok=(result['flag_windows']==0 and 'GLOBAL_PERIODIC_ACTIVITY' in result['observed_statuses'])
    else:ok=None
    status=('PASS' if ok else 'FAIL') if ok is not None else ('KNOWN_CONFOUNDER' if expectation=='known_confounder' else 'MEASURED')
    return dict(name=name,expectation=expectation,result=status,parameters=params,
                model='sampled log-contrast raster' if kind=='raster' else 'analytic/noise events',**result)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--full',action='store_true')
    p.add_argument('--part',choices=['all','signals','raster'],default='all')
    p.add_argument('--out',default='validation/stress')
    p.add_argument('--limit',type=int,default=0,help='Maximum new cases in this invocation; combine with --resume')
    p.add_argument('--resume',action='store_true',help='Skip cases already in results.json; do not use after source changes')
    a=p.parse_args(argv);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    path=out/'results.json';rows=json.loads(path.read_text()) if a.resume and path.exists() else []
    names={r['name'] for r in rows};added=0
    for name,expectation,kind,params in cases(a.full):
        if a.part=='signals' and kind=='raster':continue
        if a.part=='raster' and kind!='raster':continue
        if name in names:continue
        if a.limit and added>=a.limit:break
        added+=1
        t=time.perf_counter()
        r=run_case(name,expectation,kind,params);r['case_wall_s']=round(time.perf_counter()-t,3)
        rows.append(r);path.write_text(json.dumps(rows,indent=2))
        print(f"{r['result']:18s} {name:34s} active={r['active_flag_fraction']:.2f} regions={r['max_regions']:2d} pixels={r['max_supported_pixels']:4d}",flush=True)
    fields=[k for k in rows[0] if k!='parameters'] if rows else []
    with (out/'results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    meta=dict(python=platform.python_version(),platform=platform.platform(),tested_mac=False,tested_camera=False,
        versions={k:importlib.metadata.version(k) for k in ('numpy','numba','opencv-python','matplotlib')},
        asserted=sum(r['result'] in ('PASS','FAIL') for r in rows),passed=sum(r['result']=='PASS' for r in rows),
        failed=sum(r['result']=='FAIL' for r in rows),measured=sum(r['result']=='MEASURED' for r in rows),
        known_confounders=sum(r['result']=='KNOWN_CONFOUNDER' for r in rows),
        caveat='Synthetic stress observations are not real-drone accuracy, range, lux, power, or end-to-end latency.')
    (out/'environment.json').write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta,indent=2));return int(meta['failed']>0)

if __name__=='__main__':raise SystemExit(main())
