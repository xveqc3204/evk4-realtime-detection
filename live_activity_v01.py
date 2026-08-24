import time

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
FLAG_COOLDOWN_US = 100_000


class ActivityDetector:
    def __init__(self):
        self.current_bucket = None
        self.counts = np.zeros((GRID_H, GRID_W), dtype=np.int64)
        self.warmup_sum = np.zeros((GRID_H, GRID_W), dtype=np.float64)
        self.warmup_sumsq = np.zeros((GRID_H, GRID_W), dtype=np.float64)
        self.warmup_n = 0
        self.mean = None
        self.var = None
        self.last_flag_t = -10**18

    def reset_current_window(self):
        self.current_bucket = None
        self.counts.fill(0)

    def accumulate(self, events):
        gx = events["x"].astype(np.int32) // CELL_W
        gy = events["y"].astype(np.int32) // CELL_H
        cell_index = gy * GRID_W + gx
        counts = np.bincount(cell_index, minlength=GRID_W * GRID_H)
        self.counts += counts.reshape(GRID_H, GRID_W)

    def finish_window(self, bucket):
        counts_f = self.counts.astype(np.float64)

        if self.warmup_n < WARMUP_WINDOWS:
            self.warmup_sum += counts_f
            self.warmup_sumsq += counts_f * counts_f
            self.warmup_n += 1

            if self.warmup_n % 100 == 0:
                print(f"Calibrating background: {self.warmup_n}/{WARMUP_WINDOWS}")

            if self.warmup_n == WARMUP_WINDOWS:
                self.mean = self.warmup_sum / self.warmup_n
                self.var = self.warmup_sumsq / self.warmup_n - self.mean * self.mean
                self.var = np.maximum(self.var, 1.0)
                print("\nBACKGROUND READY")
                print("Live anomaly detection running...\n")
            return

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

        current_t = (bucket + 1) * WINDOW_US

        if flag and current_t - self.last_flag_t >= FLAG_COOLDOWN_US:
            px0 = int(x0 * CELL_W)
            py0 = int(y0 * CELL_H)
            px1 = int(x1 * CELL_W)
            py1 = int(y1 * CELL_H)

            print("\n*** CANDIDATE ACTIVITY DETECTED ***")
            print(
                f"time: {current_t} us | events: {int(local_events)} | "
                f"score: {local_z:.1f}"
            )
            print(f"ROI: x={px0}:{px1}, y={py0}:{py1}")
            self.last_flag_t = current_t

        if not flag:
            delta = counts_f - self.mean
            self.mean = (1.0 - ALPHA) * self.mean + ALPHA * counts_f
            self.var = (1.0 - ALPHA) * self.var + ALPHA * delta * delta

    def push(self, events):
        if len(events) == 0:
            return

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
                self.finish_window(self.current_bucket)
                self.counts.fill(0)
                self.current_bucket += 1

            self.accumulate(segment)


def main():
    detector = ActivityDetector()
    print("Opening EVK4 v0.1 live activity detector")
    print("Keep camera still during the first ~3 seconds.\n")

    with nd.open(iterator_timeout=0.01, iterator_maximum_raw_packets=8) as device:
        print("Camera:", device.name())
        print("Serial:", device.serial())
        print("Resolution:", device.properties())
        print()

        for _, packet in device:
            if packet is not None and packet.polarity_events is not None:
                detector.push(packet.polarity_events)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
