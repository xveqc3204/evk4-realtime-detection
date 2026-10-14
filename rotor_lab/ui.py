"""Monochrome instrument UI with EVK-style yellow/blue polarity rendering.

No GUI operation is part of the event-processing worker. Image panels are
previews, not intensity photographs. Colors are a chosen display convention.
"""
from __future__ import annotations
from collections import defaultdict, deque
import time
import cv2
import numpy as np

CANVAS_W, CANVAS_H = 1440, 900
WHITE=(235,235,235); MUTED=(160,160,160); LINE=(65,65,65)
YELLOW=(50,210,255); BLUE=(255,145,45)  # BGR. ON yellow, OFF blue.


def polarity_image(raw):
    out=np.zeros((*raw.shape,3),np.uint8)
    out[raw==1]=BLUE
    out[raw==2]=YELLOW
    return out


def filtered_image(freq):
    return np.repeat(np.where(freq>0,255,0).astype(np.uint8)[...,None],3,axis=2)


def is_fresh(snap,cfg,now=None):
    now=time.monotonic() if now is None else now
    age=now-snap.get('evaluated_monotonic',snap.get('published_monotonic',now))
    return snap.get('kind')=='frame' and 0<=age<=cfg.silence_ms/1000


def clean_panels(snap,cfg,now=None):
    if not is_fresh(snap,cfg,now):
        blank=np.zeros((360,640,3),np.uint8)
        return blank,blank.copy()
    raw=polarity_image(np.asarray(snap['raw']))
    filtered=filtered_image(np.asarray(snap['frequency']))
    return raw,filtered


class History:
    """Short, bounded display history. Fresh measured centers only, never coasting."""
    def __init__(self):
        self.points=defaultdict(lambda:deque(maxlen=500))
        self.last_t=None
    def add(self,snap):
        t=snap.get('t_us')
        if t is None or t==self.last_t or snap.get('kind')!='frame':return
        self.last_t=t
        for tr in snap.get('activity_tracks',snap.get('tracks',[])):
            if tr['confirmed'] and tr['state']!='COASTING':
                self.points[int(tr['id'])].append((t,*tr['center'],tr.get('hz',0.0)))
        for tid in list(self.points):
            pts=self.points[tid]
            while pts and t-pts[0][0]>10_000_000:pts.popleft()
            if not pts:del self.points[tid]
        # A long session of clutter must not make the GUI history unbounded.
        if len(self.points)>64:
            for tid in sorted(self.points,key=lambda i:self.points[i][-1][0])[:-64]:
                del self.points[tid]


