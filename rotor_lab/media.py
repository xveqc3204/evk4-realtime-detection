"""Bounded media writer and evidence-preserving still-image exports."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import queue
import threading
import time
import cv2
import numpy as np
from ui import polarity_image, filtered_image, CANVAS_W, CANVAS_H


class MediaWriter:
    def __init__(self,out,fps,rgb=False,max_bytes=64*1024*1024):
        self.out=Path(out);self.fps=fps;self.error=None;self.written=0;self.skipped=0
        self.pending=0;self.max_bytes=max_bytes;self.lock=threading.Lock()
        self.q=queue.Queue(maxsize=8);self.writers={};self.files={}
        self.timestamps=None;self.csv=None
        try:
            shapes={'dashboard':(CANVAS_W,CANVAS_H),'raw_events':(640,360),'filtered_events':(640,360)}
            if rgb:shapes['rgb_preview']=(640,360)
            for name,size in shapes.items():
                for ext,codec in [('mp4','mp4v'),('avi','MJPG')]:
                    path=self.out/f'{name}.{ext}'
                    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*codec),fps,size)
                    if writer.isOpened():
                        self.writers[name]=writer;self.files[name]=path.name;break
                    writer.release()
                else:raise RuntimeError(f'No video encoder for {name}; try without video')
            self.timestamps=(self.out/'video_frames.csv').open('x',newline='')
            self.csv=csv.DictWriter(self.timestamps,fieldnames=['frame_index','gui_sequence','host_unix','host_monotonic','sensor_t_us','evaluated_monotonic','status','rotor_candidate','rgb_received_monotonic','rgb_valid','rgb_age_ms'])
            self.csv.writeheader()
        except Exception:
            for w in self.writers.values():w.release()
            if self.timestamps:self.timestamps.close()
            raise
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def submit(self,images,row):
        size=sum(i.nbytes for i in images.values())
        with self.lock:
            if self.error or self.pending+size>self.max_bytes:
                self.skipped+=1;return False
            self.pending+=size
        try:self.q.put_nowait((images,dict(row),size));return True
        except queue.Full:
            with self.lock:self.pending-=size;self.skipped+=1
            return False

    def _run(self):
        try:
            while True:
                item=self.q.get()
                if item is None:break
                imgs,row,size=item
                try:
                    if not self.error:
                        for key,writer in self.writers.items():
                            writer.write(imgs[key])
                        row['frame_index']=self.written
                        self.csv.writerow(row);self.written+=1
                except Exception as exc:self.error=f'Media write failed: {exc}'
                finally:
                    with self.lock:self.pending-=size
        except Exception as exc:self.error=f'Media writer failed: {exc}'
        finally:
            for writer in self.writers.values():writer.release()
            if self.timestamps:self.timestamps.close()

    def close(self):
        try:self.q.put(None,timeout=2)
        except queue.Full:self.error='Video writer could not stop cleanly'
        self.thread.join(timeout=10)
        if self.thread.is_alive():self.error='Video writer shutdown timed out'
        result=dict(recording_starts='first fresh event preview, after compilation',files=self.files,nominal_fps=self.fps,encoded_frames=self.written,
                    dropped_gui_frames=self.skipped,error=self.error,
                    synchronization='No hardware synchronization. CSV stores host and available sensor times.',
                    image_resolution='raw/filtered 640x360 display previews; native event data in events.evs',
                    playback='Constant nominal frame rate, not a timing instrument. Use video_frames.csv for timing.',
                    codec_note='VideoWriter cannot detect every disk/codec failure. Verify files before deleting event data.')
        (self.out/'media.json').write_text(json.dumps(result,indent=2))
        return result


def save_photo(out,bundle,dashboard=None,rgb=None):
    """Save native event views and numerical frequency evidence, not a fake photograph."""
    folder=Path(out)/'photos'/str(bundle['request_id'])
    folder.mkdir(parents=True,exist_ok=False)
    snap=bundle['snapshot'];raw=bundle['raw_native'];freq=bundle['frequency_native']
    images={'raw_yellow_blue.png':polarity_image(raw),'filtered_bw.png':filtered_image(freq)}
    if dashboard is not None:images['dashboard.png']=dashboard
    if rgb is not None:images['rgb_reference.png']=rgb
    for name,image in images.items():
        if not cv2.imwrite(str(folder/name),image):raise IOError(f'Failed writing {folder/name}')
    np.savez_compressed(folder/'pixel_data.npz',raw_polarity=raw,frequency_hz=freq,
                        cycle_only_frequency_hz=bundle['cycle_only_frequency'],
                        sensor_t_us=np.int64(snap['t_us']))
    ys,xs=np.nonzero(freq)
    with (folder/'frequency_pixels.csv').open('x',newline='') as f:
        writer=csv.writer(f);writer.writerow(['sensor_t_us','x_px','y_px','optical_hz'])
        for y,x in zip(ys,xs):writer.writerow([snap['t_us'],int(x),int(y),float(freq[y,x])])
    meta={k:v for k,v in snap.items() if not isinstance(v,np.ndarray)}
    meta.update(saved_host_unix=time.time(),sensor_geometry=[raw.shape[1],raw.shape[0]],
                interpretation='Recent-event visualization; white filtered pixels passed period and spatial tests. Not a normal photograph or motor segmentation.',
                source_native_resolution=True, rgb_synchronized=False)
    (folder/'metadata.json').write_text(json.dumps(meta,indent=2))
    return folder
