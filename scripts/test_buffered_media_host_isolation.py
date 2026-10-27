#!/usr/bin/env python3
"""Offline execution of the actual media shell; never production evidence."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT/'scripts/run_buffered_media_preparation_host.sh'
SHA = 'a'*40
OTHER_SHA = 'b'*40
OFF_FLAGS = (
    'PUBLISH_ENABLED', 'ALLOW_REAL_THREADS_POST', 'ALLOW_REAL_THREADS_VIDEO_POST',
    'ALLOW_REAL_X_POST', 'ALLOW_MEDIA_POSTS', 'ALLOW_THREADS_CAROUSEL',
    'ALLOW_THREADS_MIXED_CAROUSEL', 'ALLOW_VIDEO_DOWNLOAD', 'ALLOW_VIDEO_CUT',
    'ALLOW_CLOUDINARY_UPLOAD', 'ALLOW_TRANSCRIPTION_API', 'ALLOW_LOCAL_TRANSCRIPTION',
    'GITHUB_MODELS_ENABLED', 'MOCK_LLM', 'MOCK_SHEETS', 'DRY_RUN',
)


class MediaHostIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='sns-media-shell-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.runtime = self.base/'runtime'
        self.shared = self.runtime/'shared'
        self.shared.mkdir(parents=True)
        self.deploy_lock = self.base/'deploy.lock'
        self.deploy_lock.touch()
        self.events = self.base/'events.jsonl'
        self.calls = self.base/'calls.jsonl'
        self.bin = self.base/'bin'
        self.bin.mkdir()
        self.release = self.make_release(SHA)
        (self.runtime/'current').symlink_to(self.release)
        self.config = self.shared/'runtime.env'
        self.write_config()
        self.wrapper = self.base/'host.sh'
        source = HOST.read_text()
        self.assertEqual(source.count('common_lock=/run/lock/chadult-production-deploy.lock'), 1)
        self.wrapper.write_text(source.replace('common_lock=/run/lock/chadult-production-deploy.lock',
            'common_lock='+shlex.quote(str(self.deploy_lock))))
        self.executable(self.bin/'awk', r'''
import json, os, sys
field = 'total' if 'MemTotal' in sys.argv[1] else 'available'
with open(os.environ['TEST_EVENTS'], 'a') as out:
    out.write(json.dumps({'event': 'memory', 'field': field})+'\n')
print(os.environ.get('TEST_MEMORY_'+field.upper(), '8388608' if field == 'total' else '4194304'))
''')
        self.executable(self.bin/'flock', r'''
import fcntl, json, os, pathlib, sys
if os.environ.get('TEST_PROMOTE_AT_LOCK'):
    current = pathlib.Path(os.environ['BUFFERED_RUNTIME_ROOT'])/'current'
    current.unlink(); current.symlink_to(os.environ['TEST_PROMOTE_AT_LOCK'])
fd = int(sys.argv[-1])
fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
with open(os.environ['TEST_EVENTS'], 'a') as out:
    out.write(json.dumps({'event': 'deploy_lock'})+'\n')
''')
        self.executable(self.bin/'readlink', r'''
import json, os, pathlib, sys
resolved = str(pathlib.Path(sys.argv[-1]).resolve())
with open(os.environ['TEST_EVENTS'], 'a') as out:
    out.write(json.dumps({'event': 'resolve', 'path': resolved})+'\n')
if os.environ.get('TEST_MOVE_AFTER_RESOLVE'):
    current = pathlib.Path(sys.argv[-1]); current.unlink()
    current.symlink_to(os.environ['TEST_MOVE_AFTER_RESOLVE'])
print(resolved)
''')
        stat = shutil.which('stat')
        self.executable(self.bin/'stat', f'''
import os, sys
if os.environ.get('TEST_OWNER_UID') and '%u' in sys.argv:
    print(os.environ['TEST_OWNER_UID'])
else:
    os.execv({stat!r}, [{stat!r}, *sys.argv[1:]])
''')

    def executable(self, path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!{sys.executable} -I\n'+body)
        path.chmod(0o700)

    def make_release(self, sha: str) -> Path:
        release = self.runtime/'releases'/sha
        (release/'scripts').mkdir(parents=True)
        (release/'scripts/run_buffered_media_preparation_host.py').write_text('# offline placeholder\n')
        (release/'.production-release').write_text(sha+'\n')
        self.executable(release/'.venv/bin/python', r'''
import fcntl, json, os, pathlib, runpy, sys, types
with open(os.environ['TEST_DEPLOY_LOCK'], 'a') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        held = True
    else:
        held = False
        fcntl.flock(lock, fcntl.LOCK_UN)
dotenv = types.ModuleType('dotenv'); dotenv.load_dotenv = lambda: None
sys.modules['dotenv'] = dotenv
cfg = runpy.run_path(os.environ['TEST_CONFIG_LOADER'])['get_config']()
row = {'argv': sys.argv[1:], 'cwd': os.getcwd(), 'lock_held': held,
       'sheet': cfg['sheet_id'], 'sa_fixture': cfg['sa_dict']['fixture_id'],
       'flags': {key:os.environ.get(key) for key in json.loads(os.environ['TEST_OFF_FLAGS'])},
       'revision': os.environ.get('CODE_REVISION'),
       'release': os.environ.get('PRODUCTION_RUNTIME_RELEASE'),
       'beauty_grant': os.environ.get('BEAUTY_ACTIVATION_APPROVED'),
       'gemini_key': os.environ.get('GEMINI_API_KEY'),
       'cloudinary_cloud': os.environ.get('CLOUDINARY_CLOUD_NAME'),
       'import_hook': os.environ.get('PYTHONPATH'),
       'alternate_keys_present': any(os.environ.get(key) for key in ['GITHUB_TOKEN','GH_TOKEN','GITHUB_MODELS_TOKEN','GITHUB_MODELS_API_KEY'])}
with open(os.environ['TEST_CALLS'], 'a') as out:
    out.write(json.dumps(row)+'\n')
raise SystemExit(int(os.environ.get('TEST_CHILD_EXIT', '0')))
''')
        return release

    def write_config(self, **overrides: str | None) -> None:
        values: dict[str, str | None] = {
            'SPREADSHEET_ID': 'protected-media-workbook',
            'GCP_SA_JSON_BASE64': base64.b64encode(json.dumps({'fixture_id':'protected-media-sa'}).encode()).decode(),
            'CLOUDINARY_CLOUD_NAME': 'protected-cloud-fixture',
            'CLOUDINARY_API_KEY': 'offline-cloud-key-fixture',
            'CLOUDINARY_API_SECRET': 'offline-cloud-secret-fixture',
            'GEMINI_API_KEY': 'offline-gemini-key-fixture',
            'BEAUTY_ACTIVATION_APPROVED': 'false',
            **{key:'true' for key in OFF_FLAGS},
        }
        values.update(overrides)
        self.config.write_text(''.join(key+'='+shlex.quote(value)+'\n'
            for key,value in values.items() if value is not None))
        self.config.chmod(0o600)

    def execute(self, *, tracing: bool = False, **extra: str):
        env = {
            'PATH':str(self.bin)+os.pathsep+os.environ.get('PATH',''),
            'HOME':str(self.base), 'BUFFERED_RUNTIME_ROOT':str(self.runtime),
            'TEST_EVENTS':str(self.events), 'TEST_CALLS':str(self.calls),
            'TEST_DEPLOY_LOCK':str(self.deploy_lock), 'TEST_CONFIG_LOADER':str(ROOT/'src/config_loader.py'),
            'TEST_OFF_FLAGS':json.dumps(OFF_FLAGS),
            'SA_JSON_BASE64':base64.b64encode(json.dumps({'fixture_id':'forged-sa'}).encode()).decode(),
            'SNS_MASTER_SHEET_ID':'forged-sheet', 'NOTE_MASTER_SHEET_ID':'forged-legacy-sheet',
            'GEMINI_API_KEY':'forged-gemini-key', 'CLOUDINARY_CLOUD_NAME':'forged-cloud',
            'BEAUTY_ACTIVATION_APPROVED':'true', 'PYTHONPATH':'/nonexistent/forged-imports',
            'GITHUB_TOKEN':'forged-model-token', 'MOCK_LLM':'true','MOCK_SHEETS':'true','DRY_RUN':'true',
        }
        env.update(extra)
        return subprocess.run(['bash', *(['-x'] if tracing else []), str(self.wrapper)],
            env=env,cwd=self.base,text=True,capture_output=True,timeout=12,check=False)

    def children(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_fixed_protected_configuration_mock_isolation_and_pinned_execution(self):
        result=self.execute()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(self.children()),1)
        row=self.children()[0]
        self.assertEqual(row['argv'],[str(self.release/'scripts/run_buffered_media_preparation_host.py'),'--apply','--confirm-preparation'])
        self.assertEqual(row['sheet'],'protected-media-workbook')
        self.assertEqual(row['sa_fixture'],'protected-media-sa')
        self.assertEqual(row['gemini_key'],'offline-gemini-key-fixture')
        self.assertEqual(row['cloudinary_cloud'],'protected-cloud-fixture')
        self.assertEqual(row['beauty_grant'],'false')
        self.assertFalse(row['alternate_keys_present'])
        self.assertTrue(all(value=='false' for value in row['flags'].values()))
        self.assertFalse(row['import_hook'])
        self.assertTrue(row['lock_held'])
        self.assertEqual(row['cwd'],str(self.release))
        self.assertEqual(row['release'],str(self.release))
        self.assertEqual(row['revision'],SHA)

    def test_protected_raw_credentials_and_legacy_sheet_alias_use_actual_loader(self):
        self.write_config(GCP_SA_JSON_BASE64=None, SPREADSHEET_ID=None,
            GCP_SA_JSON=json.dumps({'fixture_id':'protected-raw-media-sa'}),
            NOTE_MASTER_SHEET_ID='protected-legacy-media-workbook')
        result=self.execute()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(self.children()),1)
        self.assertEqual(self.children()[0]['sheet'],'protected-legacy-media-workbook')
        self.assertEqual(self.children()[0]['sa_fixture'],'protected-raw-media-sa')
        self.assertTrue(self.children()[0]['lock_held'])

    def test_shell_tracing_cannot_print_protected_credentials(self):
        result=self.execute(tracing=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('offline-gemini-key-fixture',result.stdout+result.stderr)
        self.assertNotIn('offline-cloud-secret-fixture',result.stdout+result.stderr)
        self.assertNotIn('protected-media-workbook',result.stdout+result.stderr)

    def test_caller_selected_env_cannot_supply_missing_protected_credentials(self):
        forged=self.base/'forged.env';forged.write_text(self.config.read_text());forged.chmod(0o600)
        self.write_config(GEMINI_API_KEY=None)
        result=self.execute(BUFFERED_RUNTIME_ENV_FILE=str(forged))
        self.assertEqual(result.returncode,78,result.stderr)
        self.assertEqual(self.children(),[])

    def test_caller_sheets_aliases_cannot_replace_missing_protected_account(self):
        for missing in ('GCP_SA_JSON_BASE64','SPREADSHEET_ID'):
            with self.subTest(missing=missing):
                self.write_config(**{missing:None})
                result=self.execute(GCP_SA_JSON='{}',GOOGLE_APPLICATION_CREDENTIALS='/nonexistent/forged.json')
                self.assertEqual(result.returncode,78,result.stderr)
                self.assertEqual(self.children(),[])

    def test_resource_floors_and_unknown_memory_never_invoke_media_child(self):
        self.config.unlink()  # Deferral must not need or load runtime credentials.
        for total,available in (('4194303','4194304'),('8388608','1572863'),('','4194304'),('8388608','invalid')):
            with self.subTest(total=total,available=available):
                result=self.execute(TEST_MEMORY_TOTAL=total,TEST_MEMORY_AVAILABLE=available)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('[DEFERRED]',result.stderr)
                self.assertIn('requires >=4 GiB RAM',result.stderr)
                self.assertEqual(self.children(),[])

    def test_exact_memory_floors_allow_the_existing_runner(self):
        result=self.execute(TEST_MEMORY_TOTAL='4194304',TEST_MEMORY_AVAILABLE='1572864')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(self.children()),1)

    def test_deployment_lock_precedes_release_resolution(self):
        other=self.make_release(OTHER_SHA)
        result=self.execute(TEST_PROMOTE_AT_LOCK=str(other))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.children()[0]['release'],str(other))
        events=[json.loads(line)['event'] for line in self.events.read_text().splitlines()]
        self.assertLess(events.index('deploy_lock'),events.index('resolve'))

    def test_moving_current_after_resolution_cannot_retarget_the_child(self):
        other=self.make_release(OTHER_SHA)
        result=self.execute(TEST_MOVE_AFTER_RESOLVE=str(other))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(os.path.realpath(self.runtime/'current'),str(other))
        self.assertEqual(self.children()[0]['release'],str(self.release))
        self.assertTrue(self.children()[0]['lock_held'])

    def test_linked_configuration_and_foreign_owner_refused_before_child(self):
        saved=self.base/'saved.env';self.config.rename(saved);self.config.symlink_to(saved)
        result=self.execute()
        self.assertEqual(result.returncode,78,result.stderr)
        self.assertEqual(self.children(),[])
        self.config.unlink();saved.rename(self.config)
        self.config.chmod(0o644)
        result=self.execute()
        self.assertEqual(result.returncode,77,result.stderr)
        self.assertEqual(self.children(),[])
        self.config.chmod(0o600)
        result=self.execute(TEST_OWNER_UID=str(os.geteuid()+1))
        self.assertEqual(result.returncode,77,result.stderr)
        self.assertEqual(self.children(),[])

    def test_invalid_marker_and_linked_worker_refused_before_child(self):
        marker=self.release/'.production-release';marker.write_text(OTHER_SHA+'\n')
        result=self.execute()
        self.assertEqual(result.returncode,78,result.stderr)
        self.assertEqual(self.children(),[])
        marker.write_text(SHA+'\n')
        worker=self.release/'scripts/run_buffered_media_preparation_host.py'
        worker.unlink();worker.symlink_to(marker)
        result=self.execute()
        self.assertEqual(result.returncode,78,result.stderr)
        self.assertEqual(self.children(),[])

    def test_nonzero_runner_exit_is_not_retried_or_hidden(self):
        result=self.execute(TEST_CHILD_EXIT='23')
        self.assertEqual(result.returncode,23,result.stderr)
        self.assertEqual(len(self.children()),1)


if __name__=='__main__':
    unittest.main()
