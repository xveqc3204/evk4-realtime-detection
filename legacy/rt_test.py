import time

import neuromorphic_drivers as nd

from live_activity_v01 import ActivityDetector

MAX_DELAY_MS = 20.0
MAX_BACKLOG = 64


def main():
    detector = ActivityDetector()

    print("Opening EVK4 in headless real-time mode...")
    print("Keep camera still during initial calibration.\n")

    with nd.open(
        iterator_timeout=0.01,
        iterator_maximum_raw_packets=8,
    ) as device:
        print("Camera:", device.name())
        print("Serial:", device.serial())
        print("Resolution:", device.properties())
        print()

        report_start = time.monotonic()
        total_events = 0
        dropped_backlogs = 0

        for status, packet in device:
            if status.ring is None:
                continue

            delay = status.delay()
            delay_ms = 0.0 if delay is None else delay * 1000.0
            backlog = status.ring.backlog

            if delay_ms > MAX_DELAY_MS or backlog > MAX_BACKLOG:
                print(
                    f"STALE DATA -> clearing | delay={delay_ms:.1f} ms | "
                    f"backlog={backlog}"
                )
                device.clear_backlog(until=0)
                detector.reset_current_window()
                dropped_backlogs += 1
                continue

            if packet is not None and packet.polarity_events is not None:
                events = packet.polarity_events
                total_events += len(events)
                detector.push(events)

            now = time.monotonic()
            elapsed = now - report_start

            if elapsed >= 1.0:
                rate = total_events / elapsed / 1e6
                print(
                    f"rate={rate:6.2f} Mev/s | delay={delay_ms:7.2f} ms | "
                    f"backlog={backlog:4d} | clears={dropped_backlogs}"
                )
                total_events = 0
                report_start = now


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
