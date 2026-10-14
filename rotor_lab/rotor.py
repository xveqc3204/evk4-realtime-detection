"""Interpretable per-pixel periodicity filter, not a learned drone classifier.

1. Collapse same-polarity event runs into burst onsets.
2. Measure ON-to-ON and OFF-to-OFF onset periods independently.
3. Require several consistent cycles, agreement, and a configured pass band.
4. Group the actual supported pixels spatially and require persistence.

This is a deliberately simple period estimator, not FrequencyCam's IIR
algorithm or Prophesee's proprietary implementation. See ALGORITHM.md.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
import json
import math

import numpy as np
from numba import njit

EVENT_DTYPE = np.dtype([('t', '<u8'), ('x', '<u2'), ('y', '<u2'), ('on', '?')])


@dataclass
class Settings:
    min_hz: float = 80.0
    max_hz: float = 1200.0
    cycles: int = 4
    period_tolerance: float = 0.20
    edge_guard_us: int = 40
    notches_hz: tuple = ()
    notch_width_hz: float = 5.0
    min_pixels: int = 6
    group_cell_px: int = 8
    max_regions: int = 32
    global_tile_fraction: float = 0.35
    confirm_ms: float = 60.0
    clear_ms: float = 120.0
    association_px: float = 80.0
    update_ms: float = 20.0
    view_ms: float = 33.0
    max_delay_ms: float = 40.0
    max_backlog: int = 64
    silence_ms: float = 500.0
    preview_hz: float = 20.0

    def validate(self):
        for name in ('min_hz','max_hz','period_tolerance','notch_width_hz',
                     'global_tile_fraction','confirm_ms','clear_ms','association_px',
                     'update_ms','view_ms','max_delay_ms','silence_ms','preview_hz'):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
                raise ValueError(f'{name} must be a finite number')
        if not 1 <= self.min_hz < self.max_hz <= 10000:
            raise ValueError('Require 1 <= min_hz < max_hz <= 10000')
        if not 0.01 <= self.period_tolerance <= 0.4:
            raise ValueError('period_tolerance must be between 0.01 and 0.4')
        for name, lo, hi in [('cycles',2,100),('min_pixels',2,10000),
                             ('group_cell_px',1,64),('max_regions',1,128),
                             ('edge_guard_us',0,1000),('max_backlog',1,4096)]:
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v,int) or not lo <= v <= hi:
                raise ValueError(f'{name} must be an integer between {lo} and {hi}')
        if self.edge_guard_us >= 0.25e6 / self.max_hz:
            raise ValueError('edge_guard_us is too long for the maximum frequency')
        if not 0 < self.global_tile_fraction <= 1:
            raise ValueError('global_tile_fraction must be in (0,1]')
        if not 5 <= self.update_ms <= 200 or not 5 <= self.view_ms <= 200:
            raise ValueError('update_ms and view_ms must be in [5,200]')
        if self.confirm_ms < self.update_ms or self.clear_ms < self.update_ms:
            raise ValueError('confirm_ms and clear_ms must be >= update_ms')
        if not 1 <= self.preview_hz <= 30 or not 50 <= self.silence_ms <= 5000:
            raise ValueError('Invalid preview_hz or silence_ms')
        if self.max_delay_ms <= 0 or self.association_px <= 0 or self.notch_width_hz < 0:
            raise ValueError('Delay/gate must be positive; notch width must be nonnegative')
        if not isinstance(self.notches_hz, (list, tuple)):
            raise ValueError('notches_hz must be a list')
        self.notches_hz = tuple(float(v) for v in self.notches_hz)
        if any(not math.isfinite(v) or v <= 0 for v in self.notches_hz):
            raise ValueError('Notch frequencies must be finite and positive')
        return self

    def to_dict(self):
        return asdict(self)


def load_settings(path: str | Path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError('Settings must be a JSON object')
    unknown = set(data) - {f.name for f in fields(Settings)}
    if unknown:
        raise ValueError(f'Unknown settings: {sorted(unknown)}')
    return Settings(**data).validate()


@njit(cache=True, nogil=True)
def _consume(events, width, height, roi, last_event, raw_on, last_sign,
             edge_t, onset, period, streak, expires, frequency,
             min_period, max_period, tolerance, cycles, guard_us, notches, notch_width, period_eligible):
    """One compiled loop over events. Same-polarity bursts are NOT cycles."""
    invalid = 0
    for event_index in range(len(events)):
        e = events[event_index]
        t = np.int64(e['t'])
        x, y = int(e['x']), int(e['y'])
        if x < 0 or y < 0 or x >= width or y >= height:
            invalid += 1
            continue
        k = y * width + x
        if t < last_event[k]:
            invalid += 1
            continue
        last_event[k] = t
        p = 1 if e['on'] else 0
        raw_on[k] = p
        # Optional noise prefilter applies ONLY to period measurement.
        # Raw timestamps/polarity and the original event recording are untouched.
        if len(period_eligible) and not period_eligible[event_index]:
            continue
        if x < roi[0] or y < roi[1] or x >= roi[2] or y >= roi[3]:
            continue
        # Ignore events in the same ON/OFF run; they change amplitude, not period.
        if p == last_sign[k]:
            continue
        if edge_t[k] >= 0 and t - edge_t[k] < guard_us:
            continue
        edge_t[k] = t
        last_sign[k] = p
        previous = onset[k, p]
        onset[k, p] = t
        if previous < 0:
            continue
        dt = float(t - previous)
        if dt < min_period or dt > max_period:
            streak[k, p] = 0
            period[k, p] = 0.0
            expires[k] = -1
            continue
        old = period[k, p]
        if streak[k, p] == 0 or abs(dt - old) > tolerance * old:
            period[k, p] = dt
            streak[k, p] = 1
            expires[k] = -1
        else:
            period[k, p] = 0.75 * old + 0.25 * dt
            streak[k, p] = min(1000, int(streak[k, p]) + 1)
        if streak[k, 0] < cycles or streak[k, 1] < cycles:
            continue
        a, b = period[k, 0], period[k, 1]
        mean_period = 0.5 * (a + b)
        if abs(a - b) > tolerance * mean_period:
            expires[k] = -1
            continue
        f = 1e6 / mean_period
        excluded = False
        for f0 in notches:
            if abs(f - f0) <= notch_width:
                excluded = True
                break
        if excluded:
            expires[k] = -1
            continue
        frequency[k] = f
        # Need fresh evidence: a frequency is never valid forever after a hit.
        expires[k] = t + int(min(100000.0, max(10000.0, 3.0 * mean_period)))
    return invalid


@njit(cache=True, nogil=True)
def _maps(now_t, width, height, last_event, raw_on, expires, frequency, view_us):
    """Native resolution periodic map and latest-polarity 2x raw preview.

    Pooling is only for display. Actual frequency tests are per sensor pixel.
    """
    ph, pw = (height + 1) // 2, (width + 1) // 2
    raw = np.zeros((ph, pw), np.uint8)
    newest_t = np.full((ph, pw), -1, np.int64)
    freq = np.zeros((height, width), np.float32)
    for y in range(height):
        for x in range(width):
            k = y * width + x
            age = now_t - last_event[k]
            if last_event[k] >= 0 and 0 <= age <= view_us:
                # 0 = none, 1 = OFF, 2 = ON. The latest event wins in a
                # preview cell, rather than always favoring the ON polarity.
                py, px = y // 2, x // 2
                if last_event[k] >= newest_t[py, px]:
                    raw[py, px] = 2 if raw_on[k] else 1
                    newest_t[py, px] = last_event[k]
            # Frequency validity must not depend on the viewer's trail length.
            # Its own evidence-expiry timer is authoritative.
            if last_event[k] >= 0 and now_t >= last_event[k] and expires[k] >= now_t:
                freq[y, x] = frequency[k]
    return raw, freq


@njit(cache=True, nogil=True)
def _raw_native(now_t, width, height, last_event, raw_on, view_us):
    out = np.zeros((height, width), np.uint8)
    for k in range(width * height):
        age = now_t - last_event[k]
        if last_event[k] >= 0 and 0 <= age <= view_us:
            out[k // width, k % width] = 2 if raw_on[k] else 1
    return out


class PeriodFilter:
    def __init__(self, cfg: Settings, width=1280, height=720):
        self.cfg = cfg.validate()
        self.width, self.height = int(width), int(height)
        if not 1 <= self.width <= 4096 or not 1 <= self.height <= 4096:
            raise ValueError('Unsupported sensor geometry')
        self.roi = (0, 0, self.width, self.height)
        n = self.width * self.height
        self.last_event = np.full(n, -1, np.int64)
        self.raw_on = np.zeros(n, np.uint8)
        self.last_sign = np.full(n, -1, np.int8)
        self.edge_t = np.full(n, -1, np.int64)
        self.onset = np.full((n, 2), -1, np.int64)
        self.period = np.zeros((n, 2), np.float64)
        self.streak = np.zeros((n, 2), np.uint16)
        self.expires = np.full(n, -1, np.int64)
        self.frequency = np.zeros(n, np.float32)
        self.latest_t = -1
        self.notches = np.array(cfg.notches_hz, np.float64)

    def reset(self):
        self.last_event.fill(-1)
        self.last_sign.fill(-1)
        self.edge_t.fill(-1)
        self.onset.fill(-1)
        self.period.fill(0)
        self.streak.fill(0)
        self.expires.fill(-1)
        self.frequency.fill(0)
        self.latest_t = -1

    def reset_periods(self):
        """Clear period evidence without changing the independent raw timestamps."""
        self.last_sign.fill(-1); self.edge_t.fill(-1); self.onset.fill(-1)
        self.period.fill(0); self.streak.fill(0); self.expires.fill(-1); self.frequency.fill(0)

    def set_roi(self, roi):
        x0,y0,x1,y1 = map(int, roi)
        if not 0 <= x0 < x1 <= self.width or not 0 <= y0 < y1 <= self.height:
            raise ValueError('ROI must lie within the sensor')
        self.roi = (x0,y0,x1,y1)
        self.reset()

    def compile(self):
        # Live drivers and memmaps can return readonly arrays. Canonicalize
        # that flag and warm both C-contiguous and strided layouts BEFORE USB.
        self.push(np.zeros(0, dtype=EVENT_DTYPE))
        self.push(np.zeros(4, dtype=EVENT_DTYPE)[::2])
        self.maps(0)
        self.raw_native(0)
        self.reset()

    def push(self, events, period_eligible=None):
        if events.dtype != EVENT_DTYPE or events.ndim != 1:
            raise ValueError('Expected one-dimensional structured events with fields t,x,y,on')
        # This is a zero-copy descriptor. Never change the caller's array flags.
        events = events.view()
        events.flags.writeable = False
        if len(events):
            ts = events['t']
            if int(ts.max()) > np.iinfo(np.int64).max:
                raise ValueError('Event timestamp exceeds the supported signed-microsecond range')
            if (self.latest_t >= 0 and int(ts[0]) < self.latest_t) or np.any(ts[1:] < ts[:-1]):
                raise ValueError('Event timestamps moved backwards; reset on a data discontinuity')
            self.latest_t = int(ts[-1])
        if period_eligible is None:
            period_eligible = np.zeros(0, dtype=np.bool_)
        elif period_eligible.dtype != np.bool_ or period_eligible.ndim != 1 or len(period_eligible) != len(events):
            raise ValueError('Period eligibility must be a bool mask with one value per event')
        period_eligible = np.ascontiguousarray(period_eligible)
        c = self.cfg
        return _consume(events, self.width, self.height, self.roi,
                        self.last_event, self.raw_on, self.last_sign, self.edge_t,
                        self.onset, self.period, self.streak, self.expires, self.frequency,
                        1e6 / c.max_hz, 1e6 / c.min_hz, c.period_tolerance, c.cycles,
                        c.edge_guard_us, self.notches, c.notch_width_hz, period_eligible)

    def maps(self, t_us):
        return _maps(int(t_us), self.width, self.height, self.last_event, self.raw_on,
                     self.expires, self.frequency, int(self.cfg.view_ms * 1000))


    def raw_native(self, t_us):
        return _raw_native(int(t_us), self.width, self.height, self.last_event,
                           self.raw_on, int(self.cfg.view_ms * 1000))


def group_pixels(freq, cfg: Settings, roi, return_map=False):
    """Group frequency-supported pixels. Grouping never paints extra pixels.

    Small 8-pixel cells keep connected-component processing inexpensive.
    They are NOT the frequency measurement resolution.
    """
    import cv2
    # The output map contains only actual per-pixel evidence surviving the
    # spatial/frequency test. It never fills boxes or grows measured pixels.
    supported = np.zeros_like(freq) if return_map else None
    def result(regions, status, fraction):
        base = (regions, status, fraction)
        return base + (supported,) if return_map else base
    ys,xs = np.nonzero(freq)
    if not len(xs):
        return result([], 'RUN', 0.0)
    h,w = freq.shape
    cell = cfg.group_cell_px
    gh,gw = (h+cell-1)//cell, (w+cell-1)//cell
    grid = np.zeros((gh,gw), np.uint8)
    grid[ys//cell,xs//cell] = 1
    x0,y0,x1,y1 = roi
    roi_cells = max(1, ((x1-1)//cell-x0//cell+1) * ((y1-1)//cell-y0//cell+1))
    fraction = float(grid.sum()) / roi_cells
    if fraction > cfg.global_tile_fraction:
        return result([], 'GLOBAL_PERIODIC_ACTIVITY', fraction)
    n, labels = cv2.connectedComponents(grid, connectivity=8)
    ids = labels[ys//cell, xs//cell]
    sizes = np.bincount(ids, minlength=n)
    good = np.flatnonzero(sizes >= cfg.min_pixels)
    good = good[good != 0]
    if len(good) > cfg.max_regions:
        return result([], 'TOO_MANY_REGIONS', fraction)
    regions = []
    for lab in good:
        sel = ids == lab
        xx,yy = xs[sel],ys[sel]
        ff = freq[yy,xx]
        f = float(np.median(ff))
        agree = np.abs(ff-f) <= cfg.period_tolerance * f
        if np.count_nonzero(agree) < cfg.min_pixels or agree.mean() < 0.7:
            continue
        xx,yy,ff = xx[agree],yy[agree],ff[agree]
        if supported is not None:
            supported[yy,xx] = ff
        regions.append(dict(bbox=[int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1],
                            center=[float(xx.mean()),float(yy.mean())],
                            hz=float(np.median(ff)),pixels=len(xx)))
    return result(sorted(regions,key=lambda d:d['pixels'],reverse=True), 'RUN', fraction)


class PatchTracker:
    """Small nearest-position + similar-frequency associator, no motion model.

    A track follows a periodic patch, not a whole drone. A single aircraft can
    produce several tracks. Missed tracks are explicitly marked COASTING.
    """
    def __init__(self, cfg):
        self.cfg = cfg
        self.tracks = []
        self.next_id = 1

    def reset(self):
        self.tracks.clear()  # Preserve monotonic IDs across resets within this run.

    def update(self, regions, t_us):
        c = self.cfg
        self.tracks = [tr for tr in self.tracks if t_us-tr['last_seen'] <= c.clear_ms*1000]
        pairs = []
        for i,tr in enumerate(self.tracks):
            for j,r in enumerate(regions):
                dist = math.dist(tr['center'],r['center'])
                rel = abs(tr['hz']-r['hz']) / max(tr['hz'],r['hz'])
                if dist <= c.association_px and rel <= c.period_tolerance:
                    pairs.append((dist/c.association_px+rel, i,j))
        used_t,used_r=set(),set()
        for _,i,j in sorted(pairs):
            if i in used_t or j in used_r:
                continue
            tr,r=self.tracks[i],regions[j]
            if not tr['confirmed'] and t_us-tr['last_seen'] > 1.6*c.update_ms*1000:
                tr['first_seen']=t_us
                tr['hits']=0
            tr.update(r)
            tr['last_seen']=t_us
            tr['hits']+=1
            tr['confirmed'] = bool(tr['confirmed'] or
                (tr['hits']>=3 and t_us-tr['first_seen'] >= c.confirm_ms*1000))
            used_t.add(i);used_r.add(j)
        for j,r in enumerate(regions):
            if j in used_r or len(self.tracks)>=c.max_regions:
                continue
            tr=dict(r,id=self.next_id,first_seen=t_us,last_seen=t_us,hits=1,confirmed=False)
            self.next_id+=1
            self.tracks.append(tr)
        out=[]
        for tr in self.tracks:
            d=dict(tr)
            d['age_ms']=(t_us-tr['last_seen'])/1000
            d['state']='COASTING' if d['age_ms']>0 else ('CONFIRMED_PERIODIC' if d['confirmed'] else 'PENDING')
            out.append(d)
        return out


def reduce_frequency(freq):
    """Max pool 2x for display, preserving single supported sensor pixels."""
    h,w=freq.shape
    padded=np.zeros(((h+1)//2*2,(w+1)//2*2),np.float32)
    padded[:h,:w]=freq
    return padded.reshape(padded.shape[0]//2,2,padded.shape[1]//2,2).max(axis=(1,3))
