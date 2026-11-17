from pathlib import Path
import sys,importlib.util,tempfile,io,json,unittest,hashlib,struct
W=Path(__file__).resolve().parent;B=W.parent/'pr771-firstbatch-20261103-v1';R=B/'runtime';G=B/'git'
sys.path.insert(0,str(R));import els_server
assert Path(els_server.__file__).is_relative_to(R)
(W/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(W/'tmp')
hashes={}
for name in ('test_mount_flow','test_mount_retry'):
    path=G/'tests'/(name+'.py');hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)

class Identity(sys.modules['test_mount_flow'].MountFlowTests):
    def test_storage_readers_and_ride_responses_keep_the_owned_identity(self):
        from els_server.protocol import companion_messages as companion
        from els_server.domain import mount_flow
        from els_server.storage.companion_state import snapshot
        reply=self.summon()[0]
        saved=snapshot(self.path,1001)
        mount=next(p for p in saved['companions']if p['kind']=='mount')
        replies=[(reply,4),(companion.mount_list(0,[mount]),8),
                 (companion.initialization(saved),32),
                 (companion.activation_ack('mount',0,mount),4)]
        event,sequence=self.request(0x42f,struct.pack('>Qi',self.uid,0),11)
        replies.append((mount_flow.handle(self.session,event,sequence)[0],12))
        for event,offset in replies:
            with self.subTest(kind=hex(event.kind)):
                body=event.payload[offset:offset+55]
                self.assertEqual(struct.unpack_from('>Q',body)[0],self.uid)
                self.assertEqual(struct.unpack_from('>QHBiI',body,36),(self.uid,0,1,0,0))
        self.assertEqual(struct.unpack_from('>QHBiI',companion.mount_record(),36),(0,0,1,0,0))

selected=['test_mount_flow.MountFlowTests.test_native_admission_and_no_fake_skill_rpc',
          'test_mount_retry.MountRetryTests.test_current_down_replay_remains_success_and_one_receipt',
          '__main__.Identity.test_storage_readers_and_ride_responses_keep_the_owned_identity']
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n)for n in selected)
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
paths={n:str(m.__file__)for n,m in sys.modules.copy().items()if n.startswith('els_server')and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(R)for p in paths.values())
out=dict(ok=result.wasSuccessful(),tests=result.testsRun,skipped=len(result.skipped),case_ids=selected,test_hashes=hashes,
    source_sha256=hashlib.sha256((R/'els_server/protocol/mount_messages.py').read_bytes()).hexdigest(),
    import_paths_verified=True,owned_temp_root=str(W/'tmp'),errors=[(str(t),s)for t,s in result.errors+result.failures])
assert not (W/'mount-regressions.json').exists()
(W/'mount-regressions.json').write_text(json.dumps(out,indent=2),encoding='utf8')
print(stream.getvalue());print(json.dumps({k:v for k,v in out.items()if k!='errors'}))
raise SystemExit(not result.wasSuccessful())
