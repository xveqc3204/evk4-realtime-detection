"""EBS experiment recording control. Runs the existing camera application unchanged.

This file only starts/stops the existing app.py process and manages run metadata.
It does not decode events, calculate flags, alter the GUI renderer, or change
sensor settings. Launch with Start EBS Tests.command on macOS or Start EBS Tests.bat on Windows.
"""
from __future__ import annotations

import csv
import queue
import threading
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
INDEX_COLUMNS = [
    'run_id', 'start_local', 'end_local', 'environment', 'lens_mm', 'range_m',
    'focus_m', 'f_number', 'illuminance_lux', 'lighting', 'aspect', 'profile',
    'repeat', 'requested_duration_s', 'operator_notes', 'folder',
    'recording_status', 'events_written', 'observed_input_loss',
    'source_clears', 'recording_error', 'dashboard', 'raw_events',
    'filtered_events', 'original_events', 'review_notes',
]


def clean_name(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '_', value).strip('_')[:45] or 'unspecified'


def current_local_time() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def optional_positive(label: str, raw: str):
    if raw.strip() == '':
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f'{label} must be a number or blank.') from exc
    if not (0 < value < 1_000_000):
        raise ValueError(f'{label} must be positive and finite.')
    return value


def metadata_from_form(form: dict) -> dict:
    """Validate labels only. No values here affect the detector."""
    if form.get('environment') not in ('Indoor', 'Outdoor'):
        raise ValueError('Choose Indoor or Outdoor.')
    if form.get('aspect') not in ('front', 'oblique', 'side', 'rear'):
        raise ValueError('Choose a valid target aspect.')
    if form.get('profile') not in ('hover', 'crossing'):
        raise ValueError('Choose Hover or Crossing.')
    lens = optional_positive('Lens (mm)', form.get('lens_mm', ''))
    rng = optional_positive('Range (m)', form.get('range_m', ''))
    if lens is None or rng is None:
        raise ValueError('Lens and measured range are required.')
    focus = optional_positive('Focus (m)', form.get('focus_m', ''))
    aperture = optional_positive('Aperture f-number', form.get('f_number', ''))
    lux = optional_positive('Lux', form.get('illuminance_lux', ''))
    try:
        repeat = int(form.get('repeat', '1'))
    except ValueError as exc:
        raise ValueError('Repeat must be a whole number.') from exc
    if not (1 <= repeat <= 10000):
        raise ValueError('Repeat must be between 1 and 10000.')
    try:
        duration = int(form.get('duration', '60'))
    except ValueError as exc:
        raise ValueError('Duration must be whole seconds.') from exc
    if not (0 <= duration <= 86400):
        raise ValueError('Duration must be 0 to 86400 seconds. 0 means manual stop.')
    return {
        'environment': form['environment'],
        'lens_mm': lens, 'range_m': rng, 'focus_m': focus,
        'f_number': aperture, 'illuminance_lux': lux,
        'lighting': form.get('lighting', '').strip()[:300],
        'aspect': form['aspect'], 'profile': form['profile'],
        'repeat': repeat, 'requested_duration_s': duration,
        'operator_notes': form.get('notes', '').strip()[:2000],
        'activity_preset': 'sensitive', 'period_input': 'native',
        'analysis_configuration': 'Unmodified rotor_lab/settings.json and activity_presets.json',
        'sensor_timestamp_unit': 'microseconds',
        'target_identification': 'Unverified. Review target-associated evidence separately.',
        'original_event_format': 'EVK4DET1 (decoded event records)',
        'source': 'live',
    }


def unique_run_id(meta: dict, now: datetime | None = None, nonce: str | None = None) -> str:
    now = now or datetime.now().astimezone()
    tag = nonce or uuid.uuid4().hex[:6]
    lens = ('%g' % meta['lens_mm']).replace('.', 'p')
    dist = ('%g' % meta['range_m']).replace('.', 'p')
    return (now.strftime('%Y%m%d_%H%M%S') +
            f"__{meta['environment'].upper()}__L{lens}__R{dist}__{meta['aspect']}__{meta['profile']}__REP{meta['repeat']}__{tag}")


