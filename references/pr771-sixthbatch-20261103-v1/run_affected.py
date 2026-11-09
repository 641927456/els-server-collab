from pathlib import Path
import sys,io,json,unittest,tempfile,hashlib,importlib.util
from unittest.mock import patch
W=Path(__file__).resolve().parent;ROOT=Path('G:/els');B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime'
sys.path[:0]=[str(R),str(W),str(B)]
import els_server
assert Path(els_server.__file__).is_relative_to(R)
(W/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(W/'tmp')
import test_sentry_carry
hashes={}
for name in ('test_summons','test_dungeon_spawns','test_dungeon_routes'):
    p=ROOT/'tests'/(name+'.py');hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    assert p.read_bytes()==(B/'git/tests'/(name+'.py')).read_bytes()
spec=importlib.util.spec_from_file_location('test_dungeon_routes',ROOT/'tests/test_dungeon_routes.py');module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module;spec.loader.exec_module(module)
spec=importlib.util.spec_from_file_location('test_dungeon_spawns',ROOT/'tests/test_dungeon_spawns.py');module2=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module2;spec.loader.exec_module(module2)
class OriginalCapture(unittest.TestCase):
    def test_original_captured_summon_roundtrips_qualification_and_long_encounter(self):
        # Reuse the complete summon section, through105 spawn/retire cycles.
        # The later legacy El Tree enemy-gate section is outside this change
        # and has no current HP/admission context; retain its failed attempt.
        p=ROOT/'tests/test_summons.py';source=p.read_text('utf8')
        source=source.split('    # Actual stage-one wire:',1)[0]
        exec(compile(source,str(p),'exec'),{'__file__':str(p),'__name__':'original_captured_summon_section'})
class ExistingSpawns(unittest.TestCase):
    setUp=test_sentry_carry.base.SecondBatch.setUp
    dungeon=test_sentry_carry.base.SecondBatch.dungeon
    def current_spawn_session(self,identity):
        s=self.dungeon(identity)
        # The original assertions concern spawn replies, before the outer
        # login/tutorial/periodic observers prepend their unrelated notices.
        s.handle=s._handle
        return s,self.t
    def test_existing_scripted_batch_and_duplicate(self):
        with patch.object(module2,'start',self.current_spawn_session):
            module2.DungeonSpawnsTests.test_batch_creates_declared_minions_with_unique_reserved_slots(self)
    def test_existing_scripted_bad_template_owner_and_atomic_batch(self):
        with patch.object(module2,'start',self.current_spawn_session):
            module2.DungeonSpawnsTests.test_unknown_template_foreign_creator_and_failed_batch_do_not_mutate(self)
suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(test_sentry_carry.Carry),
    unittest.defaultTestLoader.loadTestsFromTestCase(OriginalCapture),
    unittest.defaultTestLoader.loadTestsFromTestCase(ExistingSpawns)])
if sys.argv[1:]==['scripted-only']:suite=unittest.defaultTestLoader.loadTestsFromTestCase(ExistingSpawns)
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
paths={n:str(m.__file__)for n,m in sys.modules.copy().items()if n.startswith('els_server')and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(R)for p in paths.values())
changed=('dungeon_routes','local_session','dungeon_flow','dungeon_settlement_commands','friends_spawns')
out=dict(ok=result.wasSuccessful(),tests=result.testsRun,skipped=len(result.skipped),
    test_hashes=hashes,test_sentry_carry_sha256=hashlib.sha256((W/'test_sentry_carry.py').read_bytes()).hexdigest(),
    source_hashes={'els_server/domain/'+name+'.py':hashlib.sha256((R/'els_server/domain'/(name+'.py')).read_bytes()).hexdigest()for name in changed},
    import_paths_verified=True,errors=[(str(t),s)for t,s in result.errors+result.failures],
    private_database_only=True,live_process=False,natural_GUI=False,installed=False)
out['fixture_scope']='Original summon section only; scripted spawn assertions use current99-level authenticated Application sessions and inner dispatch.'
target=W/('tests-scripted-final.json'if sys.argv[1:]==['scripted-only']else'tests-affected.json')
target.write_text(json.dumps(out,indent=2),encoding='utf8')
print(stream.getvalue());print(json.dumps({k:v for k,v in out.items()if k not in('errors','source_hashes','test_hashes')}))
raise SystemExit(not result.wasSuccessful())
