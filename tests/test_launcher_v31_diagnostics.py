"""Portable diagnostic-layout checks; temporary data only, no game or network."""
from pathlib import Path
import base64,datetime,hashlib,importlib.util,json,os,sys,tempfile,unittest,uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SOURCE=ROOT/'launchers/friends-v31/runtime-tools/friends_diagnostics.py'
spec=importlib.util.spec_from_file_location('launcher_v31_diagnostics',SOURCE)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
from els_server.diagnostic_reports import validate_archive

class LauncherV31Diagnostics(unittest.TestCase):
    def test_signed_resource_matches_diagnostic_tool(self):
        envelope=json.loads((SOURCE.parents[1]/'runtime-files.signed.json').read_bytes())
        definition=json.loads(base64.b64decode(envelope['payload']))
        rows={row['path']:row for row in definition['files']}
        self.assertEqual(len(rows),1082)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),rows['tools/friends_diagnostics.py']['sha256'])
        self.assertEqual(SOURCE.stat().st_size,rows['tools/friends_diagnostics.py']['size'])

    def test_both_layouts_collect_selected_bridge(self):
        with tempfile.TemporaryDirectory(prefix='launcher-v31-paths-') as folder:
            data=Path(folder);attempt=uuid.uuid4().hex;credential=uuid.uuid4().hex
            logs=data/'logs/attempts'/attempt;logs.mkdir(parents=True)
            now=datetime.datetime.now(datetime.timezone.utc).isoformat()
            (logs/'attempt.json').write_text(json.dumps(dict(schema=1,attempt_id=attempt,started_utc=now,ended_utc=now,phase='game_exit')),'utf8')
            (logs/'client-check.log').write_text('preflight passed\n','utf8')
            original_events=helper.windows_events
            helper.windows_events=lambda *args,**kwargs:dict(status='fixture',events=[])
            try:
                for layout in ('versions','component-runtimes'):
                    runtime=data/layout/'0123456789abcdef-0123456789ab'
                    bridge=runtime/'state/friends-client/exact-attempt';bridge.mkdir(parents=True)
                    label='to'+'ken'
                    (bridge/'bridge.log').write_text('selected bridge\n'+label+'='+credential+'\n','utf8')
                    marker=dict(attempt_id=attempt,path='state/friends-client/exact-attempt')
                    (logs/'game-launch.log').write_text('ELS_DIAGNOSTIC_BRIDGE: '+json.dumps(marker)+'\n','utf8')
                    request=dict(data_root=str(data),payload_root=str(runtime),attempt_id=attempt,token=credential)
                    output=data/(layout+'.zip');self.assertTrue(helper.collect(request,output)['ok'])
                    members,_=validate_archive(output.read_bytes())
                    self.assertIn(b'selected bridge',members['logs/bridge.log'])
                    self.assertNotIn(credential.encode(),members['logs/bridge.log'])
            finally:helper.windows_events=original_events

    def test_parent_and_outside_rejected(self):
        with tempfile.TemporaryDirectory(prefix='launcher-v31-outside-') as folder:
            data=Path(folder)/'launcher';data.mkdir()
            for candidate in (data,data/'versions',data/'component-runtimes',data.parent/'outside',data/'versions/../../outside'):
                with self.assertRaises(ValueError):helper.diagnostic_payload(candidate,data)

    def test_linked_runtime_and_root_rejected(self):
        with tempfile.TemporaryDirectory(prefix='launcher-v31-links-') as folder:
            data=Path(folder)/'launcher';data.mkdir();outside=Path(folder)/'outside';outside.mkdir()
            root=data/'component-runtimes';root.mkdir();linked=root/'linked'
            try:os.symlink(outside,linked,target_is_directory=True)
            except (OSError,NotImplementedError) as error:self.skipTest('Directory symlink unavailable: '+type(error).__name__)
            try:
                with self.assertRaises(ValueError):helper.diagnostic_payload(linked/'child',data)
            finally:linked.unlink()
            root.rmdir();os.symlink(outside,root,target_is_directory=True)
            try:
                with self.assertRaises(ValueError):helper.diagnostic_payload(root/'child',data)
            finally:root.unlink()

if __name__=='__main__':unittest.main()
