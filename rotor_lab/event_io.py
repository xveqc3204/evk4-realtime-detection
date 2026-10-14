"""Live, synthetic, and EVK4DET1 file sources; bounded optional recording.

The decoded 13-byte recording layout is compatible with the earlier demo
bridge. It is not Prophesee EVT3 RAW. No upstream code needs to be downloaded.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import queue
import struct
import threading
import time

import numpy as np
from rotor import EVENT_DTYPE

MAGIC=b'EVK4DET1'


@dataclass
class Packet:
    events: np.ndarray | None
    t_us: int | None = None
    delay_ms: float | None = None
    backlog: int = 0
    overflow: bool = False


class LiveSource:
    def __enter__(self):
        import neuromorphic_drivers as nd
        self.device=nd.open(iterator_timeout=0.01,iterator_maximum_raw_packets=8)
        self.device.__enter__()
        props=self.device.properties()
        self.width,self.height=props.width,props.height
        self.info=dict(source='live',name=str(self.device.name()),serial=self.device.serial(),
                       width=self.width,height=self.height,speed=str(self.device.speed()))
        return self
    def __exit__(self,*exc):
        self.device.__exit__(*exc)
    def clear(self):
        self.device.clear_backlog(until=0)
    def __iter__(self):
        for status,packet in self.device:
            ring=status.ring
            delay=status.delay() if ring is not None else None
            ev=None if packet is None else packet.polarity_events
            indices=None if packet is None else getattr(packet,'polarity_events_overflow_indices',None)
            yield Packet(ev,None if ring is None or ring.current_t is None else int(ring.current_t),
                         None if delay is None else float(delay)*1000,
                         0 if ring is None else int(ring.backlog),
                         indices is not None and len(indices)>0)


def read_recording(path):
    path=Path(path)
    with path.open('rb') as f:
        if f.read(8)!=MAGIC:
            raise ValueError('Expected EVK4DET1 .evs recording, not EVT3 RAW or a video')
        length=f.read(4)
        if len(length)!=4:
            raise ValueError('Truncated recording header')
        n=struct.unpack('<I',length)[0]
        if n>4*1024*1024:
            raise ValueError('Unreasonably large recording header')
        body=f.read(n)
        if len(body)!=n:
            raise ValueError('Truncated recording metadata')
        header=json.loads(body)
    offset=12+n
    data_size=path.stat().st_size-offset
    if data_size<0 or data_size%EVENT_DTYPE.itemsize:
        raise ValueError('Recording ends in a partial event. Preserve it but do not claim it is complete.')
    if not data_size:
        return header,np.zeros(0,dtype=EVENT_DTYPE)
    return header,np.memmap(path,dtype=EVENT_DTYPE,mode='r',offset=offset)


class FileSource:
    def __init__(self,path,realtime=True):
        self.path=str(path)
        self.realtime=realtime
    def __enter__(self):
        self.header,self.events=read_recording(self.path)
        geom=self.header.get('source_info',{})
        self.width=int(geom.get('width',self.header.get('width',1280)))
        self.height=int(geom.get('height',self.header.get('height',720)))
        self.info=dict(source='replay',path=self.path,width=self.width,height=self.height,
                       file_header=self.header)
        return self
    def __exit__(self,*exc):
        self.events=None
    def clear(self):
        pass
    def __iter__(self):
        if not len(self.events):
            return
        t0=int(self.events['t'][0]);start=time.monotonic();i=0
        while i<len(self.events):
            # Bound both duration and event count of replay packets.
            limit=min(len(self.events),i+100000)
            j=i+int(np.searchsorted(self.events['t'][i:limit],int(self.events['t'][i])+5000,'left'))
            j=max(i+1,j)
            ev=np.asarray(self.events[i:j])
            if self.realtime:
                time.sleep(max(0,start+(int(ev['t'][-1])-t0)/1e6-time.monotonic()))
            yield Packet(ev,int(ev['t'][-1]))
            i=j


def periodic_events(hz=240.0, duration_s=0.25, points=None, start_us=0,
                    burst=3, jitter=0.0, seed=1):
    """Test signal: periodic ON/OFF bursts. Not a physics-based drone model."""
    if points is None:
        points=[(x,y) for y in range(30,34) for x in range(30,34)]
    rng=np.random.default_rng(seed);out=[];period=1e6/hz
    for x,y in points:
        phase=rng.uniform(0,period)
        for c in range(int(duration_s*hz)+2):
            # Same period for each ON/OFF pair; each point has a distinct phase.
            shift=rng.normal(0,jitter*period)
            for on,frac in ((True,0.0),(False,0.5)):
                edge=start_us+phase+(c+frac)*period+shift
                for b in range(burst):
                    t=int(edge+b*min(10.0,period/100))
                    if start_us<=t<start_us+duration_s*1e6:
                        out.append((t,x,y,on))
    ev=np.array(out,dtype=EVENT_DTYPE)
    if len(ev):ev.sort(order='t',kind='stable')
    return ev


class DemoSource:
    """Explicitly synthetic moving periodic patch, clutter, and a quiet tail."""
    def __init__(self,duration=10,realtime=True,hz=240,scenario='periodic'):
        self.duration=duration;self.realtime=realtime;self.hz=hz;self.scenario=scenario
        self.width=1280;self.height=720
    def __enter__(self):
        self.info=dict(source='synthetic',width=self.width,height=self.height,
                       hz=self.hz,scenario=self.scenario,not_real_drone=True)
        # A small amount of broadband background throughout, including the quiet tail.
        rng=np.random.default_rng(42)
        n=int(self.duration*6000)
        ev=np.zeros(n,dtype=EVENT_DTYPE)
        ev['t']=rng.uniform(0,self.duration*1e6,n).astype(np.uint64)
        ev['x']=rng.integers(0,self.width,n,dtype=np.uint16)
        ev['y']=rng.integers(0,self.height,n,dtype=np.uint16)
        ev['on']=rng.integers(0,2,n).astype(bool)
        chunks=[ev]
        active_start=min(1.0,self.duration*.15)
        active_end=max(active_start,self.duration-1.0)
        if self.scenario=='noise':
            n=int(max(0,active_end-active_start)*100000)
            ev=np.zeros(n,dtype=EVENT_DTYPE)
            ev['t']=rng.uniform(active_start*1e6,active_end*1e6,n).astype(np.uint64)
            ev['x']=rng.integers(420,460,n,dtype=np.uint16)
            ev['y']=rng.integers(300,340,n,dtype=np.uint16)
            ev['on']=rng.integers(0,2,n).astype(bool)
            chunks.append(ev)
        elif self.scenario=='global':
            # Generate broad periodic illumination incrementally, not a huge
            # multi-second event list in memory. Every other analysis tile fires.
            yy,xx=np.mgrid[4:720:8,4:1280:8]
            self.global_xy=np.column_stack((xx.ravel()[::2],yy.ravel()[::2]))
            self.active_start_us=int(active_start*1e6)
            self.active_end_us=int(active_end*1e6)
        else:
            # Slowly translate a periodically flashing 16x12 patch. This is not
            # evidence that actual translating propellers will be resolved.
            pts=[(x,y) for y in range(12) for x in range(16)]
            ev=periodic_events(self.hz,active_end-active_start,pts,int(active_start*1e6),burst=3)
            tt=ev['t'].astype(np.float64)/1e6-active_start
            ev['x']=(ev['x']+200+tt*45).astype(np.uint16)
            ev['y']=(ev['y']+340+np.sin(tt)*25).astype(np.uint16)
            chunks.append(ev)
        self.events=np.concatenate(chunks)
        self.events.sort(order='t',kind='stable')
        return self
    def __exit__(self,*exc):
        self.events=None
    def clear(self):pass
    def __iter__(self):
        start=time.monotonic();i=0
        # Includes quiet sensor-time windows, independent of display speed.
        for end in range(5000,int(self.duration*1e6)+5000,5000):
            j=int(np.searchsorted(self.events['t'],end,'left'))
            pkt=self.events[i:j]
            if self.scenario=='global':
                half_period=0.5e6/self.hz
                lo=max(end-5000,self.active_start_us);hi=min(end,self.active_end_us)
                parts=[pkt]
                first=max(0,int(np.ceil((lo-self.active_start_us)/half_period)))
                last=max(first,int(np.ceil((hi-self.active_start_us)/half_period)))
                for edge in range(first,last):
                    pulse=np.zeros(len(self.global_xy),dtype=EVENT_DTYPE)
                    pulse['t']=int(self.active_start_us+edge*half_period)
                    pulse['x']=self.global_xy[:,0];pulse['y']=self.global_xy[:,1]
                    pulse['on']=edge%2==0
                    parts.append(pulse)
                pkt=np.concatenate(parts);pkt.sort(order='t',kind='stable')
            if self.realtime:time.sleep(max(0,start+end/1e6-time.monotonic()))
            yield Packet(pkt,end)
            i=j


class Recorder:
    """Bounded asynchronous writer. Any observed omission is reported."""
    def __init__(self,path,metadata,max_bytes=64*1024*1024):
        hb=json.dumps({'dtype':EVENT_DTYPE.descr,'created_unix':time.time(),**metadata}).encode()
        self.fh=Path(path).open('xb')
        self.fh.write(MAGIC+struct.pack('<I',len(hb))+hb)
        self.count=0;self.error=None;self.bytes_pending=0;self.limit=max_bytes
        self.q=queue.Queue(maxsize=32);self.lock=threading.Lock()
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
    def submit(self,ev):
        if not len(ev):return True
        with self.lock:
            if self.error:return False
            if self.bytes_pending+ev.nbytes>self.limit:
                self.error='Recording queue exceeded byte budget; event file is incomplete'
                return False
            self.bytes_pending+=ev.nbytes
        try:self.q.put_nowait(ev.copy())
        except Exception as exc:
            with self.lock:
                self.bytes_pending-=ev.nbytes
                self.error=f'Recording enqueue failed: {exc}'
            return False
        return True
    def _run(self):
        try:
            while True:
                ev=self.q.get()
                if ev is None:break
                try:
                    self.fh.write(ev.tobytes());self.count+=len(ev)
                except Exception as exc:self.error=f'Event write failed: {exc}'
                finally:
                    with self.lock:self.bytes_pending-=ev.nbytes
        finally:
            try:self.fh.close()
            except Exception as exc:self.error=f'Event close failed: {exc}'
    def close(self):
        try:self.q.put(None,timeout=2)
        except queue.Full:self.error='Recorder did not accept shutdown; completeness unknown'
        self.thread.join(timeout=10)
        if self.thread.is_alive():self.error='Recorder shutdown timed out; completeness unknown'
        return dict(events_written=self.count,recording_error=self.error)
