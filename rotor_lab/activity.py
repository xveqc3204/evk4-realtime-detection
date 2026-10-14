"""Small raw-activity branch and explainable evidence flags.

Raw activity reads the full-resolution last-event timestamps already retained
BEFORE periodicity filtering. It never depends on a frequency estimate or on
GUI colors. Counts are DISTINCT recently active pixels, not total events.
All spatial coordinates are native image pixels; all t_us values are sensor us.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from collections import deque
from pathlib import Path
import json
import math

import cv2
import numpy as np
from numba import njit

FLAG_NAMES = ('ACTIVITY', 'ROTOR_EVIDENCE', 'DRONE_CANDIDATE')


@dataclass
class ActivitySettings:
    window_ms: float = 20.0
    cell_px: int = 8
    warmup_ms: float = 1000.0
    background_tau_ms: float = 5000.0
    variance_floor: float = 0.25
    z_threshold: float = 3.0
    min_pixels: int = 4
    confirm_hits: int = 3
    history_windows: int = 4
    clear_ms: float = 120.0
    association_px: float = 40.0
    max_active_fraction: float = 0.25
    max_regions: int = 32
    candidate_age_ms: float = 200.0
    candidate_motion_px: float = 8.0
    rotor_match_margin_px: int = 8
    neighbor_us: int = 1000

    def validate(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f'{f.name} must be a finite number')
        for k in ('cell_px','min_pixels','confirm_hits','history_windows','max_regions','rotor_match_margin_px','neighbor_us'):
            if not isinstance(getattr(self,k), int): raise ValueError(f'{k} must be an integer')
        if not 1 <= self.cell_px <= 64 or self.min_pixels < 2:
            raise ValueError('Require cell_px 1..64 and at least two distinct pixels')
        if not 2 <= self.confirm_hits <= self.history_windows <= 20:
            raise ValueError('Require 2 <= confirm_hits <= history_windows <= 20')
        if not 5 <= self.window_ms <= 200 or self.warmup_ms < self.window_ms:
            raise ValueError('Invalid activity window or warmup')
        if self.background_tau_ms < self.window_ms or self.variance_floor <= 0 or self.z_threshold <= 0:
            raise ValueError('Invalid background/threshold values')
        if self.clear_ms < self.window_ms or self.association_px <= 0 or not 0 < self.max_active_fraction <= 1:
            raise ValueError('Invalid association, retention or global limit')
        if not 1 <= self.max_regions <= 128 or self.candidate_age_ms < self.window_ms or self.candidate_motion_px <= 0:
            raise ValueError('Invalid candidate settings')
        if self.rotor_match_margin_px < 0 or not 1 <= self.neighbor_us <= 100000:
            raise ValueError('Invalid match margin or neighbor time')
        return self

    def to_dict(self): return asdict(self)


def load_activity_settings(path, preset='sensitive'):
    data = json.loads(Path(path).read_text())
    if preset not in ('baseline','sensitive'): raise ValueError('Unknown activity preset')
    values = dict(data['common']); values.update(data[preset])
    unknown = set(values)-{f.name for f in fields(ActivitySettings)}
    if unknown: raise ValueError(f'Unknown activity keys: {sorted(unknown)}')
    return ActivitySettings(**values).validate()


@njit(cache=True, nogil=True)
def _raw_grid(last_event, width, height, roi, now_us, window_us, cell):
    gh, gw = (height+cell-1)//cell, (width+cell-1)//cell
    counts = np.zeros((gh,gw), np.int32)
    sx = np.zeros((gh,gw), np.float64); sy = np.zeros((gh,gw), np.float64)
    x0,y0,x1,y1 = roi
    total_raw = 0
    for y in range(y0,y1):
        for x in range(x0,x1):
            t = last_event[y*width+x]
            # Half-open window prevents counting an unchanged edge twice at
            # successive evaluations exactly window_us apart.
            if t >= 0 and 0 <= now_us-t < window_us:
                total_raw += 1
                # Isolated native pixels are not object support, even if they
                # land in adjacent coarse grid cells. No periodicity is needed.
                neighbor = False
                for ny in range(max(y0,y-1),min(y1,y+2)):
                    for nx in range(max(x0,x-1),min(x1,x+2)):
                        if nx == x and ny == y: continue
                        nt = last_event[ny*width+nx]
                        if nt >= 0 and 0 <= now_us-nt < window_us:
                            neighbor = True; break
                    if neighbor: break
                if not neighbor: continue
                gy,gx = y//cell,x//cell
                counts[gy,gx] += 1; sx[gy,gx] += x; sy[gy,gx] += y
    return counts,sx,sy,total_raw


@njit(cache=True, nogil=True)
def _neighbor_mask(events, surface, width, height, max_dt_us):
    """Experimental causal 8-neighbor support. Current pixel cannot support itself."""
    keep = np.zeros(len(events), np.bool_)
    for i in range(len(events)):
        e = events[i]; x,y,t = int(e['x']),int(e['y']),np.int64(e['t'])
        if x < 0 or y < 0 or x >= width or y >= height: continue
        good = False
        for yy in range(max(0,y-1),min(height,y+2)):
            for xx in range(max(0,x-1),min(width,x+2)):
                if xx == x and yy == y: continue
                last = surface[yy*width+xx]
                if last >= 0 and 0 <= t-last <= max_dt_us:
                    good = True; break
            if good: break
        keep[i] = good
        surface[y*width+x] = t
    return keep


class NeighborSupport:
    def __init__(self,width,height,dt_us=1000):
        self.width,self.height,self.dt_us = width,height,dt_us
        self.surface = np.full(width*height,-1,np.int64)
    def reset(self): self.surface.fill(-1)
    def mask(self,events):
        ev = events.view(); ev.flags.writeable = False
        return _neighbor_mask(ev,self.surface,self.width,self.height,self.dt_us)
    def compile(self,dtype):
        self.mask(np.zeros(0,dtype=dtype)); self.mask(np.zeros(4,dtype=dtype)[::2]); self.reset()


class RawActivity:
    """Adaptive count-of-active-pixels grid, connected clusters, nearest tracks.

    This is an added raw cue reference, not a claim of recovered drone identity.
    Warm up without target. Weak target settings are a test preset, not validated.
    """
    def __init__(self,cfg,width,height):
        self.cfg=cfg.validate(); self.width=width; self.height=height
        shape=((height+cfg.cell_px-1)//cfg.cell_px,(width+cfg.cell_px-1)//cfg.cell_px)
        self.mean=np.zeros(shape); self.var=np.full(shape,cfg.variance_floor)
        self.m2=np.zeros(shape); self.n=0; self.first_t=None; self.last_t=None
        self.tracks=[]; self.next_id=1; self.ready=False
    def compile(self):
        _raw_grid(np.full(self.width*self.height,-1,np.int64),self.width,self.height,
                  (0,0,self.width,self.height),0,int(self.cfg.window_ms*1000),self.cfg.cell_px)
        cv2.connectedComponentsWithStats(np.zeros(self.mean.shape,np.uint8), connectivity=8)
    def reset(self,background=False):
        self.tracks=[]; self.last_t=None
        if background or not self.ready:
            self.mean.fill(0); self.var.fill(self.cfg.variance_floor); self.m2.fill(0)
            self.n=0; self.first_t=None; self.ready=False
    def update(self,last_event,t_us,roi):
        c=self.cfg; t_us=int(t_us)
        if self.last_t is not None and t_us<=self.last_t:
            if t_us<self.last_t: self.reset(True)
            else: return {'status':'NO_NEW_SENSOR_TIME','tracks':[],'raw_pixels':0,'max_z':0.,'active_fraction':0.}
        dt=c.window_ms if self.last_t is None else (t_us-self.last_t)/1000
        if dt>c.clear_ms: self.tracks=[]
        self.last_t=t_us
        counts,sx,sy,total_raw=_raw_grid(last_event,self.width,self.height,tuple(roi),t_us,int(c.window_ms*1000),c.cell_px)
        x=counts.astype(float)
        result=dict(status='RUN',raw_pixels=int(total_raw),raw_spatial_pixels=int(counts.sum()),max_z=0.,active_fraction=0.,tracks=[],
                    thresholds=c.to_dict(),warmup_remaining_ms=0.)
        if self.first_t is None: self.first_t=t_us
        if not self.ready:
            self.n+=1; delta=x-self.mean; self.mean+=delta/self.n; self.m2+=delta*(x-self.mean)
            self.var=np.maximum(self.m2/max(1,self.n-1),c.variance_floor)
            elapsed=(t_us-self.first_t)/1000
            self.ready=elapsed>=c.warmup_ms
            result.update(status='BACKGROUND_WARMUP',warmup_remaining_ms=max(0,c.warmup_ms-elapsed))
            return result
        sigma=np.sqrt(np.maximum(self.var,np.maximum(self.mean,c.variance_floor)))
        z=(x-self.mean)/sigma
        active=(counts>0)&(z>=c.z_threshold)
        roi_cells=max(1,((roi[2]-1)//c.cell_px-roi[0]//c.cell_px+1)*((roi[3]-1)//c.cell_px-roi[1]//c.cell_px+1))
        fraction=float(active.sum())/roi_cells
        result.update(max_z=float(z.max(initial=0)),active_fraction=fraction)
        if fraction>c.max_active_fraction:
            self.tracks=[]; result['status']='GLOBAL_RAW_ACTIVITY'; return result
        n,labels,stats,_=cv2.connectedComponentsWithStats(active.astype(np.uint8),connectivity=8)
        pixel_totals=np.bincount(labels.ravel(),weights=counts.ravel(),minlength=n)
        eligible=[i for i in range(1,n) if pixel_totals[i]>=c.min_pixels]
        if len(eligible)>c.max_regions:
            self.tracks=[]; result['status']='TOO_MANY_RAW_REGIONS'; return result
        regions=[]
        for lab in eligible:
            gx,gy,w,h,_=map(int,stats[lab])
            sl=np.s_[gy:gy+h,gx:gx+w]; sel=labels[sl]==lab
            total=float(counts[sl][sel].sum())
            regions.append(dict(bbox=[max(roi[0],gx*c.cell_px),max(roi[1],gy*c.cell_px),
                                  min(roi[2],(gx+w)*c.cell_px),min(roi[3],(gy+h)*c.cell_px)],
                                center=[float(sx[sl][sel].sum()/total),float(sy[sl][sel].sum()/total)],
                                pixels=int(total),z=float(z[sl][sel].max())))
        # Do not learn the foreground into the background. Adjacent cells are
        # frozen too; only the small grid is dilated, not the event display.
        freeze=cv2.dilate(active.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
        alpha=1-math.exp(-min(dt,c.clear_ms)/c.background_tau_ms)
        delta=x-self.mean
        self.mean=np.where(freeze,self.mean,self.mean+alpha*delta)
        self.var=np.where(freeze,self.var,np.maximum(c.variance_floor,(1-alpha)*self.var+alpha*delta*delta))
        self.tracks=[tr for tr in self.tracks if t_us-tr['last_seen']<=c.clear_ms*1000]
        for tr in self.tracks: tr['history'].append(False)
        pairs=[]
        for i,tr in enumerate(self.tracks):
            for j,r in enumerate(regions):
                d=math.dist(tr['center'],r['center'])
                extent=max(tr['bbox'][2]-tr['bbox'][0],tr['bbox'][3]-tr['bbox'][1],
                           r['bbox'][2]-r['bbox'][0],r['bbox'][3]-r['bbox'][1])
                gate=min(c.association_px,max(8.0,extent*0.5))
                if d<=gate: pairs.append((d,i,j))
        used_t=set(); used_r=set()
        for _,i,j in sorted(pairs):
            if i in used_t or j in used_r: continue
            tr=self.tracks[i]; r=regions[j]
            if not tr['confirmed'] and t_us-tr['last_seen'] > 1.6*c.window_ms*1000:
                tr['history']=deque([False],maxlen=c.history_windows)
                tr['first_seen']=t_us;tr['first_center']=list(r['center']);tr['hits']=0
            tr.update(r); tr['history'][-1]=True; tr['hits']+=1; tr['last_seen']=t_us
            tr['confirmed']=bool(tr['confirmed'] or sum(tr['history'])>=c.confirm_hits)
            used_t.add(i);used_r.add(j)
        for j,r in enumerate(regions):
            if j in used_r or len(self.tracks)>=c.max_regions:continue
            self.tracks.append(dict(r,id=self.next_id,first_seen=t_us,last_seen=t_us,hits=1,
                                    history=deque([True],maxlen=c.history_windows),confirmed=False,
                                    first_center=list(r['center'])))
            self.next_id+=1
        result['tracks']=[dict((k,v) for k,v in tr.items() if k!='history') for tr in self.tracks]
        for tr in result['tracks']:
            tr['age_ms']=(t_us-tr['last_seen'])/1000
            tr['span_ms']=(t_us-tr['first_seen'])/1000
            tr['displacement_px']=math.dist(tr['center'],tr['first_center'])
            tr['state']='COASTING' if tr['age_ms'] else ('CONFIRMED_ACTIVITY' if tr['confirmed'] else 'PENDING')
        return result


def evidence_flags(raw,periodic_tracks,t_us,cfg,valid=True,rotor_status='RUN'):
    """Flags are not mutually exclusive. Candidate is a documented heuristic.

    Additional corroboration beyond periodicity: a fresh raw track spanning
    >=200 ms and either >=8 px displacement or >=2 spatially separated periodic
    regions inside it. Moving lights and fans can still pass: never identity.
    """
    if not valid:
        return dict(flags={k:None for k in FLAG_NAMES},identity='UNKNOWN',
                    unknown_reason='unavailable_invalid_data',detail='No current valid decision',objects=[])
    pts=[p for p in periodic_tracks if p.get('confirmed') and p.get('state')!='COASTING' and rotor_status=='RUN']
    active=[r for r in raw.get('tracks',[]) if r['confirmed'] and r['state']!='COASTING' and raw['status']=='RUN']
    objects=[]
    for tr in raw.get('tracks',[]):
        x0,y0,x1,y1=tr['bbox']; m=cfg.rotor_match_margin_px
        matches=[p for p in pts if x0-m<=p['center'][0]<x1+m and y0-m<=p['center'][1]<y1+m]
        multiple=any(math.dist(p['center'],q['center'])>=8 for i,p in enumerate(matches) for q in matches[i+1:])
        activity=tr in active
        movement=tr['displacement_px']>=cfg.candidate_motion_px
        mature=tr['span_ms']>=cfg.candidate_age_ms
        candidate=bool(activity and matches and mature and (movement or multiple))
        reasons=[]
        if activity:reasons.append('persistent_raw_cluster')
        if matches:reasons.append('coincident_repeatable_periodicity')
        if mature and movement:reasons.append('image_displacement')
        if multiple:reasons.append('multiple_periodic_regions')
        objects.append(dict(track_id='A'+str(tr['id']),bbox=tr['bbox'],center=tr['center'],
                            flags=dict(ACTIVITY=activity,ROTOR_EVIDENCE=bool(matches),DRONE_CANDIDATE=candidate),
                            state=tr['state'],raw_pixels=tr['pixels'],raw_z=tr['z'],age_ms=tr['span_ms'],
                            displacement_px=tr['displacement_px'],periodic_ids=[p['id'] for p in matches],
                            frequency_hz=[p['hz'] for p in matches],reasons=reasons))
    matched={i for o in objects for i in o['periodic_ids']}
    for p in pts:
        if p['id'] not in matched:
            objects.append(dict(track_id='P'+str(p['id']),bbox=p['bbox'],center=p['center'],
                        flags=dict(ACTIVITY=False,ROTOR_EVIDENCE=True,DRONE_CANDIDATE=False),
                        state=p['state'],frequency_hz=[p['hz']],reasons=['periodicity_without_raw_association']))
    flags=dict(ACTIVITY=bool(active),ROTOR_EVIDENCE=bool(pts),
               DRONE_CANDIDATE=any(o['flags']['DRONE_CANDIDATE'] for o in objects))
    if flags['DRONE_CANDIDATE']:
        identity='POSSIBLE_DRONE'; reason=None;detail='Activity + associated periodicity + motion or multiple patches; unverified'
    elif not active:
        identity='UNKNOWN';reason='insufficient_activity';detail=raw.get('status','RUN')
    else:
        identity='UNKNOWN';reason='insufficient_rotor_evidence'
        detail='No associated confirmed periodic patch' if not any(o.get('periodic_ids') for o in objects) else 'Periodicity present; additional candidate corroboration not met'
    return dict(flags=flags,identity=identity,unknown_reason=reason,detail=detail,objects=objects)
