"""Only the four rebased quest leaves need new private regression results."""
from common import *
import ast,io,sqlite3,sys,tempfile,unittest
from contextlib import closing
from unittest.mock import patch
R=W/'runtime';B=ROOT/'analysis/pr771-firstbatch-20261103-v1';GAPS=ROOT/'analysis/pr771-gaps-20261103-v1'
sys.path[:0]=[str(R),str(B),str(GAPS)];sys.dont_write_bytecode=True
(W/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(W/'tmp')
import els_server
assert Path(els_server.__file__).is_relative_to(R)
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.domain.seal_quests import quest_catalog
from els_server.domain.tutorial_quests import restore_initialization
from els_server.protocol.protocol_codec import encode_event
import test_secondbatch,test_gaps
old=ROOT/'analysis/player-feedback-regression-20261103-v1'
classes=[];inputs={}
for name,cls in [('verify_arrival_roots.py','Arrival'),('verify_remote_quest_claim.py','Remote')]:
    path=old/name;inputs[str(path)]=sha(path);tree=ast.parse(path.read_text('utf8'))
    scope=dict(globals(),__name__='rebased_'+cls,HERE=W/'tmp',BASELINE=False)
    from els_server.storage.seal_quests import QuestIncomplete
    scope['QuestIncomplete']=QuestIncomplete
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.ClassDef)and n.name==cls],type_ignores=[]),str(path),'exec'),scope)
    classes.append(scope[cls])
class AboveFifty(classes[0]):
    def test_arrival_preserved_above_fifty_epic_tasks(self):
        c=quest_catalog();ids=[i for i,q in sorted(c.quests.items())if q['m_eQuestType']==5 and i not in(100000,100030,100090,25610,25611,25612)][:55]
        with closing(sqlite3.connect(self.path))as db,db:
            for identity in ids:db.execute('INSERT OR IGNORE INTO character_quests VALUES(?,?,?,?,?)',(1001,identity,1,1,json.dumps({s['m_iID']:0 for s in c.objectives(identity)})))
        self.test_new_town_independent_root_no_reward_and_idempotence()
suite=unittest.TestSuite()
for cls in(test_gaps.QuestLimits,test_gaps.Reselection,*classes):suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
suite.addTest(AboveFifty('test_arrival_preserved_above_fifty_epic_tasks'))
for name in('test_all_eight_new_entries_require_real_predecessor_and_claim','test_region_rejects_level_owner_and_rolls_back_encode_failure'):suite.addTest(test_secondbatch.SecondBatch(name))
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
loaded=[Path(m.__file__)for n,m in sys.modules.copy().items()if n.startswith('els_server')and getattr(m,'__file__',None)]
assert all(p.is_relative_to(R)for p in loaded)
report=dict(ok=result.wasSuccessful(),tests=result.testsRun,skipped=len(result.skipped),errors=[(str(t),trace)for t,trace in result.errors+result.failures],
    source_hashes={r['path']:sha(R/r['path'])for r in read(W/'rebase.json')['changes']},
    original_test_hashes=inputs,test_sha256=sha(__file__),import_paths_verified=True,production_database_used=False,natural_GUI=False)
save(W/'rebase-tests.json',report);print(stream.getvalue());print(json.dumps(dict(ok=report['ok'],tests=report['tests'],errors=len(report['errors']),skipped=report['skipped'])));sys.exit(not report['ok'])
