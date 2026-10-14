import time

import neuromorphic_drivers as nd


def main():
    nd.print_device_list()

    with nd.open() as device:
        print("\nCamera opened")
        print("Name:", device.name())
        print("Serial:", device.serial())
        print("Properties:", device.properties())
        print("\nMove your hand in front of the camera. Ctrl+C to stop.\n")

        start = time.time()
        total = 0

        for _, packet in device:
            if packet is not None and packet.polarity_events is not None:
                total += len(packet.polarity_events)

            if time.time() - start >= 1.0:
                print(f"{total:,} events/sec")
                total = 0
                start = time.time()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
