"""Independent synthetic scene generator for SOFTWARE tests, not a sensor twin.

A generic four-arm quadcopter is rasterized as a body, arms and rotating
2-blade silhouettes. A sampled log-contrast threshold produces ON/OFF events.
Unlike periodic_events(), periods are not injected into the event list.
Projection, contrast, missing events and noise are adjustable. There is no
calibrated lux, range, rotor RPM, lens, EVK4 noise or specific Teal model here.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import time
import cv2
import numpy as np
from rotor import EVENT_DTYPE
from event_io import Packet


@dataclass
class QuadSpec:
    width: int = 192
    height: int = 144
    duration_s: float = 0.8
    start_s: float = 0.06
    stop_s: float = 0.62
    hz: tuple = (240.0, 260.0, 280.0, 300.0)  # optical blade passage, not shaft RPM
    radius_px: float = 9.0
    blade_width_px: float = 1.4
    span_x_px: float = 28.0
    span_y_px: float = 22.0
    center_x: float = 96.0
    center_y: float = 72.0
    vx_px_s: float = 0.0
    vy_px_s: float = 0.0
    yaw_rate_rad_s: float = 0.0
    vertical_scale: float = 1.0
    contrast: float = 1.0  # log-intensity difference, NOT lux
    threshold: float = 0.22
    sample_us: int = 100
    keep_probability: float = 1.0
    noise_events_s: float = 2000.0
    timestamp_jitter_us: float = 0.0
    occlusion: tuple = ()  # optional (start_s, end_s), no object in scene
    disabled_rotors: tuple = ()
    ramp_hz_s: float = 0.0
    seed: int = 1

    def centers(self, t):
        dt=max(0.0,t-self.start_s)
        a=self.yaw_rate_rad_s*dt
        xy=np.array([[-self.span_x_px,-self.span_y_px],
                     [self.span_x_px,-self.span_y_px],
                     [self.span_x_px,self.span_y_px],
                     [-self.span_x_px,self.span_y_px]],dtype=float)
        R=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
        xy=xy@R.T
        xy[:,1]*=self.vertical_scale
        return xy+np.array([self.center_x+self.vx_px_s*dt,self.center_y+self.vy_px_s*dt])

    def visible(self,t):
        return (self.start_s <= t < self.stop_s and
                not (len(self.occlusion)==2 and self.occlusion[0] <= t < self.occlusion[1]))


def luminance_frame(spec: QuadSpec, t: float):
    """Return a log-luminance contrast raster with four independently rotating blades."""
    img=np.zeros((spec.height,spec.width),np.float32)
    if not spec.visible(t):return img
    dt=t-spec.start_s
    c=(spec.center_x+spec.vx_px_s*dt,spec.center_y+spec.vy_px_s*dt)
    centers=spec.centers(t)
    # A deliberately generic body and four arms, no manufacturer geometry.
    cp=(round(c[0]),round(c[1]))
    for px,py in centers:
        cv2.line(img,cp,(round(px),round(py)),0.6*spec.contrast,2)
    cv2.rectangle(img,(cp[0]-6,cp[1]-10),(cp[0]+6,cp[1]+10),0.7*spec.contrast,-1)
    for i,(px,py) in enumerate(centers):
        if i in spec.disabled_rotors:continue
        r=spec.radius_px
        x0=max(0,int(math.floor(px-r-2)));x1=min(spec.width,int(math.ceil(px+r+2)))
        y0=max(0,int(math.floor(py-r*spec.vertical_scale-2)));y1=min(spec.height,int(math.ceil(py+r*spec.vertical_scale+2)))
        if x1<=x0 or y1<=y0:continue
        yy,xx=np.mgrid[y0:y1,x0:x1]
        dx=xx+0.5-px;dy=(yy+0.5-py)/max(spec.vertical_scale,0.03)
        # Two blades: rotation rate is half the requested blade-pass rate.
        angle=math.pi*(spec.hz[i]*dt+0.5*spec.ramp_hz_s*dt*dt)+i*0.43
        across=-math.sin(angle)*dx+math.cos(angle)*dy
        rr=dx*dx+dy*dy
        mask=(rr<=r*r)&(rr>1.0)&(np.abs(across)<spec.blade_width_px/2)
        img[y0:y1,x0:x1][mask]=spec.contrast
    return img


def render_events(spec: QuadSpec):
    """Sample contrast and emit threshold crossings; deterministic from spec/seed.

    Discretization has a finite sample rate. Do not interpret the resulting
    tests as calibrated physics, absolute lux, distance, or real aircraft recall.
    """
    if spec.sample_us<10 or spec.duration_s<=0 or spec.threshold<=0:
        raise ValueError('Invalid synthetic sampling/duration/contrast threshold')
    rng=np.random.default_rng(spec.seed)
    reference=np.zeros((spec.height,spec.width),np.float32)
    parts=[]
    for us in range(0,int(spec.duration_s*1e6),spec.sample_us):
        frame=luminance_frame(spec,us/1e6)
        delta=frame-reference
        steps=np.floor(np.abs(delta)/spec.threshold).astype(np.int16)
        yy,xx=np.nonzero(steps)
        if not len(xx):continue
        counts=steps[yy,xx]
        n=int(counts.sum())
        ev=np.zeros(n,EVENT_DTYPE)
        ev['t']=us
        ev['x']=np.repeat(xx,counts);ev['y']=np.repeat(yy,counts)
        ev['on']=np.repeat(delta[yy,xx]>0,counts)
        reference[yy,xx]+=np.sign(delta[yy,xx])*counts*spec.threshold
        if spec.keep_probability<1:
            ev=ev[rng.random(len(ev))<spec.keep_probability]
        parts.append(ev)
    n=int(spec.noise_events_s*spec.duration_s)
    noise=np.zeros(n,EVENT_DTYPE)
    noise['t']=rng.integers(0,int(spec.duration_s*1e6),n)
    noise['x']=rng.integers(0,spec.width,n);noise['y']=rng.integers(0,spec.height,n)
    noise['on']=rng.integers(0,2,n).astype(bool)
    parts.append(noise)
    ev=np.concatenate(parts) if parts else np.zeros(0,EVENT_DTYPE)
    if spec.timestamp_jitter_us and len(ev):
        jitter=rng.normal(0,spec.timestamp_jitter_us,len(ev)).astype(np.int64)
        ev['t']=np.clip(ev['t'].astype(np.int64)+jitter,0,int(spec.duration_s*1e6)-1)
    ev.sort(order='t',kind='stable')
    return ev


class QuadSource:
    """Streaming generic quadcopter demo. Source geometry remains 1280 x 720.

    A small raster is embedded at native sensor coordinates, not stretched.
    It has a quiet prelude/tail and independent rotor blade-pass rates.
    """
    def __init__(self,duration=6,realtime=True,hz=240,scenario='quad'):
        self.duration=duration;self.realtime=realtime
        stop=max(0.2,duration-0.5);start=min(0.5,duration*0.1)
        self.spec=QuadSpec(duration_s=duration,start_s=start,stop_s=stop,
                           hz=(hz,hz*1.07,hz*1.14,hz*1.21),noise_events_s=2000)
        if scenario in ('quad_move','quad_fast'):
            self.spec.vx_px_s=12 if scenario=='quad_move' else 180
            # Slow demo traverses repeatedly instead of drifting off a small raster.
            if scenario=='quad_move':self.spec.vx_px_s=min(12,45/max(0.1,duration-1))
        if scenario=='quad_dropout':self.spec.keep_probability=0.35
        self.width=1280;self.height=720;self.scenario=scenario
    def __enter__(self):
        self.info=dict(source='synthetic',width=self.width,height=self.height,
                       scenario=self.scenario,model='generic quad sampled log-contrast, NOT a Teal sensor twin',
                       synthetic_spec=asdict(self.spec),not_real_drone=True)
        self.events=render_events(self.spec)
        self.events['x']+=544;self.events['y']+=288
        # Cache the timestamp column once; searchsorted may copy a strided
        # structured-array column on every packet otherwise. Demo only.
        self._times=np.ascontiguousarray(self.events['t'])
        return self
    def __exit__(self,*exc):self.events=None;self._times=None
    def clear(self):pass
    def __iter__(self):
        i=0;start=time.monotonic()
        for end in range(5000,int(self.duration*1e6)+5000,5000):
            j=int(np.searchsorted(self._times,end,'left'))
            ev=self.events[i:j];i=j
            if self.realtime:time.sleep(max(0,start+end/1e6-time.monotonic()))
            yield Packet(ev,end)
