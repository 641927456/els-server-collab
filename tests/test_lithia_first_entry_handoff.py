"""Disposable same-owner protocol reproduction; no client or formal DB access."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from types import SimpleNamespace
import json,os,sqlite3,struct,sys,tempfile,unittest

CANDIDATE=True
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.roster_account import RosterAccount
from els_server.storage.local_state import LocalState
from els_server.storage.accounts import Accounts
from els_server.storage.seal_quests import QuestState
from els_server.domain.quest_flow import initialization
from els_server.protocol.protocol_codec import Event
from els_server.domain.dungeon_lifecycle import death_report
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'private-game.sqlite3'
        LocalAccount(LocalState(self.path)).enable_characters()
        self.accounts=Accounts(Path(self.tmp.name)/'private-accounts.sqlite3')
        reg=self.accounts.register('lithiaflow','Disposable-Test-Only')
        self.aid=reg['account_id'];self.roster=RosterAccount(self.path,self.aid,'lithiaflow')
        c=self.roster.characters.create('LithiaFlow',15,'lithia-flow-create')
        self.a=self.roster.for_character(c['uid']);self.uid=c['uid'];self.seq=0
        self.q=QuestState(self.path,self.uid,account_id=self.aid)
        self.s=LocalSession(self.a,True,True,'dx11_260923',npc_slot_test=True,gate_test=True,
                            population_test=True,clear_test=True,reward_test=True,item_test=True)
        self.s.role='game';self.s.phase='characters_ready';initialization(self.s)
        self.s.phase='map_loading'
        self.send(0x225,struct.pack('>iB',20014,0))
        from els_server.domain.town_travel import catalog
        xyz=catalog()['towns']['20014']['xyz']
        reply=self.send(0x227,struct.pack('>fffBH',*xyz,0,0))
        self.assertTrue(any(e.kind==0x228 for e in reply))
        self.assertEqual(self.s.phase,'town_ready')
        self.initial_assets=self.a.get_inventory_snapshot()

    def send(self,kind,payload):
        self.seq+=1
        return self.s.handle(Event(0x202,performers=(0,),kind=kind,payload=payload),self.seq)

    def claim(self,qid):
        reply=self.send(0xf4,struct.pack('>iiI5B',qid,0,0,0,0,1,1,0))
        self.assertEqual(reply[0].kind,0xf5);self.assertEqual(reply[0].payload[:4],bytes(4))
        return reply

    def town_prefix(self):
        # These are three distinct original quests, not three awards for one ID.
        for q in (28000,28010,28020):self.claim(q)
        self.send(0xfd,struct.pack('>i',10394));self.claim(28030)
        self.assertEqual(self.q.completed(),frozenset((28000,28010,28020,28030)))

    def enter(self,load=True):
        self.assertEqual(self.send(0x7d4,struct.pack('>ii',2,35250))[0].payload[:4],bytes(4))
        self.assertEqual(self.send(0x37f,ENTRY)[0].payload[:4],bytes(4))
        self.send(0x91,struct.pack('>ii',100,0))
        self.assertEqual(self.s.phase,'dungeon_active')
        return self.send(0xb3,bytes(9)) if load else []

    def retirement(self,hp,key):
        b=struct.pack('>iBQQ6fBf',key,255,2**64-1,2**64-1,0,0,0,-2743.94,8230,0,1,hp)
        b+=struct.pack('>IIQBQIQ',0,1,self.uid,0,0,0,0)
        return Event(0x202,performers=(0,),kind=0xad,payload=b)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return tuple(db.iterdump())

    def test_incident_without_manual_entry_task_claim(self):
        self.town_prefix();assets=self.a.get_inventory_snapshot();reply=self.enter()
        if not CANDIDATE:
            self.assertNotIn(28040,self.q.completed())
            self.assertEqual(next(r for r in self.q.snapshot()['active'] if r['id']==28040)['objectives'],{28040:1})
            event=self.retirement(500,1)
            self.assertEqual(self.s.handle(event,self.seq+1),[])
            self.assertFalse(self.s.dungeon_run.defeated);return
        self.assertIn(28040,self.q.completed())
        self.assertIn(28050,{r['id'] for r in self.q.snapshot()['active']})
        self.assertEqual(self.a.get_inventory_snapshot()['items'],assets['items'])
        self.assertTrue(any(e.kind==0xf5 and struct.unpack_from('>i',e.payload,4)[0]==28040 for e in reply))
        event=self.retirement(500,1);reply=self.s.handle(event,self.seq+1)
        self.assertEqual([e.kind for e in reply][:2],[0xae,0xaf]);self.assertFalse(self.s.part_end_notified)
        self.claim(28050)  # Native F3/AutoClearQuest response, no invented death.
        gate=self.retirement(1000,0);reply=self.s.handle(gate,self.seq+2)
        self.assertEqual([e.kind for e in reply][:2],[0xae,0xaf]);self.assertIn(0xba,[e.kind for e in reply])
        self.assertTrue(self.s.part_end_notified)
        self.claim(28060)
        self.assertEqual(self.send(0xbb,b'\0')[0].kind,0xbc)
        self.assertEqual(self.s.dungeon_run.part,1)
        cold=QuestState(self.path,self.uid,account_id=self.aid)
        self.assertTrue({28040,28050,28060}<=cold.completed())

    def test_original_town_claim_retry_does_not_repeat_awards(self):
        self.claim(28000);assets=self.a.get_inventory_snapshot();before=self.q.snapshot()
        first=self.claim(28000);second=self.claim(28000)
        self.assertEqual(self.a.get_inventory_snapshot(),assets);self.assertEqual(self.q.snapshot(),before)
        self.assertFalse(any(e.kind==0xf0 for e in first+second))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM completed_quests WHERE owner=? AND quest=28000',(self.uid,)).fetchone(),(1,))

    @unittest.skipUnless(CANDIDATE,'new candidate check')
    def test_preencoding_failure_rolls_back_entry_count_claim_and_successor(self):
        self.town_prefix();self.enter(load=False);before=self.dump()
        original=__import__('els_server.protocol.protocol_codec',fromlist=['encode_event']).encode_event
        def fail(e,*a,**kw):
            if e.kind==0xf5:raise ValueError('entry-encoder-failure')
            return original(e,*a,**kw)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'entry-encoder-failure'):self.send(0xb3,bytes(9))
        self.assertEqual(self.dump(),before)
        self.assertNotIn(28040,self.q.completed())
        # A later original B3 can retry after SQL/encoding rollback.
        self.send(0xb3,bytes(9));self.assertIn(28040,self.q.completed())

    @unittest.skipUnless(CANDIDATE,'new candidate check')
    def test_loaded_entry_retry_is_idempotent_and_does_not_reset_successor(self):
        self.town_prefix();self.enter();before=self.dump();assets=self.a.get_inventory_snapshot()
        for _ in range(3):self.send(0xb3,bytes(9))
        self.assertEqual(self.dump(),before);self.assertEqual(self.a.get_inventory_snapshot(),assets)

    @unittest.skipUnless(CANDIDATE,'new candidate check')
    def test_shared_action_encoder_failure_is_owned_by_outer_transaction(self):
        before=self.dump()
        try:
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('BEGIN IMMEDIATE')
                self.q.action('claim',dict(quest=28000,npc=0,flags=(0,0,1,1,0)),
                    'outer-claim',lambda r: (_ for _ in ()).throw(ValueError('outer-encoder')),transaction=db)
        except ValueError as ex:self.assertEqual(str(ex),'outer-encoder')
        else:self.fail('missing encoder failure')
        self.assertEqual(self.dump(),before)

    @unittest.skipUnless(CANDIDATE,'new candidate check')
    def test_first_entry_rejects_stale_and_unsynchronized_context(self):
        self.town_prefix();self.enter(load=False)
        from els_server.domain.lithia_first_entry import record_visit
        run=self.s.dungeon_run;base='discovery:'+run.run_id+':0:0:0'
        proof=(run.run_id+':'+run.graph['source_sha256']+':0:0').encode()
        event=dict(kind='visit_dungeon',dungeon=35250,level=1)
        before=self.dump()
        with self.assertRaises(ValueError):record_visit(self.s,run,self.q,base,event,proof)
        self.assertEqual(self.dump(),before)
        self.s.dungeon_substage_synced=True;old=self.s.reward_run_id;self.s.reward_run_id='stale'
        with self.assertRaises(ValueError):record_visit(self.s,run,self.q,base,event,proof)
        self.s.reward_run_id=old;self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main()