def recording_command(python: Path, run: Path, meta: dict, *, demo: bool = False) -> list[str]:
    """Use existing record/live flags and source implementation unchanged."""
    duration = meta['requested_duration_s']
    # Existing app.py defaults record duration=60 if passed zero. Live mode with
    # both recording flags is the existing supported unlimited alternative.
    args = [str(python), str(ROOT / 'app.py')]
    args += ['record', '--duration', str(duration)] if duration else ['live', '--record', '--video']
    args += [
        '--activity-preset', 'sensitive',
        '--period-input', 'native',
        '--config', str(ROOT / 'settings.json'),
        '--activity-config', str(ROOT / 'activity_presets.json'),
        '--photos-every', '5',
        '--run-dir', str(run),
        '--notes', json.dumps(meta, sort_keys=True),
    ]
    if demo:
        args += ['--demo', '--no-window', '--scenario', 'periodic']
    return args


def discover_camera_python() -> Path | None:
    choices = [os.environ.get('EVK4_PYTHON'),
        str(ROOT / '.venv/Scripts/python.exe'), str(REPO / '.venv/Scripts/python.exe'),
        str(ROOT / '.venv/bin/python'), str(REPO / '.venv/bin/python'),
        sys.executable,
        str(Path.home() / 'Downloads/evk4_sep15_baseline/.venv/bin/python'),
        str(Path.home() / 'Downloads/evk4_rotor_lab_v03/.venv/bin/python'),
        str(Path.home() / 'Downloads/evk4_distance_test/.venv/bin/python'),
        str(Path.home() / 'Downloads/evk4_rotor_lab_v05/.venv/bin/python')]
    for candidate in choices:
        if not candidate:
            continue
        exe = Path(candidate).expanduser()
        if not exe.is_file() or not os.access(exe, os.X_OK):
            continue
        try:
            checked = subprocess.run([str(exe), '-c',
                'import numpy, numba, cv2, matplotlib, neuromorphic_drivers'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=18, check=False)
            if checked.returncode == 0:
                return exe
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return {}


def run_integrity(run: Path) -> dict:
    summary = load_json(run / 'summary.json')
    app = load_json(run / 'application_summary.json')
    media = load_json(run / 'media.json')
    if not summary:
        label = 'NO_SUMMARY'
    elif summary.get('status') == 'ERROR' or summary.get('recording_error') or app.get('error') or app.get('photo_error') or media.get('error') or (run / 'FORCED_STOP.txt').exists():
        label = 'ERROR'
    elif summary.get('observed_input_loss') or not summary.get('no_observed_recording_loss'):
        label = 'DATA_GAP'
    elif not (run / 'events.evs').is_file():
        label = 'NO_EVENTS'
    elif any(not any((run / (stem + suffix)).is_file() for suffix in ('.mp4', '.avi'))
             for stem in ('dashboard', 'raw_events', 'filtered_events')):
        label = 'VIDEO_MISSING'
    else:
        label = 'RECORDED_UNREVIEWED'
    return {'recording_status': label,
            'events_written': summary.get('events_written', ''),
            'observed_input_loss': summary.get('observed_input_loss', ''),
            'source_clears': summary.get('source_clears', ''),
            'recording_error': summary.get('recording_error') or app.get('error') or media.get('error') or '',
            'dashboard': next((n for n in ('dashboard.mp4', 'dashboard.avi') if (run / n).is_file()), ''),
            'raw_events': next((n for n in ('raw_events.mp4', 'raw_events.avi') if (run / n).is_file()), ''),
            'filtered_events': next((n for n in ('filtered_events.mp4', 'filtered_events.avi') if (run / n).is_file()), ''),
            'original_events': 'events.evs' if (run / 'events.evs').is_file() else '',
            'media_warnings': media.get('error', ''),
            }


def atomic_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2) + '\n')
    tmp.replace(path)


def make_dataset_root(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'Tests').mkdir(exist_ok=True)
    (dest / 'Documents').mkdir(exist_ok=True)
    readme = dest / 'README.txt'
    if not readme.exists():
        readme.write_text(
            'EBS field test dataset\n\n'
            'Tests/ contains one original application recording per time-stamped folder.\n'
            'Each take keeps original decoded events, three videos (when available), photos,\n'
            'timestamps, detection telemetry, cues, settings and trial.json.\n'
            'INDEX.csv lists tests and recording quality; it is not a detection accuracy score.\n'
            'Documents/ is for explicitly selected supplemental reports.\n'
            'This application does not identify drones conclusively.\n'
            'A no-data/invalid recording is not a negative detection.\n')


