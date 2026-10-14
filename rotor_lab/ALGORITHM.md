# Algorithm and assumptions

## Input

An event is `(timestamp_us, x, y, on)`. The driver supplies arrays in a packed 13-byte dtype. USB packet boundaries have no physical frame meaning. `PeriodFilter.push()` validates timestamp order, canonicalizes the array to a read-only zero-copy view, and calls a Numba-compiled loop. Both contiguous and strided input layouts are compiled before USB opens.

## Period measurement

`_consume()` maintains per-pixel last polarity, last edge time, last ON/OFF burst starts, period estimates, consistency counters, frequency, and an expiry time. Consecutive same-polarity events belong to one burst. Very close polarity transitions are ignored by the configurable edge guard.

The next ON burst measures an ON-to-ON period. The next OFF burst measures an OFF-to-OFF period. Intervals outside the configured range or inconsistent with recent timing reset that polarity's evidence. The default requires four consistent measured intervals per polarity and agreement between the two estimates. Accepted frequency is one million divided by the mean period in microseconds. This is an optical repetition frequency, not automatically blade-pass fundamental or motor RPM.

Fresh cycles renew an expiry deadline. Old evidence expires. The raw-view trail setting now affects visualization only and cannot change frequency acceptance.

## Spatial support

Frequency estimation remains at native pixel resolution. `group_pixels()` places supported pixels in 8-pixel grouping cells, connects occupied cells, and checks that each region has enough mutually agreeing native pixels. It does not paint the interior of a bounding box. The default needs at least six supported pixels and 70 percent frequency agreement within a connected group.

This grouping is intentionally crude. Close projected rotors can merge. Different-frequency sources in one connected group can suppress each other. Excessive global periodic support or too many regions causes an explicit non-RUN state. A software ROI changes analysis only, not USB load.

## Persistence

`PatchTracker` associates by distance and frequency. It is not a whole-object drone tracker or a calibrated motion model. The default requires at least three observations spanning 60 ms. Brief missing observations can retain an ID as COASTING, but coasting is not fresh evidence and cannot alone assert the flag.

## Application architecture

One worker owns the EVK4 and runs the estimator. The main process owns the OpenCV window. Latest-preview publication is bounded; slow previews are skipped. Event and movie writers are bounded. Overflow, stale input, timestamp regression and observed recording loss are explicit. `UNAVAILABLE` is not a negative target decision.

The core per-pixel result is packet-split invariant in tests, but whole-application decision timestamps and patch association can vary with packet delivery/evaluation scheduling during replay. Replay success is not a claim of bit-for-bit identical track timelines.

The watchdog is soft real time. Driver receive/consume delay, event-loop cost, evidence observation, confirmation and GUI age are different quantities. A small driver delay is not a complete detection-latency measurement. A timestamp-order scan is included in every packet.

## Independent synthetic model

`synthetic.py` renders a generic four-arm body with four two-blade silhouettes. It samples log-luminance contrast and emits threshold-crossing ON/OFF events. Four independent optical blade-pass frequencies, motion, projection, noise, event loss, contrast and timing jitter can be varied. It does not generate frequencies by calling the detector backward.

This renderer is a software stimulus, not an IMX636 model or a Teal digital twin. Its finite raster and 100 us time step introduce discretization. Contrast is not lux, projected pixels are not meters, random event removal is not a calibrated low-light model, and no readout arbitration or lens transfer function is simulated. Fast-crossing occupancy includes leaving the image; it is not a pure speed-limit measurement. Seed variants primarily change synthetic noise.

The exact user designation "Teal 6" has not been established from the provided materials or manufacturer source. No Teal-specific shape, blade count, frequency band or performance specification is assumed.

## Known blind spots

A periodic fan, flashing LED or periodic texture can resemble rotor evidence. A real rotor that is too small, weak, quickly translating, occluded, sparsely observed or mixed with noise may fail. Some missed-edge patterns can favor harmonics or subharmonics. Four rotor-looking clusters are not required and are not a drone identity test. This build deliberately does not add a learned classifier or claim to resolve those ambiguities.

## Technical references

These establish context, not validation of this implementation:

- Prophesee Metavision Studio temporal plot: `https://docs.prophesee.ai/stable/metavision_studio/index.html`
- Frequency Cam, Pfrommer: `https://arxiv.org/abs/2211.00198`
- EE3P, Kolar et al.: `https://arxiv.org/abs/2402.14958`
- Manufacturer Teal product page, identifying Teal 2: `https://redcat.red/solutions/teal-drones/`
