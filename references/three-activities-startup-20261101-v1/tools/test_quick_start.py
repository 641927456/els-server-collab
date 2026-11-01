"""Controlled SQL/protocol integration; never connects to the production server."""
import hashlib,json,sqlite3,struct,sys,tempfile,unittest
from pathlib import Path
from contextlib import closing
import gc
from unittest.mock import patch
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE/'runtime'))
RESUME=None
if '--resume-db' in sys.argv:
    pos=sys.argv.index('--resume-db');RESUME=Path(sys.argv[pos+1]);del sys.argv[pos:pos+2]
from els_server.domain.local_session import LocalAccount
import els_server;assert Path(els_server.__file__).resolve().is_relative_to(Path(__file__).resolve().parent/'runtime'),els_server.__file__
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.storage.characters import Characters
from els_server.domain.quick_start import QUESTS,career_transition,catalog,selected
from els_server.domain.character_rules import CLASSES
from els_server.domain.careers import PARENTS
from els_server.storage.quick_start import change_career,enrollment
from els_server.protocol import quest_messages as wire
from els_server.protocol.protocol_codec import encode_event

class QuickStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RESUME is not None:
            cls.tmp=None;cls.path=RESUME;cls.root=LocalAccount(LocalState(cls.path));cls.root.enable_characters()
            cls.created=next(c for c in cls.root.characters.list()if c['name']=='QuickMain');cls.uid=cls.created['uid']
            cls.account=cls.root.for_character(cls.uid);cls.q=QuestState(cls.path,cls.uid,account_id=1,account_source_guard=lambda db:None);return
        cls.tmp=tempfile.TemporaryDirectory(dir=HERE,prefix='owned-tests-')
        cls.path=Path(cls.tmp.name)/'game.sqlite3'
        cls.root=LocalAccount(LocalState(cls.path));cls.root.enable_characters()
        cls.created=cls.root.characters.create('QuickMain',1,'create-main',quick_start=True)
        cls.uid=cls.created['uid'];cls.account=cls.root.for_character(cls.uid)
        cls.q=QuestState(cls.path,cls.uid,account_id=1,account_source_guard=lambda db:None);cls.serial=0

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        if cls.tmp is not None:cls.tmp.cleanup()

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return '\n'.join(db.iterdump())

    def claim(self,qid,operation,encode=None):
        def default(result):
            done=next(r for r in result['state']['completed']if r['id']==qid)
            events=[wire.reward_ack(qid,result['character'],self.account.get_location(),result['slots'],result['balances'],result['items'],result['updates'],consumed=result['consumed'],completed_at=done['completed_at'])]
            for event in events:encode_event(event)
            return events
        return self.q.action('claim',dict(quest=qid,npc=0),operation,encode or default)

    def career(self,target,operation,encode=None):
        from els_server.storage.career_shop import notifications
        def prepare(db):
            self.assertEqual(db.execute('SELECT account_id FROM character_owners WHERE uid=?',(self.uid,)).fetchone(),(1,))
        def default(db,before,after,replayed,retired):
            events=notifications(db,self.uid,before,self.account.get_location(),before,after,replayed)
            for event in events:encode_event(event)
            return events
        return change_career(self.path,self.uid,1,target,operation,prepare,encode or default)

    def test_01_enrollment_retry_and_account_boundary(self):
        self.assertTrue(selected({578:0}));self.assertFalse(selected({}))
        with self.assertRaises(ValueError):selected({578:1})
        self.assertEqual(self.root.characters.create('QuickMain',1,'create-main',quick_start=True)['uid'],self.uid)
        before=self.dump()
        with self.assertRaises(ValueError):self.root.characters.create('SecondQuick',2,'second-event',quick_start=True)
        self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):QuestState(self.path,self.uid,account_id=2).snapshot()
        ordinary=self.root.characters.create('Ordinary',2,'ordinary-create')
        with closing(sqlite3.connect(self.path))as db:
            from els_server.storage.seal_quests import load_character
            from els_server.domain.seal_quests import require_eligible,quest_catalog
            c=load_character(db,ordinary['uid'],1)
            with self.assertRaises(ValueError):require_eligible(c,quest_catalog().quest(QUESTS[0]),set(),[])
        another=Characters(self.path,2).create('OtherQuick',3,'other-create',quick_start=True)
        self.assertNotEqual(another['uid'],self.uid)

    def test_02_chain_levels_rollback_replay_and_original_careers(self):
        before=self.dump()
        with self.assertRaises(ValueError):self.claim(QUESTS[0],'early-claim')
        self.assertEqual(self.dump(),before)
        expected_levels=(15,35,70,99,99)
        maps=(30000,30102,30252,33202,34060)
        for index,qid in enumerate(QUESTS):
            active=self.q.snapshot()['active'];self.assertEqual([r['id']for r in active],[qid])
            event=dict(kind='kill'if index==0 else'clear',dungeon=maps[index],level=self.account.character()['level'],rank=None)
            if index==0:event['npc']=5
            wrong=dict(event,dungeon=30080)
            self.assertEqual(self.q.record('wrong-'+str(qid),wrong,b'wrong-proof'),[])
            self.q.record('complete-'+str(qid),event,b'accepted-proof')
            self.assertEqual(self.q.record('complete-'+str(qid),event,b'accepted-proof'),[])
            if index==0:
                before=self.dump()
                with self.assertRaises(RuntimeError):self.claim(qid,'encode-fails',lambda r:(_ for _ in ()).throw(RuntimeError('encode failed')))
                self.assertEqual(self.dump(),before)
            self.claim(qid,'claim-'+str(qid));after=self.dump()
            self.claim(qid,'claim-'+str(qid));self.assertEqual(self.dump(),after)
            self.assertEqual(self.account.character()['level'],expected_levels[index])
            if index in(0,1,3):
                current=self.account.character()['unit_class']
                target=next(c for c,p in PARENTS.items()if p==current and c in CLASSES)
                self.career(target,'career-'+str(index));after=self.dump()
                self.career(target,'career-'+str(index));self.assertEqual(self.dump(),after)
            elif index==2:
                self.career(self.account.character()['unit_class'],'career-transcendence')
                self.assertTrue(self.account.character()['transcendence'])
        self.assertEqual(self.q.snapshot()['active'],[])
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT ed FROM reward_balances WHERE uid=?',(self.uid,)).fetchone(),(10000000,))
            self.assertEqual(db.execute("SELECT count(*) FROM completed_quests WHERE owner=? AND reward_json LIKE '%quick_start_skip%'",(self.uid,)).fetchone()[0],248)

    def test_03_fixed_bundles_and_master_ticket_cold_read(self):
        from els_server.storage.fixed_cubes import open_cube
        from els_server.storage.careers import use_career_item
        for template in(720720,720721,720818):
            item=next(i for i in self.account.get_inventory_snapshot()['items']if i['template']==template)
            # Native196 use_request uses UID, three flags, option and choices.
            from els_server.protocol.ice_messages import use_request
            payload=struct.pack('>QBBBII',item['uid'],0,0,0,0,1)
            use_request(payload)
            before=self.account.get_inventory_snapshot()
            events=open_cube(self.path,self.uid,template,payload,'open-'+str(template),account_id=1,prepare=lambda db:None)
            for event in events:encode_event(event)
            after=self.dump()
            open_cube(self.path,self.uid,template,payload,'open-'+str(template),account_id=1,prepare=lambda db:None)
            self.assertEqual(self.dump(),after)
        ticket=next(i for i in self.account.get_inventory_snapshot()['items']if i['template']==719707)
        payload=struct.pack('>QQiiIB',ticket['uid'],0,0,0,0,0)
        use_career_item(self.path,self.uid,payload,'master-ticket')
        after=self.dump();use_career_item(self.path,self.uid,payload,'master-ticket');self.assertEqual(self.dump(),after)
        cold=Characters(self.path,1).get(self.uid)
        self.assertTrue(cold['master']);self.assertEqual(cold['artifact']['template'],1)
        self.assertEqual(cold['artifact']['evolution'],1)
        self.assertFalse(any(i['template']==719707 for i in self.account.get_inventory_snapshot()['items']))

if __name__=='__main__':unittest.main(verbosity=2)
