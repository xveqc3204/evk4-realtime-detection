"""Raw EVK4 focus preview. No detector, recorder, dataset, log file or disk cache.

Importing this module uses only the standard library. The child imports NumPy,
OpenCV and the installed camera driver on demand. Never use this preview for
experimental measurements: its 33 ms display history is a focusing aid only.
"""
from __future__ import annotations

from collections import deque
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

TITLE = 'EBS Focus camera | RAW ONLY | NOT RECORDING'
VIEW_US = 33_000
YELLOW = (50, 210, 255)  # Existing dashboard's BGR convention.
BLUE = (255, 145, 45)


class FocusSession:
    """One no-file preview process; parent pipe EOF also requests camera release."""
    def __init__(self):
        self.proc = None
        self.closing = False
        self._errors = deque(maxlen=8)
        self._reader = None

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, python: Path):
        if self.running:
            raise RuntimeError('Finish the current focus preview first.')
        self.collect_exit()
        self._errors.clear()
        self.closing = False
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        self.proc = subprocess.Popen(
            [str(python), '-B', str(Path(__file__).resolve()), '--live'],
            cwd=str(Path(__file__).resolve().parent), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        # Drain diagnostics in memory. No pipe can block due to unread output.
        stream = self.proc.stderr
        def drain():
            try:
                for line in stream:
                    if line.strip():
                        self._errors.append(line.strip()[:2000])
            finally:
                stream.close()
        self._reader = threading.Thread(target=drain, daemon=True,
                                        name='EBS focus diagnostics')
        self._reader.start()

    def stop(self):
        if not self.running or self.closing:
            return
        self.closing = True
        try:
            self.proc.stdin.write('stop\n')
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass  # Poll will collect the already-ending child.

    def collect_exit(self):
        """None while running, otherwise (exit_code, bounded diagnostic text)."""
        if self.proc is None or self.proc.poll() is None:
            return None
        rc = self.proc.returncode
        if self._reader is not None:
            self._reader.join(timeout=0.05)
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        self.proc = None
        self.closing = False
        return rc, '\n'.join(self._errors)


class RawView:
    """Last ON/OFF timestamp per native sensor pixel. No periodicity filtering."""
    def __init__(self, width: int, height: int):
        import numpy as np
        if not (1 <= width <= 4096 and 1 <= height <= 4096):
            raise ValueError('Unsupported camera dimensions.')
        self.np = np
        self.width, self.height = int(width), int(height)
        self.on = np.full(width * height, -1, dtype=np.int64)
        self.off = np.full(width * height, -1, dtype=np.int64)
        self.latest = -1

    def clear(self):
        self.on.fill(-1)
        self.off.fill(-1)
        self.latest = -1

    def push(self, events):
        if events is None or not len(events):
            return 0
        np = self.np
        if not {'t', 'x', 'y', 'on'}.issubset(events.dtype.names or ()):
            raise ValueError('Expected camera event fields: t, x, y, on.')
        t = events['t'].astype(np.int64, copy=False)
        x = events['x'].astype(np.int64, copy=False)
        y = events['y'].astype(np.int64, copy=False)
        p = events['on'].astype(bool, copy=False)
        valid = (x >= 0) & (x < self.width) & (y >= 0) & (y < self.height) & (t >= 0)
        if not valid.any():
            return 0
        t, x, y, p = t[valid], x[valid], y[valid], p[valid]
        end = int(t.max())
        if self.latest >= 0 and end < self.latest:
            self.clear()  # Never retain future-dated pixels after a clock reset.
        indexes = y * self.width + x
        # Unbuffered maximum handles repeated coordinates in a packet correctly.
        np.maximum.at(self.on, indexes[p], t[p])
        np.maximum.at(self.off, indexes[~p], t[~p])
        self.latest = max(self.latest, end)
        return len(t)

    def image(self, now_us: int):
        np = self.np
        last = np.maximum(self.on, self.off)
        age = int(now_us) - last
        alive = (last >= 0) & (age >= 0) & (age <= VIEW_US)
        # Simultaneous opposite-polarity timestamps render ON. Display only.
        is_on = self.on >= self.off
        out = np.zeros((self.height * self.width, 3), dtype=np.uint8)
        out[alive & is_on] = YELLOW
        out[alive & ~is_on] = BLUE
        return out.reshape(self.height, self.width, 3)


def run_preview(stop_event, *, driver=None, cv=None):
    """Default EVK4 configuration, same iterator options as event_io.LiveSource.

    No sensor-bias writes, acquisition-recording modules, or filename arguments.
    Queued preview packets may be cleared to remain current. No scientific data
    is being retained. A later recording opens its own fresh driver session.
    """
    if driver is None:
        import neuromorphic_drivers as driver
    if cv is None:
        import cv2 as cv
    import numpy as np

    window_open = False
    last_draw = 0.0
    advanced_at = time.monotonic()
    watermark = -1
    recent_notice_until = 0.0
    try:
        with driver.open(iterator_timeout=0.01, iterator_maximum_raw_packets=8) as device:
            props = device.properties()
            view = RawView(int(props.width), int(props.height))
            if stop_event.is_set():
                return
            cv.namedWindow(TITLE, cv.WINDOW_NORMAL)
            window_open = True
            cv.resizeWindow(TITLE, 1000, 630)
            for status, packet in device:
                now = time.monotonic()
                if stop_event.is_set():
                    break
                ring = status.ring
                delay = status.delay() if ring is not None else None
                backlog = int(ring.backlog) if ring is not None else 0
                if (delay is not None and float(delay) > 0.15) or backlog > 64:
                    device.clear_backlog(until=0)
                    view.clear()
                    watermark = -1
                    advanced_at = now
                    recent_notice_until = now + 0.75
                else:
                    events = None if packet is None else packet.polarity_events
                    view.push(events)
                    tick = None if ring is None else ring.current_t
                    current = max(view.latest, -1 if tick is None else int(tick))
                    if current >= 0 and current != watermark:
                        if watermark >= 0 and current < watermark:
                            view.clear()
                        watermark, advanced_at = current, now
                if now - last_draw >= 1 / 25:
                    # Host advancement only fades idle display; never recorded or
                    # used for detection, frequency estimation or measurements.
                    display_t = watermark + int((now - advanced_at) * 1_000_000)
                    raw = view.image(display_t)
                    canvas = np.zeros((view.height + 78, view.width, 3), dtype=np.uint8)
                    canvas[48:48 + view.height] = raw
                    label = 'FOCUS ONLY - NOT RECORDING | ON yellow / OFF blue'
                    cv.putText(canvas, label, (12, 28), cv.FONT_HERSHEY_SIMPLEX,
                               .60, (235, 235, 235), 1, cv.LINE_AA)
                    guidance = 'Turn the lens focus ring. Q / Esc / close window = finish.'
                    if now < recent_notice_until:
                        guidance = 'Preview catching up. No data is being saved.'
                    elif watermark < 0 or now - advanced_at > 0.5:
                        guidance = 'No recent events. Gently move a target; check the lens cap / connection.'
                    cv.putText(canvas, guidance, (12, view.height + 68),
                               cv.FONT_HERSHEY_SIMPLEX, .48, (200, 200, 200), 1, cv.LINE_AA)
                    cv.imshow(TITLE, canvas)
                    last_draw = now
                key = cv.waitKey(1) & 0xff
                if key in (ord('q'), ord('Q'), 27):
                    break
                try:
                    if cv.getWindowProperty(TITLE, cv.WND_PROP_VISIBLE) < 1:
                        break
                except cv.error:
                    break
    finally:
        if window_open:
            cv.destroyAllWindows()


def main():
    # Stop is an in-memory pipe message. EOF handles a closed/crashed controller.
    stop_event = threading.Event()
    def read_stop():
        try:
            sys.stdin.readline()
        finally:
            stop_event.set()
    threading.Thread(target=read_stop, daemon=True, name='EBS focus stop').start()
    try:
        run_preview(stop_event)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'Focus preview could not run: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
