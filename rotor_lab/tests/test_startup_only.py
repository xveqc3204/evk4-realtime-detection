"""Software-only startup-order regression tests. No physical EVK4 required."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import queue
import tempfile
import threading
import time as real_time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import app
from event_io import Packet
from rotor import EVENT_DTYPE, PeriodFilter, Settings


class Clock:
    def __init__(self):
        self.now = 1000.0
    def monotonic(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


class TestSource:
    def __init__(self, clock, order, delay=None, overflow=False, backlog=0,
                 mismatch=False, fail_open=False):
        self.clock, self.order = clock, order
        self.width, self.height = 32, 24
        self.delay, self.overflow, self.backlog = delay, overflow, backlog
        self.mismatch, self.fail_open = mismatch, fail_open
        self.clears = 0
        self.info = dict(source='mock_camera', width=32, height=24)
    def __enter__(self):
        self.order.append('camera_open')
        if self.fail_open:
            raise RuntimeError('injected no device found')
        self.opened = self.clock.monotonic()
        if self.mismatch:
            self.width = 64
        return self
    def __exit__(self, *args):
        return False
    def clear(self):
        self.clears += 1
    def __iter__(self):
        ev = np.array([(1000, 10, 10, True)], dtype=EVENT_DTYPE)
        age = (self.clock.monotonic() - self.opened) * 1000
        yield Packet(ev, 1000, age if self.delay is None else self.delay,
                     self.backlog, self.overflow)


def run_software_case(module=app, **source_options):
    order = []
    clock = Clock()
    source = TestSource(clock, order, **source_options)
    def host_inspection():
        order.append('host_inspection')
        clock.advance(.075)  # deterministic 75 ms metadata stall, not a benchmark
        return 'SOFTWARE_TEST'
    def version_lookup(name):
        order.append('version_lookup')
        return 'SOFTWARE_TEST'
    def make_filter(cfg, width=1280, height=720):
        obj = PeriodFilter(cfg, width, height)
        if (width,height) != (2,2):
            order.append('allocate_filter')
            original_compile = obj.compile
            def compiled():
                order.append('compile_full_filter')
                return original_compile()
            obj.compile = compiled
        return obj
    with tempfile.TemporaryDirectory() as d:
        options = dict(demo=False, replay=None, duration=0, record=True,
                       video=False, run_dir=d, notes='MOCK INPUT, NOT REAL CAMERA',
                       roi=None, distance_test=True, test_box=None)
        clock_api = SimpleNamespace(monotonic=clock.monotonic,
                                    perf_counter=real_time.perf_counter,
                                    time=real_time.time)
        with patch.object(module, 'time', clock_api), \
             patch.object(module, 'LiveSource', return_value=source), \
             patch.object(module, 'PeriodFilter', side_effect=make_filter), \
             patch.object(module.platform, 'platform', side_effect=host_inspection), \
             patch.object(module.importlib.metadata, 'version', side_effect=version_lookup), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            module.worker(options, Settings().to_dict(), queue.Queue(2),
                          queue.Queue(8), threading.Event())
        root = Path(d)
        summary = json.loads((root/'summary.json').read_text())
        rows = [json.loads(line) for line in (root/'telemetry.jsonl').read_text().splitlines()]
        session = json.loads((root/'session.json').read_text()) if (root/'session.json').exists() else None
    return source, summary, rows, session, order


class StartupOrderTests(unittest.TestCase):
    def test_host_inspection_happens_before_open(self):
        _, s, _, _, order = run_software_case()
        self.assertLess(order.index('host_inspection'), order.index('camera_open'))
        self.assertLess(max(i for i,x in enumerate(order) if x=='version_lookup'), order.index('camera_open'))
        self.assertNotEqual(s['status'], 'ERROR')

    def test_full_filter_allocated_and_warmed_before_open(self):
        _, _, _, _, order = run_software_case()
        self.assertLess(order.index('allocate_filter'), order.index('camera_open'))
        self.assertLess(order.index('compile_full_filter'), order.index('camera_open'))

    def test_preopen_metadata_stall_does_not_make_first_packet_stale(self):
        source, s, rows, _, _ = run_software_case()
        self.assertEqual(next(r for r in rows if r['type']=='first_packet')['delay_ms'], 0)
        self.assertEqual(source.clears, 0)
        self.assertFalse(s['observed_input_loss'])
        self.assertTrue(s['no_observed_recording_loss'])
        self.assertEqual(s['events_written'], 1)

    def test_real_first_packet_delay_is_still_flagged(self):
        source, s, rows, _, _ = run_software_case(delay=45.24)
        self.assertEqual(source.clears, 1)
        self.assertTrue(s['observed_input_loss'])
        self.assertFalse(s['no_observed_recording_loss'])
        gap = next(row for row in rows if row['type']=='input_gap')
        self.assertEqual(gap['packet_index'], 1)
        self.assertEqual(gap['delay_ms'], 45.24)
        self.assertEqual(Settings().max_delay_ms, 40)

    def test_first_packet_overflow_is_not_excused_as_startup(self):
        source, s, _, _, _ = run_software_case(overflow=True)
        self.assertEqual(source.clears, 1)
        self.assertEqual(s['overflow_packets'], 1)
        self.assertTrue(s['observed_input_loss'])

    def test_first_packet_backlog_is_not_excused_as_startup(self):
        source, s, _, _, _ = run_software_case(backlog=65)
        self.assertEqual(source.clears, 1)
        self.assertTrue(s['observed_input_loss'])

    def test_inconsistent_geometry_fails_instead_of_reallocating_after_open(self):
        _, s, _, _, _ = run_software_case(mismatch=True)
        self.assertEqual(s['status'], 'ERROR')
        self.assertIn('geometry', s['error'])
        self.assertEqual(s['events_received'], 0)

    def test_missing_camera_remains_error(self):
        _, s, _, _, _ = run_software_case(fail_open=True)
        self.assertEqual(s['status'], 'ERROR')
        self.assertIn('no device found', s['error'])
        self.assertFalse(s['no_observed_recording_loss'])

    def test_settings_preserved_and_patch_identified(self):
        _, _, _, session, _ = run_software_case()
        self.assertEqual(session['settings'], json.loads(json.dumps(Settings().to_dict())))
        self.assertEqual(session['startup_patch'], 'v03-init-order-only')
        self.assertNotIn('paired_measurement_box', session)