def refresh_index(dataset: Path) -> None:
    """Scan only test folders. Preserve original files and record notes."""
    rows = []
    for trial_path in sorted((dataset / 'Tests').glob('*/trial.json')):
        run = trial_path.parent
        meta = load_json(trial_path)
        row = {k: '' for k in INDEX_COLUMNS}
        row.update({k: meta.get(k, '') for k in INDEX_COLUMNS})
        row['run_id'] = run.name
        row['folder'] = 'Tests/' + run.name
        row.update({k: v for k, v in run_integrity(run).items() if k in INDEX_COLUMNS})
        rows.append(row)
    p = dataset / 'INDEX.csv'
    tmp = dataset / 'INDEX.csv.tmp'
    with tmp.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(p)


def finalize_trial(dataset: Path, run: Path, meta: dict, exit_code: int | None,
                   stop_requested: bool, review_notes: str = '',
                   operator_log: Path | None = None) -> dict:
    if not run.is_dir():
        return {'recording_status': 'NOT_CREATED', 'recording_error': 'Application did not create run directory.'}
    if operator_log is not None and operator_log.is_file():
        log_target = run / 'operator.log'
        if not log_target.exists():
            shutil.move(str(operator_log), str(log_target))
    quality = run_integrity(run)
    result = dict(meta, run_id=run.name,
                  end_local=current_local_time(), exit_code=exit_code,
                  stop_requested_from_gui=bool(stop_requested),
                  review_notes=review_notes[:2000], **quality)
    atomic_json(run / 'trial.json', result)
    refresh_index(dataset)
    return result


def request_graceful_stop(proc: subprocess.Popen) -> bool:
    if proc.poll() is not None:
        return False
    proc.send_signal(signal.SIGINT)
    return True


def parse_evk4_usb_listing(text: str) -> bool:
    """Recognize USB enumeration, not a driver-open or working-stream guarantee."""
    return bool(re.search(r"(?im)^\s*EVK4\s*:", text) or
                ("EVK4" in text and "Prophesee" in text))


