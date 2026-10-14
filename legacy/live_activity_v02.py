import time
from collections import deque

import numpy as np
import neuromorphic_drivers as nd

WIDTH = 1280
HEIGHT = 720
WINDOW_US = 5_000
GRID_W = 32
GRID_H = 18
CELL_W = WIDTH // GRID_W
CELL_H = HEIGHT // GRID_H

WARMUP_WINDOWS = 600
ALPHA = 0.002
TILE_Z_THRESHOLD = 8.0
LOCAL_Z_THRESHOLD = 12.0
MIN_LOCAL_EVENTS = 100
MAX_ACTIVE_FRACTION = 0.25

PENDING_HISTORY = 5
REQUIRED_HITS = 3
MAX_ASSOC_DISTANCE_PX = 250.0
CLEAR_AFTER_US = 50_000
POSITION_ALPHA = 0.40
VELOCITY_ALPHA = 0.30
TRACK_REPORT_US = 100_000

MAX_DELAY_MS = 20.0
MAX_BACKLOG = 64


class ActivityDetector:
    def __init__(self):
        self.current_bucket = None
        self.counts = np.zeros((GRID_H, GRID_W), dtype=np.int64)
        self.warmup_sum = np.zeros((GRID_H, GRID_W), dtype=np.float64)
        self.warmup_sumsq = np.zeros((GRID_H, GRID_W), dtype=np.float64)
        self.warmup_n = 0
        self.mean = None
        self.var = None

    def reset_current_window(self):
        self.current_bucket = None
        self.counts.fill(0)

    def accumulate(self, events):
        gx = events["x"].astype(np.int32) // CELL_W
        gy = events["y"].astype(np.int32) // CELL_H
        cell_index = gy * GRID_W + gx
        counts = np.bincount(cell_index, minlength=GRID_W * GRID_H)
        self.counts += counts.reshape(GRID_H, GRID_W)

    def analyze_window(self, bucket):
        t_us = (bucket + 1) * WINDOW_US
        counts_f = self.counts.astype(np.float64)

        if self.warmup_n < WARMUP_WINDOWS:
            self.warmup_sum += counts_f
            self.warmup_sumsq += counts_f * counts_f
            self.warmup_n += 1

            if self.warmup_n % 100 == 0:
                print(f"Calibrating: {self.warmup_n}/{WARMUP_WINDOWS}")

            if self.warmup_n == WARMUP_WINDOWS:
                self.mean = self.warmup_sum / self.warmup_n
                self.var = self.warmup_sumsq / self.warmup_n - self.mean * self.mean
                self.var = np.maximum(self.var, 1.0)
                print("\nBACKGROUND READY")
                print("v0.2 tracking active\n")

            return t_us, None, False

        std = np.sqrt(self.var + 1.0)
        z = (counts_f - self.mean) / std

        peak_y, peak_x = np.unravel_index(np.argmax(z), z.shape)
        y0 = max(0, peak_y - 1)
        y1 = min(GRID_H, peak_y + 2)
        x0 = max(0, peak_x - 1)
        x1 = min(GRID_W, peak_x + 2)

        local_events = counts_f[y0:y1, x0:x1].sum()
        local_mean = self.mean[y0:y1, x0:x1].sum()
        local_var = self.var[y0:y1, x0:x1].sum()
        local_z = (local_events - local_mean) / np.sqrt(local_var + 1.0)

        active_tiles = z > TILE_Z_THRESHOLD
        active_fraction = np.count_nonzero(active_tiles) / active_tiles.size
        localized = active_fraction < MAX_ACTIVE_FRACTION

        flag = (
            localized
            and local_z > LOCAL_Z_THRESHOLD
            and local_events > MIN_LOCAL_EVENTS
        )

        candidate = None

        if flag:
            px0 = int(x0 * CELL_W)
            py0 = int(y0 * CELL_H)
            px1 = int(x1 * CELL_W)
            py1 = int(y1 * CELL_H)
            cx = (px0 + px1) / 2.0
            cy = (py0 + py1) / 2.0

            candidate = {
                "t_us": t_us,
                "bbox": (px0, py0, px1, py1),
                "center": (cx, cy),
                "events": int(local_events),
                "score": float(local_z),
                "active_fraction": float(active_fraction),
            }

        if candidate is None:
            delta = counts_f - self.mean
            self.mean = (1.0 - ALPHA) * self.mean + ALPHA * counts_f
            self.var = (1.0 - ALPHA) * self.var + ALPHA * delta * delta

        return t_us, candidate, True

    def push(self, events):
        results = []
        if len(events) == 0:
            return results

        bucket_ids = events["t"] // WINDOW_US
        boundaries = np.flatnonzero(bucket_ids[1:] != bucket_ids[:-1]) + 1
        starts = np.concatenate(([0], boundaries))
        ends = np.concatenate((boundaries, [len(events)]))

        for start, end in zip(starts, ends):
            segment = events[start:end]
            bucket = int(segment["t"][0] // WINDOW_US)

            if self.current_bucket is None:
                self.current_bucket = bucket

            while bucket > self.current_bucket:
                results.append(self.analyze_window(self.current_bucket))
                self.counts.fill(0)
                self.current_bucket += 1

            self.accumulate(segment)

        return results


class TargetTracker:
    def __init__(self):
        self.state = "IDLE"
        self.track_id = 0
        self.pending_history = deque(maxlen=PENDING_HISTORY)
        self.pending_center = None
        self.pending_bbox = None
        self.pending_candidate = None
        self.center = None
        self.bbox = None
        self.velocity = (0.0, 0.0)
        self.last_seen_t = None
        self.track_start_t = None
        self.last_report_t = None

    @staticmethod
    def distance(a, b):
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return float(np.sqrt(dx * dx + dy * dy))

    def reset_pending(self):
        self.pending_history.clear()
        self.pending_center = None
        self.pending_bbox = None
        self.pending_candidate = None

    def begin_pending(self, candidate):
        self.state = "PENDING"
        self.reset_pending()
        self.pending_history.append(True)
        self.pending_center = candidate["center"]
        self.pending_bbox = candidate["bbox"]
        self.pending_candidate = candidate

    def activate(self, t_us):
        self.track_id += 1
        self.state = "ACTIVE"
        self.center = self.pending_center
        self.bbox = self.pending_bbox
        self.velocity = (0.0, 0.0)
        self.last_seen_t = t_us
        self.track_start_t = t_us
        self.last_report_t = t_us
        candidate = self.pending_candidate

        print("\n================================")
        print("TARGET_ACTIVITY = 1")
        print(f"track_id: {self.track_id}")
        print(f"time: {t_us / 1e6:.6f} s")
        print(f"ROI: {self.bbox}")

        if candidate is not None:
            print(f"events: {candidate['events']}")
            print(f"activity score: {candidate['score']:.1f}")

        print("================================\n")
        self.reset_pending()

    def clear(self, t_us, reason="target_lost"):
        if self.state == "ACTIVE":
            duration_us = t_us - self.track_start_t
            print("\n================================")
            print("TARGET_ACTIVITY = 0")
            print(f"track_id: {self.track_id}")
            print(f"time: {t_us / 1e6:.6f} s")
            print(f"duration: {duration_us / 1e6:.3f} s")
            print(f"reason: {reason}")
            print("================================\n")

        self.state = "IDLE"
        self.center = None
        self.bbox = None
        self.velocity = (0.0, 0.0)
        self.last_seen_t = None
        self.track_start_t = None
        self.last_report_t = None
        self.reset_pending()

    def update_pending(self, candidate, t_us):
        if candidate is None:
            self.pending_history.append(False)
            if (
                len(self.pending_history) == PENDING_HISTORY
                and sum(self.pending_history) == 0
            ):
                self.state = "IDLE"
                self.reset_pending()
            return

        if self.pending_center is None:
            self.begin_pending(candidate)
            return

        distance = self.distance(candidate["center"], self.pending_center)

        if distance <= MAX_ASSOC_DISTANCE_PX:
            self.pending_history.append(True)
            self.pending_center = candidate["center"]
            self.pending_bbox = candidate["bbox"]
            self.pending_candidate = candidate
        else:
            self.begin_pending(candidate)

        if sum(self.pending_history) >= REQUIRED_HITS:
            self.activate(t_us)

    def update_active(self, candidate, t_us):
        if candidate is not None:
            dt = (t_us - self.last_seen_t) / 1e6

            if dt > 0:
                predicted = (
                    self.center[0] + self.velocity[0] * dt,
                    self.center[1] + self.velocity[1] * dt,
                )
            else:
                predicted = self.center

            distance = self.distance(candidate["center"], predicted)

            if distance <= MAX_ASSOC_DISTANCE_PX:
                old_center = self.center
                measured_center = candidate["center"]

                self.center = (
                    (1.0 - POSITION_ALPHA) * old_center[0]
                    + POSITION_ALPHA * measured_center[0],
                    (1.0 - POSITION_ALPHA) * old_center[1]
                    + POSITION_ALPHA * measured_center[1],
                )

                if dt > 0:
                    measured_velocity = (
                        (measured_center[0] - old_center[0]) / dt,
                        (measured_center[1] - old_center[1]) / dt,
                    )

                    self.velocity = (
                        (1.0 - VELOCITY_ALPHA) * self.velocity[0]
                        + VELOCITY_ALPHA * measured_velocity[0],
                        (1.0 - VELOCITY_ALPHA) * self.velocity[1]
                        + VELOCITY_ALPHA * measured_velocity[1],
                    )

                self.bbox = candidate["bbox"]
                self.last_seen_t = t_us

        if t_us - self.last_seen_t > CLEAR_AFTER_US:
            self.clear(t_us, reason="no_associated_activity")
            return

        if t_us - self.last_report_t >= TRACK_REPORT_US:
            print(
                f"TRACK {self.track_id} | t={t_us / 1e6:.3f}s | "
                f"center=({self.center[0]:.0f},{self.center[1]:.0f}) | "
                f"velocity=({self.velocity[0]:.0f},{self.velocity[1]:.0f}) px/s"
            )
            self.last_report_t = t_us

    def update(self, candidate, t_us):
        if self.state == "IDLE":
            if candidate is not None:
                self.begin_pending(candidate)
            return

        if self.state == "PENDING":
            self.update_pending(candidate, t_us)
            return

        if self.state == "ACTIVE":
            self.update_active(candidate, t_us)


def main():
    detector = ActivityDetector()
    tracker = TargetTracker()

    print("\nOpening EVK4 - Version 0.2")
    print("Headless live activity tracking\n")

    with nd.open(
        iterator_timeout=0.01,
        iterator_maximum_raw_packets=8,
    ) as device:
        print("Camera:", device.name())
        print("Serial:", device.serial())
        print("Resolution:", device.properties())
        print("\nKEEP CAMERA STILL DURING INITIAL CALIBRATION\n")

        report_start = time.monotonic()
        total_events = 0
        clears = 0

        for status, packet in device:
            if status.ring is None:
                continue

            delay = status.delay()
            delay_ms = 0.0 if delay is None else delay * 1000.0
            backlog = status.ring.backlog
            current_t = status.ring.current_t

            if delay_ms > MAX_DELAY_MS or backlog > MAX_BACKLOG:
                print(
                    "STALE DATA -> CLEARING | "
                    f"delay={delay_ms:.1f} ms | backlog={backlog}"
                )
                device.clear_backlog(until=0)
                detector.reset_current_window()

                if current_t is not None:
                    tracker.clear(current_t, reason="backlog_clear")

                clears += 1
                continue

            if packet is not None and packet.polarity_events is not None:
                events = packet.polarity_events
                total_events += len(events)
                results = detector.push(events)

                for t_us, candidate, ready in results:
                    if ready:
                        tracker.update(candidate, t_us)

            now = time.monotonic()
            elapsed = now - report_start

            if elapsed >= 1.0:
                rate = total_events / elapsed / 1e6
                print(
                    f"HEALTH | rate={rate:5.2f} Mev/s | "
                    f"delay={delay_ms:6.2f} ms | backlog={backlog:3d} | "
                    f"clears={clears} | state={tracker.state}"
                )
                total_events = 0
                report_start = now


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
