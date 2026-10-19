"""Region chains use real quest transactions; offline progress proofs only."""
import sqlite3,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.region_quests import region_catalog,account_dungeon_allowed,sequence
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.protocol.protocol_codec import Event
from els_server.protocol.quest_messages import initialization

class RegionQuestFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'region.db';self.a=LocalAccount(LocalState(self.path));self.a.enable_characters()
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=1001')
        self.s=LocalSession(self.a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
            npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        self.s.role='game';self.s.phase='town_ready';self.q=QuestState(self.path,account_id=1);self.counter=0

    def action(self,kind,qid):
        self.counter+=1
        body=struct.pack('>ii',qid,10025) if kind==0xee else struct.pack('>iiI5B',qid,10025,0,0,1,1,1,0)
        return self.s.handle(Event(0x202,performers=(0,),kind=kind,payload=body),self.counter)

    def record(self,qid,dungeon):
        self.counter+=1
        return self.q.record('test:'+str(self.counter),dict(kind='clear',dungeon=dungeon,level=99,rank=None),
            ('offline-region-test:'+str(qid)+':'+str(self.counter)).encode())

    def test_all_thirteen_tasks_claim_restore_and_unlock_in_order(self):
        c=region_catalog();completed=set();awards=[]
        for qid,q in sorted(c.quest_definitions().items()):
            regions=[int(i) for i,r in c.data['regions'].items() if r['requirement'].get('RequireQuestID')==qid]
            for region in regions:self.assertFalse(c.region_allowed(region,self.a.character(),self.q.completed()))
            self.assertEqual([e.kind for e in self.action(0xee,qid)],[0xef,0xf0])
            self.assertNotEqual(self.action(0xf4,qid)[0].payload[:4],bytes(4))
            for sid in sequence(q['m_vecSubQuest']):
                sub=c.subquest_definitions()[sid];target=sequence(sub['m_ClearCondition']['m_eDungeonID'])[0]
                self.assertEqual(self.record(qid,123456),[])
                self.assertEqual(self.record(qid,target)[0].kind,0xf3)
            response=self.action(0xf4,qid)
            self.assertEqual([e.kind for e in response],[0xf5,0x2b,0x55b])
            self.assertEqual(response[0].payload[:4],bytes(4));completed.add(qid)
            self.assertEqual(self.q.completed(),completed)
            for region in regions:self.assertTrue(c.region_allowed(region,self.a.character(),self.q.completed()))
            before=self.a.get_inventory_snapshot()
            self.assertEqual(self.action(0xf4,qid)[0].payload[:4],bytes(4))
            self.assertEqual(self.a.get_inventory_snapshot(),before)
            reopened=QuestState(self.path,account_id=1)
            self.assertEqual(reopened.completed(),completed)
            self.assertEqual(initialization(reopened.snapshot()).payload,initialization(self.q.snapshot()).payload)
        items=self.a.get_inventory_snapshot()['items']
        self.assertEqual(sum(i['count'] for i in items if i['template']==118655),1)
        self.assertEqual(self.q.snapshot()['active'],[])

    def test_session_refuses_locked_map_then_accepts_after_actual_claim(self):
        request=Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,34090))
        self.assertEqual(self.s.handle(request)[0].payload[:4],struct.pack('>i',2224))
        self.action(0xee,26640);self.record(26640,34060)
        # Completed objectives are not a claimed task receipt.
        self.assertFalse(account_dungeon_allowed(self.a,34090))
        self.action(0xf4,26640)
        self.assertTrue(account_dungeon_allowed(self.a,34090))
        self.assertEqual(self.s.handle(request)[0].payload[:4],bytes(4))
        # Re-check after the queued selection: a level/class change cannot
        # retain an earlier successful entrance ticket.
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE characters SET level=98 WHERE uid=1001')
        from tests.test_dungeon_routes import ENTRY
        reply=self.s.handle(Event(0x202,kind=0x382,payload=ENTRY))
        self.assertEqual(reply[0].payload[:4],struct.pack('>i',-1))
        self.assertEqual(self.s.phase,'town_ready')

    def test_all_thirteen_tasks_via_admitted_dungeon_sessions(self):
        from tests.test_dungeon_routes import ENTRY,load,finish
        from els_server.domain.dungeon_routes import route_catalog
        from els_server.domain.dungeon_rotation import tower_encounter,selected
        c=region_catalog();maps=[]
        for qid,q in sorted(c.quest_definitions().items()):
            self.assertEqual(self.action(0xee,qid)[0].payload,bytes(4))
            sid=sequence(q['m_vecSubQuest'])[0]
            candidates=sequence(c.subquest_definitions()[sid]['m_ClearCondition']['m_eDungeonID'])
            admitted=[i for i in candidates if route_catalog().supports(i) and (not tower_encounter(i) or selected(i))]
            self.assertTrue(admitted,qid)
            identity=35800 if 35800 in admitted else admitted[0];maps.append(identity)
            from els_server.game_data import client_data
            single=1 in client_data().dungeon(identity).get('DUNGEON_CHECK_CONDITION',{}).values()
            mode=2 if single else 1;request=0x37f if single else 0x382
            self.assertEqual(self.s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',mode,identity)))[0].payload,struct.pack('>ii',0,mode))
            self.assertEqual(self.s.handle(Event(0x202,kind=request,payload=ENTRY))[0].payload[:4],bytes(4))
            self.s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))
            clock=[0.0];self.s.dungeon_run.clock=lambda:clock[0];load(self.s)
            finish(self.s,clock)
            # No direct QuestState.record call: the normal authenticated death
            # and clear dispatch must produce the task progress notification.
            row=next(r for r in self.q.snapshot()['active'] if r['id']==qid)
            self.assertEqual(row['objectives'][sid],1,qid)
            self.assertEqual(self.action(0xf4,qid)[0].payload[:4],bytes(4))
            self.s.handle(Event(0x202,kind=0x225,payload=struct.pack('>iB',20000,0)))
            self.s.handle(Event(0x202,kind=0x227,payload=struct.pack('>fffBH',0,0,0,0,0)))
            self.assertEqual(self.s.phase,'town_ready')
        self.assertEqual(self.q.completed(),set(c.quest_definitions()))
        # Gold Castle is now admitted and is the first eligible map in this
        # region; the previous catalog selected 35090 instead.
        self.assertTrue({35080,35090}&set(maps));self.assertIn(35800,maps)

if __name__=='__main__':unittest.main()
