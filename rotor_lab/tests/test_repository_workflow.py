"""Repository launch and duration checks. No camera is opened by these tests."""
from __future__ import annotations
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import app
import field


class CaptureBeforeWorker(Exception):
    pass


class DurationTests(unittest.TestCase):
    def field_args(self, argv):
        with patch.object(field, 'record', return_value=0) as call:
            self.assertEqual(field.main(argv), 0)
        return call.call_args.args[0]

    def app_args(self, argv):
        captured = {}
        class Context:
            def Queue(self, *args, **kwargs): return None
            def Event(self): return None
            def Process(self, *args, **kwargs):
                captured.update(kwargs['args'][0])
                raise CaptureBeforeWorker()
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)/'run'
            with patch.object(app.mp, 'get_context', return_value=Context()), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(CaptureBeforeWorker):
                    app.main([*argv,'--run-dir',str(run)])
        return captured

    def test_distance_default_is_one_minute(self):
        self.assertEqual(self.field_args(['25','20']).duration,60.)

    def test_distance_override_is_not_overwritten(self):
        self.assertEqual(self.field_args(['25','20','--duration','90']).duration,90.)

    def test_distance_minimum_20_seconds_unchanged(self):
        self.assertEqual(self.field_args(['25','20','--duration','20']).duration,20.)
        with self.assertRaisesRegex(ValueError,'at least 20'):
            field.main(['25','20','--duration','19'])

    def test_generic_record_default_is_one_minute(self):
        a=self.app_args(['record'])
        self.assertEqual(a['duration'],60)
        self.assertTrue(a['record']);self.assertTrue(a['video'])

    def test_generic_override_preserved(self):
        self.assertEqual(self.app_args(['record','--duration','90'])['duration'],90)

    def test_live_monitoring_is_unlimited(self):
        self.assertEqual(self.app_args(['live'])['duration'],0)

    def test_explicit_live_recording_duration_preserved(self):
        a=self.app_args(['live','--record','--duration','60'])
        self.assertEqual(a['duration'],60);self.assertTrue(a['record'])

    def test_photo_still_has_its_own_timer(self):
        a=self.app_args(['photo','--after','7'])
        self.assertEqual(a['after'],7);self.assertEqual(a['duration'],0)

    def test_bad_live_duration_rejected(self):
        for value in ['-1','nan','inf']:
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):app.main(['record','--duration',value])


class RoutingTests(unittest.TestCase):
    def test_generic_capture_forwards_real_app_options(self):
        opts=['--duration','90','--name','no target','--photos-every','5']
        with patch.object(field.subprocess,'call',return_value=0) as call:
            field.main(['capture',*opts])
        self.assertEqual(call.call_args.args[0],[sys.executable,str(field.ROOT/'app.py'),'record',*opts])

    def test_photo_forwards_after(self):
        with patch.object(field.subprocess,'call',return_value=0) as call:
            field.main(['photo','--after','5'])
        self.assertEqual(call.call_args.args[0][-3:],['photo','--after','5'])

    def test_check_default_stays_short(self):
        with patch.object(field.subprocess,'call',return_value=0) as call:
            field.main(['check'])
        self.assertEqual(call.call_args.args[0][-3:],['--camera','--seconds','5.0'])

    def test_check_can_be_extended(self):
        with patch.object(field.subprocess,'call',return_value=0) as call:
            field.main(['check','--seconds','15'])
        self.assertEqual(call.call_args.args[0][-1],'15.0')

    def test_verify_fail_is_nonzero(self):
        with patch.object(field,'resolve_run',return_value=Path('/test-only')), \
             patch.object(field,'verify',return_value={'status':'FAIL','issues':['simulated loss']}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(field.main(['verify','latest']),1)

    def test_verify_pass_is_zero(self):
        with patch.object(field,'resolve_run',return_value=Path('/test-only')), \
             patch.object(field,'verify',return_value={'status':'PASS'}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(field.main(['verify','latest']),0)

    def test_latest_replay_and_compare_use_the_same_trial(self):
        with tempfile.TemporaryDirectory() as d:
            run=Path(d);(run/'events.evs').write_bytes(b'path-test-only')
            with patch.object(field,'resolve_run',return_value=run), patch.object(field.subprocess,'call',return_value=0) as call:
                field.main(['replay','latest']);replay=call.call_args.args[0]
                field.main(['compare','latest']);compare=call.call_args.args[0]
            self.assertIn(str(run/'events.evs'),replay);self.assertIn(str(run/'events.evs'),compare)

    def test_explicit_run_folder_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'events.evs').write_bytes(b'path-test-only')
            self.assertEqual(field.recording_path(d),Path(d)/'events.evs')

    def test_missing_original_events_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'not found'):field.recording_path(d)


class RootLauncherTests(unittest.TestCase):
    def sandbox(self, root):
        repo=root/'repo with spaces';lab=repo/'rotor_lab';lab.mkdir(parents=True)
        shutil.copyfile(field.ROOT.parent/'run.sh',repo/'run.sh')
        shutil.copyfile(field.ROOT/'test.sh',lab/'test.sh')
        home=root/'fake_home';home.mkdir()
        env=dict(os.environ,HOME=str(home),LOGFILE=str(root/'arguments.txt'))
        env.pop('EVK4_PYTHON',None)
        return repo,lab,home,env

    def fake_python(self,path,works=True):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('#!/usr/bin/env bash\nif [ "${1:-}" = "-c" ]; then exit '+('0' if works else '1')+'; fi\nprintf "%s\\n" "$PWD" "$@" > "$LOGFILE"\n')
        path.chmod(0o755)

    def test_root_launcher_preserves_arguments_and_runs_in_app_folder(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo,lab,home,env=self.sandbox(root)
            py=root/'explicit python';self.fake_python(py);env['EVK4_PYTHON']=str(py)
            result=subprocess.run(['bash',str(repo/'run.sh'),'25','20','--notes','test with spaces'],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((root/'arguments.txt').read_text().splitlines(),[str(lab),'field.py','25','20','--notes','test with spaces'])

    def test_root_environment_is_discovered(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo,lab,home,env=self.sandbox(root)
            self.fake_python(repo/'.venv/bin/python')
            result=subprocess.run(['bash',str(repo/'run.sh'),'test'],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_incomplete_environment_is_skipped_for_existing_working_one(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo,lab,home,env=self.sandbox(root)
            self.fake_python(repo/'.venv/bin/python',False)
            self.fake_python(home/'Downloads/evk4_distance_test/.venv/bin/python')
            result=subprocess.run(['bash',str(repo/'run.sh'),'check'],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_missing_env_does_not_install_anything(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo,lab,home,env=self.sandbox(root)
            result=subprocess.run(['bash',str(repo/'run.sh'),'check'],env=env,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((lab/'.venv').exists());self.assertFalse((repo/'.venv').exists())
            self.assertIn('No complete existing',result.stdout)

    def test_explicit_invalid_environment_fails_without_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo,lab,home,env=self.sandbox(root)
            self.fake_python(repo/'.venv/bin/python')
            env['EVK4_PYTHON']=str(root/'missing')
            result=subprocess.run(['bash',str(repo/'run.sh'),'check'],env=env,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('not an executable',result.stdout)


if __name__=='__main__':unittest.main()
