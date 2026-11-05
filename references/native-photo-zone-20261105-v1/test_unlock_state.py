"""Owned SQL: original ticket use, durable scope and rollback boundaries."""
import bootstrap as env
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,sqlite3,struct,tempfile,time,unittest,sys
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import photo_zone_state as state
from els_server.protocol import photo_zone_messages as wire

class UnlockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='owned-studio-unlock-',dir=env.HERE)
        self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'own.sqlite3';prepare(self.path)
        self.owners=[]
        for index in(1,2):
            roster=Characters(self.path,index);uid=roster.create('OwnStudio'+str(index),index,'owned-studio-'+str(index))['uid']
            local=LocalAccount(LocalState(self.path,uid),account_id=index);local.enable_characters(characters=roster);local.get_inventory_snapshot();self.owners.append(uid)
        self.owner=self.owners[0]
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            self.ticket=grant_items(db,[dict(template=288494,metadata=2,group=4,quantity=2)],self.owner)[0]
        self.payload=struct.pack('>QH',self.ticket['uid'],744)
    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())
    def count(self):
        with closing(sqlite3.connect(self.path))as db:return sum(i['count']for i in load_items(db,self.owner)if i['template']==288494)
    def opened(self,uid=None,account=1):
        with closing(sqlite3.connect(self.path))as db:
            db.execute('BEGIN');return state.snapshot(db,uid or self.owner,account)
    def guard(self,db):state.require_owner(db,self.owner,1)
    def use(self,payload=None,operation='owned-studio-use',guard=None):
        return state.use(self.path,self.owner,1,self.payload if payload is None else payload,operation,guard or self.guard)
    def test_one_ticket_opens_one_map_and_replay_does_not_consume_again(self):
        self.assertNotIn(744,self.opened());answer=self.use()
        self.assertEqual(self.count(),1);self.assertIn(744,self.opened())
        self.assertEqual([e.kind for e in answer],[0x5b9,0x5ba])
        before=self.dump();self.use();self.assertEqual(before,self.dump())
        with self.assertRaises(ValueError):self.use(struct.pack('>QH',self.ticket['uid'],692))
        with self.assertRaises(ValueError):self.use(operation='owned-repeat-new-request')
        self.assertEqual(before,self.dump())
        self.assertNotIn(744,self.opened(self.owners[1],2))
    def test_invalid_target_and_foreign_uid_preserve_ticket(self):
        before=self.dump()
        for world in(689,1153,65535):
            with self.assertRaises(ValueError):self.use(struct.pack('>QH',self.ticket['uid'],world))
        with self.assertRaises(ValueError):self.use(struct.pack('>QH',self.ticket['uid']+100000,744))
        self.assertEqual(before,self.dump())
    def test_native_encoder_failure_rolls_back_ticket_map_and_receipt(self):
        before=self.dump()
        with patch.object(wire,'unlocked_ack',side_effect=ValueError('Owned encoder fault')):
            with self.assertRaises(ValueError):self.use()
        self.assertEqual(before,self.dump());self.assertEqual(self.count(),2)
    def test_actor_change_after_encoding_rolls_back_every_write(self):
        before=self.dump();calls=[]
        def guard(db):
            self.guard(db);calls.append(1)
            if len(calls)>1:raise ValueError('Owned selected actor changed')
        with self.assertRaises(ValueError):self.use(guard=guard)
        self.assertEqual(before,self.dump())
    def test_completed_original_task_unlocks_without_ticket_or_shared_ownership(self):
        # This fixture supplies a completed shared-engine row, not a client
        # counter or a claim that a natural dungeon battle was executed.
        from els_server.storage.seal_quests import ensure
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');ensure(db)
            db.execute('INSERT INTO completed_quests VALUES(?,?,?,?)',(self.owner,31011,int(time.time()),'{}'))
        self.assertIn(744,self.opened());self.assertNotIn(744,self.opened(self.owners[1],2))
        before=self.dump()
        with self.assertRaises(ValueError):self.use()
        self.assertEqual(before,self.dump());self.assertEqual(self.count(),2)
    def test_replay_restores_current_replacement_in_a_freed_source_slot(self):
        self.use()
        from els_server.storage.item_instances import remove
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            current=next(i for i in load_items(db,self.owner)if i['uid']==self.ticket['uid'])
            remove(db,self.owner,current)
            replacement=grant_items(db,[dict(template=288495,metadata=0,group=4,quantity=1)],self.owner)[0]
        self.assertEqual((replacement['group'],replacement['slot']),(self.ticket['group'],self.ticket['slot']))
        before=self.dump();answer=self.use()
        from els_server.domain.fashion_state import record
        self.assertIn(record(replacement),answer[0].payload)
        self.assertEqual(before,self.dump())
    def test_shared_quest_engine_counts_thirty_five_distinct_accepted_clears(self):
        from els_server.storage.seal_quests import QuestState,QuestIncomplete
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(self.owner,))
        LocalState(self.path,self.owner).save(20001,0,0,(1.,2.,3.))
        q=QuestState(self.path,self.owner,account_id=1,account_source_guard=self.guard)
        request=dict(quest=31011,npc=10003)
        q.action('accept',request,'owned-photo-accept',lambda value:[])
        event=dict(kind='clear',dungeon=33901,level=99)
        for index in range(34):
            q.record('owned-photo-clear-'+str(index),event,('owned-proof-'+str(index)).encode())
        q.record('owned-photo-clear-33',event,b'owned-proof-33')
        with self.assertRaises(QuestIncomplete):q.action('claim',request,'owned-photo-claim',lambda value:[])
        self.assertNotIn(744,self.opened())
        q.record('owned-photo-clear-34',event,b'owned-proof-34')
        before=self.count();q.action('claim',request,'owned-photo-claim',lambda value:[])
        self.assertIn(744,self.opened());self.assertEqual(self.count(),before)
        saved=self.dump();q.action('claim',request,'owned-photo-claim',lambda value:[])
        self.assertEqual(saved,self.dump())
    def test_shared_quest_encoder_cannot_commit_after_its_actor_guard_changes(self):
        from els_server.storage.seal_quests import QuestState
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(self.owner,))
        LocalState(self.path,self.owner).save(20001,0,0,(1.,2.,3.))
        calls=[]
        def guard(db):
            self.guard(db);calls.append(1)
            if len(calls)>1:raise ValueError('Owned obsolete quest actor')
        q=QuestState(self.path,self.owner,account_id=1,account_source_guard=guard)
        before=self.dump()
        with self.assertRaises(ValueError):q.action('accept',dict(quest=31011,npc=10003),'owned-photo-late-accept',lambda value:[])
        self.assertEqual(before,self.dump())

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:],module=sys.modules[__name__])if len(sys.argv)>1 else unittest.defaultTestLoader.loadTestsFromTestCase(UnlockTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    target=env.HERE/('unlock-state-'+str(time.time_ns())+'.json')
    target.write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,
        production_database_access=False,natural_battle=False),indent=2),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