def inspect_usb_connection(*, platform_name: str | None = None, runner=None,
                           camera_python: Path | None = None) -> tuple[str, str]:
    """Idle device discovery only. This does not open the EVK4 event stream.

    macOS: system USB listing. Windows: installed neuromorphic_drivers listing.
    A positive result does not establish that recording works. No probes run
    while an acquisition is in progress.
    """
    platform_name = sys.platform if platform_name is None else platform_name
    runner = runner or subprocess.run
    if platform_name == 'win32':
        if camera_python is None:
            return 'unavailable', 'Find the recording Python environment first.'
        try:
            res = runner([str(camera_python), '-c',
                          'import neuromorphic_drivers as nd; nd.print_device_list()'],
                         capture_output=True, text=True, timeout=12, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 'unavailable', f'Windows EVK4 discovery unavailable: {type(exc).__name__}'
        if res.returncode != 0:
            return 'unavailable', 'Device driver discovery failed; check USB driver in Device Manager.'
        if 'Prophesee EVK4' in res.stdout or 'PROPHESEE_EVK4' in res.stdout:
            return 'connected', 'EVK4 found through the Python camera driver.'
        return 'disconnected', 'EVK4 not found by driver. Check USB connection and Windows driver.'
    if platform_name != 'darwin':
        return 'unavailable', 'USB status is supported on macOS and Windows only.'
    try:
        result = runner(['system_profiler', 'SPUSBDataType'],
                        capture_output=True, text=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 'unavailable', f'USB check unavailable: {type(exc).__name__}'
    if result.returncode != 0:
        return 'unavailable', f'USB check returned code {result.returncode}'
    if parse_evk4_usb_listing(result.stdout):
        return 'connected', 'EVK4 found on USB. Driver access is checked when a recording starts.'
    return 'disconnected', 'No EVK4 reported by macOS USB. Plug it in and click Refresh.'



def run_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    # Device and Python checks happen on an idle background thread. GUI opens offline.
    camera_py = None
    probe_queue = queue.Queue()
    probe = {"busy": False, "checked_python": False, "usb_kind": "checking", "next_at": 0.0}
    ui = tk.Tk()
    ui.title('EBS Field Tests | Recording Control')
    ui.geometry('850x790')
    ui.minsize(760, 695)
    ui.option_add('*Font', 'Helvetica 12')
    styles = ttk.Style(ui)
    if 'clam' in styles.theme_names():
        styles.theme_use('clam')

    today = datetime.now().strftime('%Y-%m-%d')
    dataset = tk.StringVar(value=str(Path.home() / 'Downloads' / f'EBS_Field_Data_{today}'))
    form = {
        'environment': tk.StringVar(value='Indoor'),
        'lens_mm': tk.StringVar(value='75'),
        'range_m': tk.StringVar(value='20'),
        'focus_m': tk.StringVar(value='20'),
        'f_number': tk.StringVar(),
        'illuminance_lux': tk.StringVar(),
        'lighting': tk.StringVar(value=''),
        'aspect': tk.StringVar(value='front'),
        'profile': tk.StringVar(value='hover'),
        'repeat': tk.StringVar(value='1'),
        'duration': tk.StringVar(value='60'),
    }
    status = tk.StringVar(value='OFFLINE | GUI ready. Connect EVK4 before recording.')
    usb_status = tk.StringVar(value='Camera USB: Checking...')
    python_status = tk.StringVar(value='Recording software: Checking...')
    last_run_label = tk.StringVar(value='No recording this session')
    runtime = {'proc': None, 'run': None, 'meta': None, 'log': None,
               'started': None, 'stop_requested': False, 'finalized': False, 'dataset': None}

    outer = ttk.Frame(ui, padding=10)
    outer.pack(fill='both', expand=True)
    ttk.Label(outer, text='EBS | Field recording', font=('Helvetica', 17, 'bold')).pack(anchor='w')
    ttk.Label(outer, text='Unchanged detection, frequency filter, recording format and data pipeline.').pack(anchor='w', pady=(1, 7))
    connection_row = ttk.Frame(outer, padding=(3, 4))
    connection_row.pack(fill='x')
    connection_details = ttk.Frame(connection_row)
    connection_details.pack(side='left', expand=True, fill='x')
    ttk.Label(connection_details, textvariable=usb_status).pack(anchor='w')
    ttk.Label(connection_details, textvariable=python_status).pack(anchor='w')
    ttk.Label(outer, text='USB detected means physically connected, not verified camera acquisition.').pack(anchor='w', pady=(0, 4))

    destrow = ttk.Frame(outer)
    destrow.pack(fill='x')
    ttk.Label(destrow, text='Local dataset folder').pack(anchor='w')
    destcontrol = ttk.Frame(destrow)
    destcontrol.pack(fill='x', pady=(2, 6))
    ttk.Entry(destcontrol, textvariable=dataset).pack(side='left', expand=True, fill='x')
    def choose_folder():
        p = filedialog.askdirectory(initialdir=str(Path.home() / 'Downloads'))
        if p: dataset.set(p)
    ttk.Button(destcontrol, text='Choose', command=choose_folder).pack(side='left', padx=(8, 0))

    fields = ttk.LabelFrame(outer, text='1. Test conditions (recorded as metadata)', padding=6)
    fields.pack(fill='x', pady=4)
    values = [
        ('Environment', 'environment', ('Indoor', 'Outdoor')),
        ('Lens (mm)', 'lens_mm', None),
        ('Range (m)', 'range_m', None),
        ('Focus (m)', 'focus_m', None),
        ('Aperture f/', 'f_number', None),
        ('Illuminance (lux)', 'illuminance_lux', None),
        ('Light source / conditions', 'lighting', None),
        ('Aspect', 'aspect', ('front', 'oblique', 'side', 'rear')),
        ('Target motion', 'profile', ('hover', 'crossing')),
        ('Repeat', 'repeat', None),
        ('Duration (s; 0=manual)', 'duration', None),
    ]
    for i, (label, key, opts) in enumerate(values):
        row, col = divmod(i, 2)
        cell = ttk.Frame(fields, padding=(2, 4))
        cell.grid(row=row, column=col, sticky='ew', padx=3)
        ttk.Label(cell, text=label, width=22).pack(side='left')
        if opts:
            ttk.Combobox(cell, textvariable=form[key], values=opts, state='readonly').pack(side='left', fill='x', expand=True)
        else:
            ttk.Entry(cell, textvariable=form[key]).pack(side='left', fill='x', expand=True)
    fields.columnconfigure(0, weight=1)
    fields.columnconfigure(1, weight=1)
    ttk.Label(outer, text='Notes / measured setup changes').pack(anchor='w', pady=(4, 0))
    notes = tk.Text(outer, height=2, wrap='word')
    notes.pack(fill='x')
    fixed = ttk.Label(outer, text='Fixed processing: sensitive raw activity | native periodic input | unchanged settings.json', foreground='#444')
    fixed.pack(anchor='w', pady=(5, 3))

    controls = ttk.LabelFrame(outer, text='2. Record and save', padding=10)
    controls.pack(fill='x', pady=4)
    line = ttk.Frame(controls)
    line.pack(fill='x')

    def open_dir(folder: Path):
        if not folder.is_dir():
            messagebox.showinfo('Not available', 'The folder has not been created yet.')
            return
        if sys.platform == 'darwin':
            subprocess.Popen(['open', str(folder)])
        elif sys.platform == 'win32':
            os.startfile(str(folder))
        else:
            subprocess.Popen(['xdg-open', str(folder)])

    def start():
        if runtime['proc'] is not None and runtime['proc'].poll() is None:
            return
        if probe['usb_kind'] == 'disconnected':
            messagebox.showwarning('Connect the EVK4',
                'The control window works offline, but recording needs the EVK4. '
                'Connect the USB cable, click Refresh, then Start Recording.')
            return
        if camera_py is None:
            messagebox.showerror('Camera environment missing',
                'No established EVK4 Python environment was found.\n'
                'From the repository root, create one using the existing pinned requirements, or set EVK4_PYTHON.')
            return
        try:
            f = {k: v.get() for k, v in form.items()}
            f['notes'] = notes.get('1.0', 'end').strip()
            meta = metadata_from_form(f)
            dest = Path(dataset.get()).expanduser().resolve()
            if dest == ROOT or dest == REPO or dest.is_relative_to(REPO):
                raise ValueError('Choose a dataset directory outside the Git repository.')
            if dest.exists() and not dest.is_dir():
                raise ValueError('Dataset destination is not a folder.')
            # Avoid writing original multi-GB events into cloud-synced locations.
            if any(s in str(dest).lower() for s in ('google drive', 'onedrive', 'dropbox')):
                raise ValueError('Record to a local or external disk first, not a cloud-synced folder.')
            if not dest.exists():
                dest.mkdir(parents=True)
            free = shutil.disk_usage(dest).free
            if free < 8 * 1024**3 and not messagebox.askyesno(
                'Low storage', f'Only {free / 1024**3:.1f} GB free. Original event recordings can be large. Continue?'):
                return
            make_dataset_root(dest)
            stamp = unique_run_id(meta)
            run = dest / 'Tests' / stamp
            if run.exists():
                raise ValueError('Generated run folder already exists. Retry Start.')
            meta['start_local'] = current_local_time()
            meta['run_id'] = stamp
            meta['notes'] = meta.pop('operator_notes')
            meta['operator_notes'] = meta['notes']
            cmd = recording_command(camera_py, run, meta)
            log_path = dest / ('_operator_' + stamp + '.log')
            fh = log_path.open('x')
            try:
                kwargs = dict(cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT)
                if sys.platform != 'win32':
                    kwargs['start_new_session'] = True
                p = subprocess.Popen(cmd, **kwargs)
            except BaseException:
                fh.close()
                raise
            fh.close()
            runtime.update(proc=p, run=run, meta=meta, dataset=dest, log=log_path,
                           started=time.monotonic(), stop_requested=False,
                           finalized=False)
            last_run_label.set(stamp)
            status.set('STARTING CAMERA ...')
            start_button.configure(state='disabled')
            stop_button.configure(state='normal')
        except Exception as exc:
            messagebox.showerror('Could not start', str(exc))

    def stop():
        p = runtime['proc']
        if p is None or p.poll() is not None or runtime['stop_requested']:
            return
        if sys.platform == 'win32':
            # Windows SIGINT to a subprocess is not the POSIX graceful signal.
            # Do not terminate a recorder containing multi-GB experimental data.
            messagebox.showinfo('Finish this recording safely',
                'Select the EVK4 camera/dashboard window and press Q.\n'
                'The existing camera application will close its event and movie files.\n'
                'This control window will show FINISHED automatically.\n'
                'Do not close this window while finalizing.')
            return
        try:
            runtime['stop_requested'] = request_graceful_stop(p)
            stop_button.configure(state='disabled')
            status.set('STOP REQUESTED | Finalizing files. Keep this window open.')
        except OSError as exc:
            messagebox.showerror('Stop failed', str(exc))

    start_button = ttk.Button(line, text='START RECORDING', command=start)
    start_button.pack(side='left', fill='x', expand=True, padx=3)
    stop_label = 'STOP: press Q in EVK4 window' if sys.platform == 'win32' else 'STOP & SAVE'
    stop_button = ttk.Button(line, text=stop_label, command=stop, state='disabled')
    stop_button.pack(side='left', fill='x', expand=True, padx=3)
    def preview_without_camera():
        try:
            f = {k: v.get() for k, v in form.items()}
            f['notes'] = notes.get('1.0', 'end').strip()
            meta = metadata_from_form(f)
            messagebox.showinfo('Offline test setup',
                f"Environment: {meta['environment']}\n"
                f"Lens: {meta['lens_mm']:g} mm | Range: {meta['range_m']:g} m\n"
                f"Focus: {meta['focus_m'] or 'not recorded'} m | "
                f"Lux: {meta['illuminance_lux'] or 'not recorded'}\n"
                f"Aspect: {meta['aspect']} | Motion: {meta['profile']}\n"
                f"Duration: {meta['requested_duration_s']} seconds\n\n"
                'Settings are valid. No recording started; no camera required.')
        except ValueError as exc:
            messagebox.showerror('Check test details', str(exc))
    ttk.Button(controls, text='Preview settings (offline)',
               command=preview_without_camera).pack(anchor='w', pady=(1, 2))
    ttk.Label(controls, textvariable=status, font=('Helvetica', 12, 'bold')).pack(anchor='w', pady=6)
    ttk.Label(controls, textvariable=last_run_label, wraplength=680).pack(anchor='w')
    actionrow = ttk.Frame(controls)
    actionrow.pack(fill='x', pady=5)
    ttk.Button(actionrow, text='Open last run', command=lambda: open_dir(runtime['run']) if runtime['run'] else None).pack(side='left', padx=3)
    ttk.Button(actionrow, text='Open dataset', command=lambda: open_dir(Path(dataset.get()).expanduser())).pack(side='left', padx=3)
    def add_documents():
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(title='Choose supplementary documents to copy')
        if not paths: return
        dest = Path(dataset.get()).expanduser() / 'Documents'
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for p in map(Path, paths):
            d = dest / p.name
            if d.exists():
                continue
            shutil.copy2(p, d)
            copied += 1
        messagebox.showinfo('Documents', f'Copied {copied} new document(s). Existing files not overwritten.')
    ttk.Button(actionrow, text='Add documents', command=add_documents).pack(side='left', padx=3)

    def attach_reference():
        run = runtime['run']
        if run is None or not run.is_dir():
            messagebox.showinfo('No take selected', 'Record a test first, then attach its reference movie.')
            return
        if runtime['proc'] is not None and runtime['proc'].poll() is None:
            messagebox.showinfo('Recording', 'Attach the reference movie after the recording finishes.')
            return
        selected = filedialog.askopenfilename(
            title='Select reference camera movie for this test',
            filetypes=[('Video files', '*.mp4 *.mov *.avi *.mkv'), ('All files', '*')])
        if not selected:
            return
        source = Path(selected)
        ref = run / 'reference'
        ref.mkdir(exist_ok=True)
        target = ref / source.name
        if target.exists():
            messagebox.showwarning('File exists', 'A reference file with this name is already attached. Nothing was overwritten.')
            return
        try:
            shutil.copy2(source, target)
            row = load_json(run / 'trial.json')
            row.setdefault('reference_movies', []).append('reference/' + target.name)
            row['reference_time_alignment'] = 'Unverified; not hardware synchronized'
            atomic_json(run / 'trial.json', row)
            refresh_index(runtime['dataset'])
        except Exception as exc:
            messagebox.showerror('Could not attach video', str(exc))
            return
        messagebox.showinfo('Reference saved', 'Copied into this take under reference/. Original is unchanged. Not synchronized by default.')

    ttk.Button(actionrow, text='Attach reference video', command=attach_reference).pack(side='left', padx=3)

    def refresh_connection(force_python=False):
        if probe['busy']:
            return
        if runtime['proc'] is not None and runtime['proc'].poll() is None:
            return  # no background USB probes while recording
        probe['busy'] = True
        usb_status.set('Camera USB: Checking...')
        check_python = force_python or not probe['checked_python']
        if check_python:
            python_status.set('Recording software: Checking...')
        def task():
            python_result = discover_camera_python() if check_python else camera_py
            kind, detail = inspect_usb_connection(camera_python=python_result)
            probe_queue.put((kind, detail, check_python, python_result))
        threading.Thread(target=task, daemon=True, name='EVK4 idle connection check').start()

    ttk.Button(connection_row, text='Refresh connection',
               command=lambda: refresh_connection(force_python=(camera_py is None))).pack(side='right', padx=6)

    guidance = ttk.Label(outer,
        text='In the camera window: press 1 when the target enters, 2 when it leaves, S for a photo.\n'
             'Records events, dashboard/raw/filtered videos, logs and plots.\n'
             'macOS: Stop & Save. Windows: press Q in the camera window; controller finalizes the take.',
        justify='left', wraplength=710)
    guidance.pack(anchor='w', pady=4)

    def poll():
        nonlocal camera_py
        try:
            while True:
                kind, detail, checked_py, found_py = probe_queue.get_nowait()
                probe.update(busy=False, usb_kind=kind, next_at=time.monotonic()+8)
                if checked_py:
                    camera_py = found_py
                    probe['checked_python'] = True
                if kind == 'connected':
                    usb_status.set('Camera USB: CONNECTED (hardware detected)')
                elif kind == 'disconnected':
                    usb_status.set('Camera USB: DISCONNECTED (plug in to record)')
                else:
                    usb_status.set('Camera USB: CHECK UNAVAILABLE (' + detail + ')')
                if probe['checked_python']:
                    python_status.set('Recording software: READY' if camera_py is not None
                                      else 'Recording software: NOT FOUND (check Python environment)')
                if runtime['proc'] is None:
                    status.set('OFFLINE | Ready to record' if camera_py is not None and kind=='connected'
                               else 'OFFLINE | GUI ready. Connect camera when available.')
        except queue.Empty:
            pass
        p = runtime['proc']
        if p is not None and not runtime['finalized']:
            elapsed = time.monotonic() - runtime['started']
            rc = p.poll()
            if rc is None:
                if runtime['stop_requested']:
                    status.set(f'FINALIZING | {elapsed:.0f} seconds since launch | Keep this window open')
                else:
                    stage = ('FINALIZING REPORT' if (runtime['run'] / 'summary.json').is_file()
                             else ('RECORDING' if (runtime['run'] / 'session.json').is_file()
                                   else 'OPENING CAMERA'))
                    status.set(f'{stage} | {elapsed:.0f} seconds since launch | Stop & Save available')
            else:
                runtime['finalized'] = True
                quality = finalize_trial(runtime['dataset'], runtime['run'],
                                         runtime['meta'], rc, runtime['stop_requested'],
                                         operator_log=runtime['log'])
                status.set(f"FINISHED | {quality.get('recording_status')} | code {rc}")
                stop_button.configure(state='disabled')
                start_button.configure(state='normal')
                if quality.get('recording_status') != 'RECORDED_UNREVIEWED':
                    messagebox.showwarning('Review recording quality',
                        'The run finished, but data integrity needs review.\n'
                        f"Status: {quality.get('recording_status')}\n"
                        'Keep the complete run and inspect summary.json and the GUI log.\n'
                        'Never count invalid data as a negative detection.')
        if (p is None or p.poll() is not None) and not probe['busy'] and \
           time.monotonic() >= probe['next_at']:
            refresh_connection()
        if p is not None and p.poll() is None:
            usb_status.set('Camera USB: Acquisition running; idle USB checks paused')
        ui.after(800, poll)

    def exit_app():
        p = runtime['proc']
        if p is not None and p.poll() is None:
            messagebox.showwarning('Recording in progress',
                'Click Stop & Save and keep this window open until finalization finishes.')
            return
        ui.destroy()
    ui.protocol('WM_DELETE_WINDOW', exit_app)
    poll()
    ui.mainloop()


if __name__ == '__main__':
    run_gui()
