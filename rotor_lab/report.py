"""Presentation plots and CSVs from run diagnostics. Never invent depth or labels.

Usage: bash run.sh report captures/<run>
Charts are generated after a run, not required by the live detector.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import numpy as np


def load_rows(path):
    rows=[];bad=0
    if not path.exists():return rows,bad
    with path.open() as f:
        for line in f:
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:bad+=1
    return rows,bad


def write_csv(path,rows,fields):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


def forecast(points,horizon_s=.10):
    """Simple least-squares x(t),y(t) projection in SENSOR PIXELS, not world XYZ."""
    p=np.array(points,dtype=float) # time_s, x, y
    if len(p)<5:return None
    p=p[p[:,0]>=p[-1,0]-.30]
    if len(p)<5 or p[-1,0]-p[0,0]<.08:return None
    t=p[:,0]-p[-1,0]
    X=np.column_stack([t,np.ones_like(t)])
    coef=np.linalg.lstsq(X,p[:,1:3],rcond=None)[0]
    resid=float(np.sqrt(np.mean(np.sum((X@coef-p[:,1:3])**2,axis=1))))
    if not np.isfinite(coef).all() or resid>25:return None
    dt=np.linspace(0,horizon_s,6)
    # Anchor to the last measurement; slope is estimated, not a measured velocity.
    xy=p[-1,1:3]+dt[:,None]*coef[0]
    return dict(t=(p[-1,0]+dt).tolist(),x=xy[:,0].tolist(),y=xy[:,1].tolist(),
                velocity_px_s=coef[0].tolist(),fit_rmse_px=resid,
                method='Last 0.30 s linear image-plane fit, anchored to last measurement',
                meaning='Illustrative model forecast, unvalidated; third plot axis is TIME, not depth')


def export_report(run_dir,prediction_ms=100):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    path=Path(run_dir).expanduser().resolve()
    session=json.loads((path/'session.json').read_text())
    rows,bad=load_rows(path/'telemetry.jsonl')
    decisions=[r for r in rows if r.get('type')=='decision']
    summary=json.loads((path/'summary.json').read_text()) if (path/'summary.json').exists() else {'status':'INCOMPLETE'}
    source=session.get('source_info',{}).get('source','unknown')
    label='SYNTHETIC SOFTWARE TEST' if source=='synthetic' else ('RECORDED REPLAY' if source=='replay' else 'EVK4 EXPERIMENT')
    W=session.get('source_info',{}).get('width',1280);H=session.get('source_info',{}).get('height',720)
    settings=session.get('settings',{});lo=settings.get('min_hz',80);hi=settings.get('max_hz',1200)
    gap_limit=settings.get('clear_ms',120)/1000
    out=path/'report';out.mkdir(exist_ok=True)
    t0=min((r['t_us'] for r in decisions),default=0)/1e6
    tab=[];track_rows=[];hist_rows=[];by_id={}
    for r in decisions:
        t=r['t_us']/1e6-t0
        tab.append(dict(time_s=t,sensor_t_us=r['t_us'],status=r['status'],rotor_candidate=int(r.get('rotor_candidate',False)),
                        periodic_pixels=r.get('periodic_pixels',0),cycle_only_pixels=r.get('stable_pixels',0),
                        driver_delay_ms=r.get('delay_ms'),backlog=r.get('backlog',0),map_group_ms=r.get('map_and_group_ms',0)))
        for tr in r.get('tracks',[]):
            trrow=dict(time_s=t,sensor_t_us=r['t_us'],patch_id=tr['id'],x_px=tr['center'][0],y_px=tr['center'][1],
                       optical_hz=tr['hz'],supported_pixels=tr['pixels'],confirmed=int(tr['confirmed']),state=tr['state'],
                       x0=tr['bbox'][0],y0=tr['bbox'][1],x1=tr['bbox'][2],y1=tr['bbox'][3])
            track_rows.append(trrow)
            if tr['confirmed'] and tr['state']!='COASTING':
                by_id.setdefault(tr['id'],[]).append([t,*tr['center'],tr['hz']])
        if 'frequency_histogram' in r:
            hh=r['frequency_histogram'];ee=np.linspace(lo,hi,len(hh)+1)
            for j,v in enumerate(hh):hist_rows.append(dict(time_s=t,low_hz=ee[j],high_hz=ee[j+1],pixel_observations=v))
    write_csv(out/'decisions.csv',tab,['time_s','sensor_t_us','status','rotor_candidate','periodic_pixels','cycle_only_pixels','driver_delay_ms','backlog','map_group_ms'])
    write_csv(out/'tracks.csv',track_rows,['time_s','sensor_t_us','patch_id','x_px','y_px','optical_hz','supported_pixels','confirmed','state','x0','y0','x1','y1'])
    write_csv(out/'frequency_distribution.csv',hist_rows,['time_s','low_hz','high_hz','pixel_observations'])
    tracks=sorted(by_id,key=lambda k:len(by_id[k]),reverse=True)[:12]
    traces={k:np.asarray(by_id[k]) for k in tracks}
    files=[]
    def new(title,xlabel,ylabel,three=False):
        fig=plt.figure(figsize=(9.0,5.5),layout='constrained')
        ax=fig.add_subplot(111,projection='3d' if three else None)
        ax.set_title(f'{title}\n{label}',fontsize=13,pad=12)
        ax.set_xlabel(xlabel);ax.set_ylabel(ylabel)
        if not three:
            ax.spines[['top','right']].set_visible(False)
            ax.grid(True,alpha=.15)
        fig.text(.5,.004,'Periodic-patch evidence, not verified drone identity. Figures use sensor time.',ha='center',fontsize=8)
        return fig,ax
    def save(fig,name):
        for ext in ('png','svg'):
            fig.savefig(out/f'{name}.{ext}',dpi=180)
        plt.close(fig);files.append(name+'.png')
    def empty(ax,msg):ax.text(.5,.5,msg,transform=ax.transAxes,ha='center',va='center',fontsize=12)
    def pieces(p):
        cut=np.r_[0,np.flatnonzero(np.diff(p[:,0])>gap_limit)+1,len(p)]
        return [p[a:b] for a,b in zip(cut[:-1],cut[1:])]
    fig,ax=new('2D measured periodic-patch paths','x (sensor pixels)','y (sensor pixels)')
    for k,p in traces.items():
        for i,part in enumerate(pieces(p)):ax.plot(part[:,1],part[:,2],'-',linewidth=1.4,label=f'P{k}' if i==0 else None)
        ax.annotate(f'P{k}',p[-1,1:3],fontsize=8)
    ax.set_xlim(0,W);ax.set_ylim(H,0);ax.set_aspect('equal')
    if not traces:empty(ax,'No fresh confirmed periodic patches in this run.')
    else:ax.legend(loc='best',fontsize=8,ncol=3)
    save(fig,'tracks_2d')
    predictions={}
    fig,ax=new('3D space-time paths (third axis = time, NOT depth)','x (sensor pixels)','y (sensor pixels)',True)
    ax.set_zlabel('Time since first decision (s)')
    for k,p in traces.items():
        for i,part in enumerate(pieces(p)):ax.plot(part[:,1],part[:,2],part[:,0],linewidth=1.1,label=f'P{k}' if i==0 else None)
        last=pieces(p)[-1]
        pred=forecast(last[:,:3],prediction_ms/1000) if prediction_ms>0 else None
        if pred is not None:
            pred['patch_id']=k;predictions[str(k)]=pred
            ax.plot(pred['x'],pred['y'],pred['t'],'--',linewidth=1.6,label=f'P{k} model +{prediction_ms:g} ms')
    ax.set_xlim(0,W);ax.set_ylim(H,0)
    if not traces:ax.text2D(.12,.55,'No measured path. No forecast generated.',transform=ax.transAxes)
    if traces:ax.legend(fontsize=7,loc='upper left')
    save(fig,'tracks_3d_time')
    (out/'image_plane_forecasts.json').write_text(json.dumps(predictions,indent=2))
    fig,ax=new('Optical frequency of fresh confirmed patches','Time since first decision (s)','Estimated optical repetition (Hz)')
    for k,p in traces.items():
        for i,part in enumerate(pieces(p)):ax.plot(part[:,0],part[:,3],'.-',markersize=2,label=f'P{k}' if i==0 else None)
    ax.set_ylim(lo,hi)
    if not traces:empty(ax,'No fresh confirmed frequency track.')
    else:ax.legend(fontsize=8,ncol=3)
    save(fig,'frequency_over_time')
    fig,ax=new('Frequency distribution of accepted pixels','Estimated optical repetition (Hz)','Pixel observations across decisions')
    if hist_rows:
        hist=np.array([r['frequency_histogram'] for r in decisions if 'frequency_histogram' in r]).sum(axis=0)
        edges=np.linspace(lo,hi,len(hist)+1)
        ax.bar((edges[:-1]+edges[1:])/2,hist,width=np.diff(edges)*.9)
    else:empty(ax,'No frequency histogram data was saved.')
    ax.set_xlim(lo,hi)
    save(fig,'frequency_distribution')
    fig,ax=new('Supported pixels and candidate intervals','Time since first decision (s)','Supported native sensor pixels')
    if tab:
        t=np.array([r['time_s'] for r in tab]);v=np.array([r['periodic_pixels'] for r in tab]);flag=np.array([r['rotor_candidate'] for r in tab],bool)
        ax.plot(t,v,linewidth=1,label='Periodic pixels after spatial test')
        ax.fill_between(t,0,v,where=flag,alpha=.2,label='Candidate asserted')
        ax.legend(fontsize=9)
    else:empty(ax,'No decision data.')
    save(fig,'activity_timeline')
    fig,ax=new('Host processing diagnostics (not total detection latency)','Time since first decision (s)','Milliseconds')
    if tab:
        t=[r['time_s'] for r in tab]
        ax.plot(t,[r['map_group_ms'] for r in tab],label='Map + grouping')
        d=np.array([np.nan if r['driver_delay_ms'] is None else r['driver_delay_ms'] for r in tab],float)
        if np.isfinite(d).any():ax.plot(t,d,label='Driver receive-to-consume')
        ax.legend(fontsize=9)
    else:empty(ax,'No timing data.')
    save(fig,'processing_diagnostics')
    # Still-image frequency diagrams use exactly the saved snapshot pixels.
    for photo in sorted((path/'photos').glob('*/pixel_data.npz')) if (path/'photos').exists() else []:
        with np.load(photo) as data:freq=data['frequency_hz'];v=freq[freq>0]
        fig,ax=new('Snapshot optical-frequency distribution','Optical repetition (Hz)','Supported pixels')
        if len(v):ax.hist(v,bins=np.linspace(lo,hi,65))
        else:empty(ax,'No supported periodic pixels in this snapshot.')
        fig.savefig(photo.parent/'frequency_diagram.png',dpi=180);plt.close(fig)
    no_loss=summary.get('no_observed_recording_loss')
    media=json.loads((path/'media.json').read_text()) if (path/'media.json').exists() else {}
    note=f'''# Experiment report\n\nSource: **{label}**. Status: **{summary.get('status')}**.\n\nNotes: {session.get('notes','')}\n\n{len(tab)} decisions; {len(by_id)} fresh confirmed periodic-patch IDs. A patch is not a counted drone or a motor identity. Plots show at most the 12 longest tracks.\n\nObserved input loss: **{summary.get('observed_input_loss','unknown')}**. Event recording requested: **{summary.get('recording_requested',False)}**. No observed recording loss: **{no_loss}**. Missing/partial JSONL lines: **{bad}**. Video skipped GUI frames: **{media.get('dropped_gui_frames',0)}**.\n\n## What the figures mean\n\n- `tracks_2d`: fresh measured image-plane patch centers, no coasting points.\n- `tracks_3d_time`: the same measured x/y centers with TIME as the third axis. Dashed extensions, when present, are short linear model forecasts. No depth, range, physical drone geometry, or validated 3D flight path is estimated.\n- `frequency_over_time`: estimated optical frequency, not guaranteed blade-pass fundamental or rotor RPM.\n- `frequency_distribution`: summed pixel observations; repeated observations of the same pixel are counted repeatedly. This is not an FFT amplitude spectrum.\n- `activity_timeline`: frequency-supported pixel evidence and candidate intervals.\n- `processing_diagnostics`: partial host timing only, not sensor-to-alert latency.\n\nPrediction horizon: {prediction_ms:g} ms. Predictions require at least 5 recent fresh observations spanning 80 ms. They are illustrative image-plane extrapolations, not ground truth.\n\nNo precision, recall, detection range, or false-alarm rate is calculated without labeled target-present and target-absent observations. A fan or LED can pass the same optical periodicity rule.\n\nCSV files and numerical forecasts are included for inspection. All images are separate PNGs with vector SVG copies.\n'''
    (out/'REPORT.md').write_text(note)
    (out/'manifest.json').write_text(json.dumps(dict(figures=files,source=source,created_from=str(path),
        third_axis='time_seconds_not_depth',prediction_ms=prediction_ms,unparsed_lines=bad,
        track_ids_plotted=tracks),indent=2))
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_dir');p.add_argument('--prediction-ms',type=float,default=100)
    a=p.parse_args()
    if not math.isfinite(a.prediction_ms) or not 0<=a.prediction_ms<=200:p.error('Prediction must be between 0 and 200 ms')
    try:print(export_report(a.run_dir,a.prediction_ms))
    except Exception as exc:raise SystemExit(f'Report failed: {exc}')

if __name__=='__main__':main()