def draw_frame(snap,cfg,rgb_frame=None,rgb_age=None,with_rgb=False,stripped=False,
               now=None,history=None,overlays=True,recording=False,run_name=''):
    now=time.monotonic() if now is None else now
    frame=np.zeros((CANVAS_H,CANVAS_W,3),np.uint8)
    def text(s,x,y,scale=.48,color=WHITE,thick=1):
        cv2.putText(frame,str(s),(int(x),int(y)),cv2.FONT_HERSHEY_SIMPLEX,scale,color,thick,cv2.LINE_AA)
    def line(a,b,color=LINE):cv2.line(frame,a,b,color,1,cv2.LINE_AA)
    fresh=is_fresh(snap,cfg,now)
    status=snap.get('status','STARTING')
    if snap.get('kind')=='frame' and not fresh:status='STALE_DATA'
    flag=bool(fresh and status=='RUN' and snap.get('flag'))
    mode='SYNTHETIC TEST' if snap.get('synthetic') else ('RECORDED REPLAY' if snap.get('replay') else 'LIVE EVK4')
    text('EVK4  /  ROTOR LAB',22,35,.88,WHITE,2)
    text('ACTIVITY FIRST  |  Raw: '+snap.get('activity_preset','sensitive')+'  |  Period input: '+snap.get('period_input','native'),25,59,.4,MUTED)
    if snap.get('captured'):mode='SNAPSHOT / '+mode
    text(mode,930,30,.49,WHITE,1)
    text(('RECORDING ENABLED' if recording else 'VIEW + TELEMETRY')+'  |  '+status,930,55,.42)
    line((20,75),(1420,75))
    if 'flags' in snap:
        valid=fresh and status=='RUN'
        for x,key,title in [(22,'ACTIVITY','ACTIVITY'),(390,'ROTOR_EVIDENCE','ROTOR EVIDENCE'),(880,'DRONE_CANDIDATE','DRONE CANDIDATE')]:
            value=snap['flags'].get(key) if valid else None
            label='N/A' if value is None else str(int(value))
            text(title+'  '+label,x,103,.52,WHITE,2)
        detail=snap.get('unknown_reason') or snap.get('identity','UNKNOWN')
        if not valid:detail='unavailable / invalid data'
        text(str(detail).replace('_',' ')+'  |  '+str(snap.get('reason_detail',''))[:92],22,124,.34,MUTED)
    else:
        flag_text = str(int(flag)) if fresh and status == 'RUN' else 'UNAVAILABLE'
        text(f'ROTOR_CANDIDATE  {flag_text}',22,108,.57,WHITE,2)
        text('Periodic optical evidence. Identity unverified.',440,106,.42,MUTED)
    text(f'{cfg.min_hz:g} - {cfg.max_hz:g} Hz',1260,124,.35,MUTED)
    raw,filt=clean_panels(snap,cfg,now)
    native_w=snap.get('width',1280);native_h=snap.get('height',720)
    # Two full-size panels, or three smaller panels when reference RGB is present.
    n=1 if stripped else (3 if with_rgb else 2)
    gap=20; pw=(CANVAS_W-gap*(n+1))//n; image_top=160; area_h=366
    panels=[]
    if stripped:panels=[('FILTERED PERIODIC PIXELS',filt,'filtered')]
    else:
        panels=[('RAW EVENTS  /  ON yellow + OFF blue',raw,'raw'),
                ('PERIODIC PIXELS  /  WHITE = SUPPORTED',filt,'filtered')]
        if with_rgb:
            if rgb_frame is not None and rgb_age is not None and rgb_age<1:rgb=rgb_frame
            else:rgb=np.zeros((360,640,3),np.uint8)
            panels.append(('RGB REFERENCE  /  UNSYNCHRONIZED',rgb,'rgb'))
    for i,(title,img,kind) in enumerate(panels):
        x=20+i*(pw+gap)
        text(title,x,145,.44)
        ih,iw=img.shape[:2];scale=min(pw/iw,area_h/ih)
        ww,hh=max(1,round(iw*scale)),max(1,round(ih*scale))
        xx=x+(pw-ww)//2; yy=image_top+(area_h-hh)//2
        frame[yy:yy+hh,xx:xx+ww]=cv2.resize(img,(ww,hh),interpolation=cv2.INTER_NEAREST if kind!='rgb' else cv2.INTER_AREA)
        cv2.rectangle(frame,(x-1,image_top-1),(x+pw,image_top+area_h),LINE,1)
        if fresh and overlays and kind!='rgb':
            panel_tracks=snap.get('activity_tracks',snap.get('tracks',[])) if kind=='raw' else snap.get('tracks',[])
            for tr in panel_tracks:
                x0,y0,x1,y1=tr['bbox']
                x0=max(0,min(native_w-1,x0));x1=max(0,min(native_w,x1))
                y0=max(0,min(native_h-1,y0));y1=max(0,min(native_h,y1))
                a=(xx+int(x0/native_w*ww),yy+int(y0/native_h*hh))
                b=(xx+int(x1/native_w*ww),yy+int(y1/native_h*hh))
                cc=MUTED if tr['state']=='COASTING' else WHITE
                cv2.rectangle(frame,a,b,cc,1)
                prefix='A' if kind=='raw' and 'activity_tracks' in snap else 'P'
                tag=prefix+str(tr['id'])+(' C' if tr['state']=='COASTING' else (' ?' if not tr['confirmed'] else ''))
                tx=max(x,min(a[0],x+pw-len(tag)*7));ty=max(image_top+16,a[1]-7)
                text(tag,tx,ty,.33,cc)
            # Keep frequency text away from neighboring small rotor boxes.
            if kind=='filtered':
                for row,tr in enumerate(snap.get('tracks',[])[:4]):
                    text(f"P{tr['id']}  {tr['hz']:.0f} Hz  {tr['pixels']} px",x+10,image_top+18+row*18,.34,MUTED)
            elif 'raw_activity' in snap:
                rr=snap['raw_activity']
                text(f"{rr.get('status','RUN')} | {rr.get('raw_pixels',0)} active pixels / 20 ms",x+10,image_top+18,.34,MUTED)
            roi=tuple(snap.get('roi',(0,0,native_w,native_h)))
            if kind=='raw' and roi!=(0,0,native_w,native_h):
                a=(xx+round(roi[0]/native_w*ww),yy+round(roi[1]/native_h*hh))
                b=(xx+round(roi[2]/native_w*ww),yy+round(roi[3]/native_h*hh))
                cv2.rectangle(frame,a,b,MUTED,1)
        if kind=='rgb' and (rgb_frame is None or rgb_age is None or rgb_age>=1):
            text('NO FRESH RGB FRAME',x+25,image_top+area_h//2,.50,WHITE)
            text('Not a low-light image',x+25,image_top+area_h//2+26,.40,MUTED)
        if kind=='raw':text(f'Recent {cfg.view_ms:g} ms. Display colors do not encode frequency.',x,548,.4,MUTED)
        elif kind=='filtered':text('Measured periodic pixels. Not motor-only segmentation.',x,548,.4,MUTED)
        else:text('Comparison only. Host receipt time is not exposure time.',x,548,.36,MUTED)
    line((20,565),(1420,565))
    # Histogram: counts of qualifying native pixels, not an amplitude FFT spectrum.
    text('FREQUENCY DISTRIBUTION',22,592,.52,WHITE,1)
    text('Supported native pixels per bin. Not an FFT.',22,613,.37,MUTED)
    hx,hy,hw,hh=64,636,565,118
    hist=np.asarray(snap.get('histogram',np.zeros(64))) if fresh else np.zeros(64)
    top=max(1,int(hist.max(initial=0)))
    for j,v in enumerate(hist):
        x0=hx+round(j*hw/len(hist));x1=hx+round((j+1)*hw/len(hist))-1
        if v>0:cv2.rectangle(frame,(x0,hy+hh-round(v/top*hh)),(max(x0,x1),hy+hh),WHITE,-1)
    line((hx,hy),(hx,hy+hh));line((hx,hy+hh),(hx+hw,hy+hh))
    text(top,hx-40,hy+8,.35,MUTED);text('0',hx-18,hy+hh,.35,MUTED)
    for hz in (cfg.min_hz,(cfg.min_hz+cfg.max_hz)/2,cfg.max_hz):
        xp=hx+round((hz-cfg.min_hz)/(cfg.max_hz-cfg.min_hz)*hw)
        text(f'{hz:g}',xp-16,hy+hh+20,.36,MUTED)
    text('Optical repetition frequency (Hz)',hx+125,hy+hh+42,.38,MUTED)
    # 2D image-plane history; no arbitrary depth or drone geometry.
    text('2D ACTIVITY PATH' if 'activity_tracks' in snap else '2D PERIODIC-PATCH PATH',701,592,.5,WHITE)
    text('Last 10 s of fresh confirmed centers. Pixels, not meters.',701,613,.35,MUTED)
    tx,ty,tw,th=702,635,310,160
    cv2.rectangle(frame,(tx,ty),(tx+tw,ty+th),LINE,1)
    for q in (1,2,3):
        line((tx+q*tw//4,ty),(tx+q*tw//4,ty+th),(30,30,30))
        line((tx,ty+q*th//4),(tx+tw,ty+q*th//4),(30,30,30))
    if history is not None:
        for tid,pts in list(history.points.items())[-12:]:
            for a,b in zip(pts,list(pts)[1:]):
                if b[0]-a[0]>cfg.clear_ms*1000:continue
                p0=(tx+round(a[1]/native_w*tw),ty+round(a[2]/native_h*th))
                p1=(tx+round(b[1]/native_w*tw),ty+round(b[2]/native_h*th))
                cv2.line(frame,p0,p1,WHITE,1,cv2.LINE_AA)
            if pts:
                end=pts[-1];xp=tx+round(end[1]/native_w*tw);yp=ty+round(end[2]/native_h*th)
                cv2.circle(frame,(xp,yp),3,WHITE,1)
                # IDs remain in the image overlay and exports; no overlapping path labels.
    text('x (sensor px) ->',tx+70,818,.36,MUTED)
    # Telemetry uses words rather than unlabeled nominal latency numbers.
    x=1050
    delay=snap.get('delay_ms');d='n/a' if delay is None else f'{delay:.2f} ms'
    age=max(0,now-snap.get('evaluated_monotonic',now))*1000
    items=[('INPUT',f"{snap.get('rate_mev_s',0):.2f} Mev/s"),('DRIVER DELAY',d),
           ('BACKLOG',str(snap.get('backlog',0))),('FRESH PIXELS',str(snap.get('periodic_pixels',0) if fresh else 0)),
           ('CYCLE-ONLY PIXELS',str(snap.get('stable_pixels',0) if fresh else 0)),('MAP AGE',f'{age:.0f} ms')]
    for i,(key,value) in enumerate(items):text(key,x,647+i*27,.32,MUTED);text(value,x+205,647+i*27,.41)
    line((20,837),(1420,837))
    text('S photo | F filtered | O boxes | B raw preset | N period input | C ROI / A full | R reset | 1 present / 2 absent | Q stop',22,860,.42)
    note=snap.get('recording_error') or snap.get('error') or 'Driver delay is not total detection latency. No 3D depth is measured. '+run_name
    text(str(note)[:174],22,885,.36,MUTED)
    return frame
