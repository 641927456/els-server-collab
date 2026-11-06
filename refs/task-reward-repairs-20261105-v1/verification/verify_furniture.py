"""Private source-award and downstream consumers, including reproducible gaps."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import unquote,urlparse

ROOT=Path('G:/els');OUT=Path(__file__).resolve().parent
CHANNEL='online'if'--online'in sys.argv else'local'
if '--online'in sys.argv:sys.argv.remove('--online')
POINT=json.loads((OUT/'base.json').read_bytes())
BASE=OUT/'runtime'
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor')]
temp=tempfile.TemporaryDirectory(prefix='owned-consumers-',dir=OUT);PRIVATE=Path(temp.name).resolve()
def audit(event,args):
    if event=='sqlite3.connect':
        raw=str(args[0]);path=Path(unquote(urlparse(raw).path).lstrip('/')if raw.startswith('file:')else raw).resolve()
        assert path.is_relative_to(PRIVATE)or(path==(BASE/'els_server/data/client/catalog.sqlite3').resolve()and'mode=ro'in raw and'immutable=1'in raw),str(path)
    if event.startswith('socket.')or event in('subprocess.Popen','os.system'):raise PermissionError('Offline private verification')
sys.addaudithook(audit)
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.seal_quests import quest_catalog,sequence,target
from els_server.storage.seal_quests import QuestState,QuestIncomplete
from els_server.protocol import quest_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.game_data import client_data

checks=[];findings=[]
def box(uid):return struct.pack('>QBBBIi',uid,0,0,0,0,0)
def item_use(uid,target_uid=0):return struct.pack('>QQiiIB',uid,target_uid,0,0,0,0)
def encode(events):
    if isinstance(events,dict):events=events['events']
    if not isinstance(events,(tuple,list)):events=[events]
    for event in events:encode_event(event)
    return events

class Consumers(unittest.TestCase):
    def setUp(self):
        self.path=PRIVATE/(self._testMethodName+'.sqlite3');prepare(self.path)
        ch=Characters(self.path,1).create('OwnAudit',1,self._testMethodName)
        self.uid=ch['uid'];self.account=LocalAccount(LocalState(self.path,self.uid));self.account.enable_characters()
        self.q=QuestState(self.path,self.uid,account_id=1,account_source_guard=self.guard);self.q.snapshot()
        self.sql('UPDATE characters SET level=99 WHERE uid=?',(self.uid,))
        self.sql('UPDATE reward_balances SET experience=?,ed=100000000 WHERE uid=?',(client_data().thresholds[-1],self.uid))
    def sql(self,query,args=()):
        with closing(sqlite3.connect(self.path))as db,db:return db.execute(query,args).fetchall()
    def guard(self,db):
        assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(self.uid,)).fetchone()==(1,)
    def items(self):
        with closing(sqlite3.connect(self.path))as db:return load_items(db,self.uid)
    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())
    def grant(self,template,quantity=1):
        with closing(sqlite3.connect(self.path))as db,db:
            return grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)],self.uid)
    def ready(self,qid):
        q=quest_catalog().quest(qid)
        for parent in sequence(q['QuestCondition']['m_vecBeforeQuestID']):
            if parent:self.sql('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(self.uid,parent,1,'{"explicit_parent_fixture":true}'))
        self.q.action('accept',dict(quest=qid,npc=10025),'accept-'+str(qid),lambda r:[])
        counts={s['m_iID']:target(s)for s in quest_catalog().objectives(qid)}
        self.sql('UPDATE character_quests SET objectives=?WHERE owner=?AND quest=?',(json.dumps(counts),self.uid,qid))
    def claim(self,qid,operation=None,fail=False):
        request=dict(quest=qid,npc=0,choices=(),flags=(0,0,0,0,0))
        def response(r):
            done=next(d for d in r['state']['completed']if d['id']==qid)
            events=[wire.reward_ack(qid,r['character'],self.account.get_location(),r['slots'],r['balances'],r['items'],r['updates'],consumed=r['consumed'],replayed=r['replayed'],completed_at=done['completed_at']),wire.initialization(r['state'])]
            encode(events)
            if fail:raise ValueError('owned late F5 encoding fault')
            return events
        return self.q.action('claim',request,operation or'claim-'+str(qid),response)
    def test_housing_task_and_furniture_gap(self):
        from els_server.storage import housing_access,housing_rooms,housing_layouts,furniture_boxes
        from els_server.protocol.housing_layout_messages import REQUEST,encode as layout_encode
        qid=26770
        for parent in sequence(quest_catalog().quest(qid)['QuestCondition']['m_vecBeforeQuestID']):
            if parent:self.sql('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(self.uid,parent,1,'{"explicit_parent_fixture":true}'))
        self.q.action('accept',dict(quest=qid,npc=10025),'housing-accept',lambda r:[])
        before=self.dump()
        with self.assertRaises(QuestIncomplete):self.claim(qid)
        self.assertEqual(before,self.dump())
        contract=self.grant(136034)[0]
        encode(housing_access.use(self.path,self.uid,1,item_use(contract['uid']),'housing-contract',self.guard))
        admission=housing_rooms.enter(self.path,self.uid,1,struct.pack('>Qi3fB',0,26000,0.,0.,0.,1),'housing-enter','owned-session',20000,self.guard)
        encode(admission['events'])
        self.assertEqual(next(r for r in self.q.snapshot()['active']if r['id']==qid)['objectives'],{26770:1})
        before=self.dump()
        with self.assertRaises(ValueError):self.claim(qid,fail=True)
        self.assertEqual(before,self.dump())
        result=self.claim(qid);rewards=[r for r in result['updates']if r['template']in(570001,570002,570014)]
        self.assertEqual({r['template']:r['count']for r in rewards},{570001:1,570002:1,570014:1})
        before=self.dump();self.claim(qid);self.assertEqual(before,self.dump())
        for item in rewards:
            # Original ground furniture position2, modern current layout record.
            request=([],[(item['uid'],(item['uid'],item['template'],2,(0.,0.,0.),0))],[],0,0,0)
            self.assertEqual(item['group'],25)
            encode(housing_layouts.save(self.path,self.uid,1,layout_encode(REQUEST,request),'place-'+str(item['template']),admission['generation'],admission['operation'],self.guard))
            before=self.dump()
            encode(housing_layouts.save(self.path,self.uid,1,layout_encode(REQUEST,request),'place-'+str(item['template']),admission['generation'],admission['operation'],self.guard))
            self.assertEqual(before,self.dump())
        # Counterexample: the later small-furniture box really produces supported furniture.
        small=self.grant(136039)[0]
        encode(furniture_boxes.perform(self.path,self.uid,1,box(small['uid']),'small-furniture',self.guard))
        modern=next(i for i in self.items()if i['template']==570011)
        request=([],[(modern['uid'],(modern['uid'],570011,2,(0.,0.,0.),0))],[],0,0,0)
        encode(housing_layouts.save(self.path,self.uid,1,layout_encode(REQUEST,request),'place-supported',admission['generation'],admission['operation'],self.guard))
        checks.append(dict(case='housing_actual_admission_to_claim',templates=[136034,136039,570001,570002,570014],objective75=True,exact_award=True,rollback=True,replay=True,quest3_native_group_and_layout_passed=True,small_box_layout_passed=True))

    def test_legacy_furniture_migration(self):
        from els_server.storage.inventory_state import InventoryState,InventoryFull,validate_plan
        from els_server.domain.furniture_rules import plan
        self.assertEqual({r['template']:r['quantity']for r in plan()},{570011:1,570012:1,570015:2,570016:1})
        self.ready(26770)
        # Recreate both the historical inventory rows and their original receipt.
        awarded=self.claim(26770)
        rewards=[i for i in awarded['updates']if i['template']in(570001,570002,570014)]
        original={i['uid']:i['template']for i in rewards}
        historical=json.loads(self.sql('SELECT reward_json FROM completed_quests WHERE owner=?AND quest=26770',(self.uid,))[0][0])
        for n,item in enumerate(rewards):
            self.sql('UPDATE inventory_items SET bag_group=4,slot=? WHERE uid=?',(n,item['uid']))
            saved=next(i for i in historical['items']if i['uid']==item['uid'])
            saved.update(group=4,slot=n)
        self.sql('UPDATE completed_quests SET reward_json=?WHERE owner=?AND quest=26770',(json.dumps(historical,sort_keys=True),self.uid))
        receipt_before=self.sql('SELECT * FROM completed_quests')
        self.assertTrue(all(i['group']==4 for i in historical['items']))
        # Slot0 is occupied by a separately owned furniture instance.
        occupied=self.grant(570001)[0]
        self.assertEqual(occupied['slot'],0)
        InventoryState(self.path,self.uid)
        migrated=[i for i in self.items()if i['uid']in original]
        self.assertEqual({i['uid']:i['template']for i in migrated},original)
        self.assertTrue(all(i['group']==25 for i in migrated))
        self.assertEqual(len({i['slot']for i in migrated+[occupied]}),4)
        self.assertEqual(self.sql('SELECT * FROM completed_quests'),receipt_before)
        before=self.dump();InventoryState(self.path,self.uid);self.assertEqual(before,self.dump())
        replay=self.claim(26770);self.assertEqual(before,self.dump())
        self.assertEqual({i['uid']for i in replay['updates']},set(original))
        self.assertTrue(all(i['group']==25 for i in replay['updates']))
        with self.assertRaises(ValueError):validate_plan([dict(template=570001,metadata=0,quantity=1,group=4)])
        # Restored legacy rows are discovered even after the migration audit exists.
        self.sql('UPDATE inventory_items SET bag_group=4,slot=0 WHERE uid=?',(rewards[0]['uid'],))
        InventoryState(self.path,self.uid)
        self.assertEqual(next(i for i in self.items()if i['uid']==rewards[0]['uid'])['group'],25)
        # A capacity failure rolls back all moves, retaining both items and receipts.
        used=sum(i['group']==25 for i in self.items())
        for _ in range(36-used):self.grant(570001)
        for n,item in enumerate(rewards[:2]):self.sql('UPDATE inventory_items SET bag_group=4,slot=? WHERE uid=?',(n,item['uid']))
        self.grant(570001) # Leave only one furniture slot for two legacy items.
        before=self.dump()
        with self.assertRaises(InventoryFull):InventoryState(self.path,self.uid)
        self.assertEqual(before,self.dump())
        checks.append(dict(case='legacy_furniture_migration',historical_group4_receipt=True,uids_preserved=True,receipts_unchanged=True,slot_collision=True,repeated_initialization=True,claim_replay_current_group25=True,restored_legacy_row=True,full_bag_atomic_rollback=True))

if __name__=='__main__':
    migration_only='--migration-only'in sys.argv
    suite=unittest.defaultTestLoader.loadTestsFromName('Consumers.test_legacy_furniture_migration',module=__import__(__name__))if migration_only else unittest.defaultTestLoader.loadTestsFromTestCase(Consumers)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    temp.cleanup()
    report=dict(ok=result.wasSuccessful(),base_release=POINT['release'],runtime=str(BASE),tests=result.testsRun,checks=checks,
                failures=[dict(test=str(t),trace=e)for t,e in result.failures+result.errors],private_SQL_removed=not PRIVATE.exists(),formal_SQL=False,network=False,natural_GUI=False)
    (OUT/('furniture-migration-validation.json'if migration_only else'furniture-validation.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(ok=report['ok'],checks=len(checks),private_SQL_removed=report['private_SQL_removed'])))
    sys.exit(0 if result.wasSuccessful()else 1)
