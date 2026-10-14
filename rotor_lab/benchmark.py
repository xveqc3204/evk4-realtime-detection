"""Native 1280x720 CPU stress benchmark, no camera/USB, not detector latency."""
from __future__ import annotations
import json
from pathlib import Path
import time
import platform
import numpy as np
from rotor import Settings,PeriodFilter,group_pixels,EVENT_DTYPE


def main():
    rng=np.random.default_rng(991);rows=[]
    for packet_size in (1000,10000,50000,100000):
        f=PeriodFilter(Settings());f.compile();kernel=[];maps=[];total=0
        # Same total event volume, different host packet grouping.
        e=np.zeros(1000000,EVENT_DTYPE);e['t']=np.arange(len(e),dtype=np.uint64)
        e['x']=rng.integers(0,1280,len(e));e['y']=rng.integers(0,720,len(e));e['on']=rng.integers(0,2,len(e)).astype(bool)
        begin=time.perf_counter()
        for i in range(0,len(e),packet_size):
            part=e[i:i+packet_size];t=time.perf_counter();f.push(part);kernel.append((time.perf_counter()-t)*1000)
            if (i+packet_size)%50000==0:
                t=time.perf_counter();_,m=f.maps(int(part['t'][-1]));group_pixels(m,f.cfg,f.roi);maps.append((time.perf_counter()-t)*1000)
        elapsed=time.perf_counter()-begin
        rows.append(dict(packet_events=packet_size,events=len(e),kernel_p95_ms=float(np.percentile(kernel,95)),
            kernel_max_ms=max(kernel),maps_p95_ms=float(np.percentile(maps,95)),wall_s=elapsed,
            unpaced_software_mev_s=len(e)/elapsed/1e6))
    out=Path('validation');out.mkdir(exist_ok=True)
    result=dict(geometry=[1280,720],platform=platform.platform(),rows=rows,
                scope='Four million synthetic random events. No USB, no live Mac measurement, no claim of maximum sensor throughput or end-to-end latency.')
    (out/'benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
