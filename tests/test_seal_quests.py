"""Native task lifecycle against temporary saves, including rollback/retries."""
import json,sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.domain.seal_quests import quest_catalog,seal_catalog,sequence,target,require_eligible,objective_increment,appropriate_level_range
from els_server.protocol import quest_messages as wire
from els_server.protocol.protocol_codec import Event

class SealQuestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.db';self.a=LocalAccount(LocalState(self.path));self.a.enable_characters()
        self.q=QuestState(self.path,account_id=1);self.q.snapshot();self.seq=0
        self.s=LocalSession(self.a,enter_town=True,client_build='dx11_260923');self.s.item_test=True;self.s.role='game';self.s.phase='town_ready'
        self.set_class(100,30)

    def set_class(self,cls,level=99,uid=1001,tc=False,master=False):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=?,level=?,transcendence=?,master=? WHERE uid=?',(cls,level,tc,master,uid))
            if master:
                typ=db.execute('SELECT unit_type FROM characters WHERE uid=?',(uid,)).fetchone()[0]
                db.execute("INSERT OR REPLACE INTO character_artifacts VALUES (?,?,1,1,0,'[0,0,0,0]')",(uid,typ))

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def action(self,kind,qid):
        self.seq+=1;q=quest_catalog().quest(qid)
        payload=struct.pack('>ii',qid,10025) if kind==0xee else struct.pack('>iiI5B',qid,q['m_eEndNPCID'],0,0,1,1,1,0) if kind==0xf4 else struct.pack('>i',qid)
        return self.s.handle(Event(0x202,performers=(0,),kind=kind,payload=payload),self.seq)

    def record(self,kind,dungeon,**fields):
        self.seq+=1
        return self.q.record('event-'+str(self.seq),dict(kind=kind,dungeon=dungeon,level=self.a.character()['level'],**fields),('proof-'+str(self.seq)).encode())

    def first_completed(self):
        self.assertEqual([e.kind for e in self.action(0xee,6980)],[0xef,0xf0])
        self.record('clear',30252,rank=None)
        self.assertEqual(self.q.snapshot()['active'][0]['objectives'],{47293:1})
        self.assertEqual(self.action(0xf4,6980)[0].payload[:4],bytes(4))

    def book_ready(self):
        self.first_completed();self.action(0xee,6990)
        s=quest_catalog().objectives(6990)[0];c=s['m_ClearCondition']
        self.record('kill',sequence(c['m_eDungeonID'])[0],npc=sequence(c['m_eKillNPCID'])[0])

    def test_full_native_chain_rewards_book_only_then_item_use_unseals(self):
        self.book_ready();reply=self.action(0xf4,6990)
        self.assertEqual([e.kind for e in reply],[0xf5,0x2b,0x55b]);self.assertEqual(reply[0].payload[:4],bytes(4))
        self.assertIn(6990,self.q.completed());self.assertEqual(self.a.character()['skill_seal_groups'],())
        book=next(i for i in self.a.get_inventory_snapshot()['items'] if i['template']==276289)
        self.seq+=1;payload=struct.pack('>QQiiIB',book['uid'],0,0,0,0,0)
        result=self.s.handle(Event(0x202,kind=0x219,payload=payload),self.seq)
        self.assertEqual([e.kind for e in result],[0x21a,0x131,0x55b]);self.assertEqual(self.a.character()['skill_seal_groups'],(2,))
        reopened=QuestState(self.path,account_id=1)
        self.assertEqual(reopened.completed(),{6980,6990});self.assertEqual(reopened.snapshot()['active'],[])

    def test_early_claim_level_class_predecessor_and_bad_wire_rejected(self):
        before=self.dump()
        self.assertNotEqual(self.action(0xee,6990)[0].payload,bytes(4));self.assertEqual(self.dump(),before)
        self.set_class(100,29);before=self.dump()
        self.assertNotEqual(self.action(0xee,6980)[0].payload,bytes(4));self.assertEqual(self.dump(),before)
        self.set_class(101,30);before=self.dump()
        self.assertNotEqual(self.action(0xee,6980)[0].payload,bytes(4));self.assertEqual(self.dump(),before)
        self.set_class(100,30);self.action(0xee,6980);before=self.dump()
        self.assertEqual(self.action(0xf4,6980)[0].payload[:4],struct.pack('>i',187));self.assertEqual(self.dump(),before)
        for kind,payload in [(0xee,b''),(0xfa,b'\0'*5),(0xf4,struct.pack('>iiI5B',6980,10017,1,0,1,1,1,0))]:
            with self.assertRaises(ValueError):wire.request(kind,payload)

    def test_clear_exclusions_level_policy_kill_filters_and_rank_are_preserved(self):
        self.action(0xee,6980)
        self.assertEqual(self.record('clear',30000,rank=9),[])
        self.assertEqual(self.record('clear',34000,rank=9),[])
        self.assertEqual(self.record('kill',30252,npc=238),[])
        self.assertEqual(self.q.snapshot()['active'][0]['objectives'][47293],0)
        event=dict(kind='clear',dungeon=30142,level=30,rank=None)
        sub=quest_catalog().subquests[6970]
        self.assertEqual(objective_increment(sub,event,b'p'),0)
        self.assertEqual(objective_increment(sub,dict(event,rank=4),b'p'),0)
        self.assertEqual(objective_increment(sub,dict(event,rank=5),b'p'),1)
        for rank in (0,9,99,-1,True,5.0,'S'):
            self.assertEqual(objective_increment(sub,dict(event,rank=rank),b'p'),0,rank)

    def test_reward_failure_codes_distinguish_missing_task_and_incomplete_objectives(self):
        before=self.dump()
        self.assertEqual(struct.unpack_from('>i',self.action(0xf4,6980)[0].payload)[0],2005)
        self.assertEqual(self.dump(),before)
        self.action(0xee,6980);before=self.dump()
        self.assertEqual(struct.unpack_from('>i',self.action(0xf4,6980)[0].payload)[0],187)
        self.assertEqual(self.dump(),before)
        self.s.phase='new'
        self.assertEqual(struct.unpack_from('>i',self.action(0xf4,6980)[0].payload)[0],2005)
        self.assertEqual(self.dump(),before)

    def test_suitable_level_uses_native_marker_and_preserves_explicit_zero(self):
        from els_server.game_data import client_data
        d=client_data().dungeon(30242)
        self.assertEqual((d['m_MinLevel'],d['m_MaxLevel']),(28,30))
        self.assertNotIn('m_SuitableLevelFixValue',d)
        self.assertEqual(appropriate_level_range(d),(23,32))
        sub=quest_catalog().subquests[47293]
        for level,expected in ((22,0),(23,1),(28,1),(30,1),(32,1),(33,0)):
            event=dict(kind='clear',dungeon=30242,level=level,rank=None)
            self.assertEqual(objective_increment(sub,event,b'accepted'),expected)
        # A resource override of zero is not the same as a missing field.
        self.assertEqual(appropriate_level_range(dict(d,m_SuitableLevelFixValue=0)),(28,32))
        zero=client_data().dungeon(33031)
        self.assertEqual(zero['m_SuitableLevelFixValue'],0)
        self.assertEqual(appropriate_level_range(zero),(99,101))
        self.assertEqual(objective_increment(sub,dict(kind='clear',dungeon=33031,level=98),b'accepted'),0)
        self.assertEqual(objective_increment(sub,dict(kind='clear',dungeon=33031,level=99),b'accepted'),1)
        for dungeon in sequence(sub['m_ClearCondition']['m_eExceptionDungeonID']):
            self.assertEqual(objective_increment(sub,dict(kind='clear',dungeon=dungeon,level=99),b'accepted'),0)

    def test_appropriate_clear_above_displayed_max_updates_claim_and_restore(self):
        self.set_class(100,32)
        self.assertEqual(self.action(0xee,6980)[0].payload,bytes(4))
        # A server clear fixture at max+2 used to be dropped by the
        # candidate-filter interval even though the native marker is active.
        self.record('clear',30242,rank=None)
        restored=QuestState(self.path,account_id=1).snapshot()['active'][0]
        self.assertEqual(restored['objectives'],{47293:1})
        reply=self.action(0xf4,6980)
        self.assertEqual(reply[0].payload[:4],bytes(4))
        self.assertIn(6980,QuestState(self.path,account_id=1).completed())
        self.assertEqual(QuestState(self.path,account_id=1).snapshot()['active'],[])

    def collection_ready(self,*,deadline=None):
        self.set_class(100,99);qid=35370
        with closing(sqlite3.connect(self.path)) as db,db:
            for i in sequence(quest_catalog().quest(qid)['QuestCondition']['m_vecBeforeQuestID']):
                db.execute("INSERT OR IGNORE INTO completed_quests VALUES (1001,?,1,'{}')",(i,))
            from els_server.storage.inventory_state import grant_items
            grant_items(db,[dict(template=271310,metadata=0,group=5,quantity=1)])
            materials=grant_items(db,[dict(template=130208,metadata=2,group=4,quantity=3)])
            if deadline is not None:
                from els_server.storage.item_expiration import assign
                assign(db,1001,materials[0]['uid'],deadline)
        self.assertEqual(self.action(0xee,qid)[0].payload,bytes(4))
        self.assertEqual(self.q.collection_snapshot()[0]['objectives'],{35370:1,35372:3})
        return materials

    def test_collection_discard_updates_native_count_and_completion_flag_before_claim(self):
        material=self.collection_ready()[0];self.seq+=1
        reply=self.s.handle(Event(0x202,kind=0x109,payload=struct.pack('>Qi',material['uid'],1)),self.seq)
        self.assertEqual([e.kind for e in reply],[0x10a,0xf3])
        row=self.q.collection_snapshot()[0]
        self.assertEqual(row['objectives'],{35370:1,35372:2})
        self.assertEqual(reply[-1].payload,wire.progress([row]).payload)
        self.assertEqual(reply[-1].payload[-7:],struct.pack('>iHB',35372,2,0))
        before=self.dump();self.assertNotEqual(self.action(0xf4,35370)[0].payload[:4],bytes(4));self.assertEqual(self.dump(),before)
        # A retry must neither discard another key nor resend stale completion.
        again=self.s.handle(Event(0x202,kind=0x109,payload=struct.pack('>Qi',material['uid'],1)),self.seq-1)
        self.assertEqual([e.kind for e in again],[0x10a]);self.assertEqual(self.dump(),before)

    def test_collection_expiration_updates_even_when_the_request_has_no_reply(self):
        import time
        deadline=int(time.time())+10;material=self.collection_ready(deadline=deadline)[0]
        with patch('time.time',return_value=deadline+1):
            reply=self.s.handle(Event(0x202,kind=0x7fffffff),987)
            progress=[e for e in reply if e.kind==0xf3]
            self.assertEqual(len(progress),1)
            row=self.q.collection_snapshot()[0]
            self.assertEqual(row['objectives'],{35370:1,35372:2})
            self.assertEqual(progress[0].payload,wire.progress([row]).payload)
        self.assertFalse(any(i['uid']==material['uid'] for i in self.a.get_inventory_snapshot()['items']))

    def test_collection_reader_is_read_only_and_owner_cache_does_not_cross_characters(self):
        from els_server.domain.quest_flow import observe
        self.collection_ready();before=self.dump()
        # A separate read can coexist with an existing SQLite writer.
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE');self.assertEqual(len(self.q.collection_snapshot()),1)
        self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):QuestState(self.path,account_id=2).collection_snapshot()
        other=self.a.characters.create('收集任务隔离',2,'collection-other')
        self.s.account=self.a.for_character(other['uid'])
        self.assertEqual(observe(self.s,[Event(0x201,kind=0x105)]),[])
        self.assertEqual(self.s._quest_collection_view[1],{})
        self.s.account=self.a
        self.assertEqual(observe(self.s,[Event(0x201,kind=0x105)]),[])
        self.assertIn(35370,self.s._quest_collection_view[1])

    def test_idle_periodic_expiration_also_retracts_collection_completion(self):
        import time
        deadline=int(time.time())+10;self.collection_ready(deadline=deadline)
        with patch('time.time',return_value=deadline+1):
            replies=self.s.periodic_notifications()
            progress=[e for e in replies if e.kind==0xf3]
            self.assertEqual(len(progress),1)
            row=self.q.collection_snapshot()[0]
            self.assertEqual(row['objectives'],{35370:1,35372:2})
            self.assertEqual(progress[0].payload,wire.progress([row]).payload)
            self.assertFalse(any(e.kind==0xf3 for e in self.s.periodic_notifications()))

    def test_death_evidence_dedup_conflict_and_relogin_restore(self):
        self.first_completed();self.action(0xee,6990)
        sub=quest_catalog().objectives(6990)[0];c=sub['m_ClearCondition']
        event=dict(kind='kill',dungeon=sequence(c['m_eDungeonID'])[0],npc=sequence(c['m_eKillNPCID'])[0],level=30)
        updates=self.q.record('unique-death',event,b'native-death');self.assertEqual(updates[0].kind,0xf3)
        state=self.q.snapshot();before=self.dump();self.assertEqual(self.q.record('unique-death',event,b'native-death'),[]);self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):self.q.record('unique-death',event,b'changed')
        self.assertEqual(self.dump(),before)
        restored=QuestState(self.path).snapshot();self.assertEqual(restored,state)
        self.assertEqual(wire.initialization(restored).payload,wire.initialization(state).payload)
        self.assertEqual(wire.active_record(restored['active'][0])[-1],1)

    def test_full_bag_and_serialization_failure_rollback_then_retry_exactly_once(self):
        self.book_ready()
        from els_server.storage.inventory_state import grant_items
        with closing(sqlite3.connect(self.path)) as db,db:
            grant_items(db,[dict(template=276289,metadata=0,group=4,quantity=36)])
        before=self.dump();self.assertEqual(self.action(0xf4,6990)[0].payload[:4],struct.pack('>i',165));self.assertEqual(self.dump(),before)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('DELETE FROM inventory_items WHERE bag_group=4 AND slot=0')
        before=self.dump()
        with patch('els_server.protocol.quest_messages.reward_ack',side_effect=ValueError('cannot encode')):
            with self.assertRaises(ValueError):self.action(0xf4,6990)
        self.assertEqual(self.dump(),before)
        reply=self.action(0xf4,6990);self.assertEqual(reply[0].payload[:4],bytes(4));before=self.dump()
        replay=self.action(0xf4,6990);self.assertEqual(replay[0].payload[:4],bytes(4))
        # A new transport sequence records a new action receipt, while the
        # completion, balances and awarded instances remain exactly once.
        after=self.dump()
        self.assertEqual([r for r in after if 'INSERT INTO "quest_actions"' not in r],[r for r in before if 'INSERT INTO "quest_actions"' not in r])
        self.assertEqual(self.a.get_reward_balances()['experience'],1200)

    def test_abandon_resets_and_old_request_retry_cannot_abandon_new_acceptance(self):
        self.action(0xee,6980);self.record('clear',30252,rank=None)
        req=dict(quest=6980)
        self.q.action('abandon',req,'abandon-old',lambda r:[wire.initialization(r['state'])])
        self.assertEqual(self.q.snapshot()['active'],[])
        self.action(0xee,6980)
        self.q.action('abandon',req,'abandon-old',lambda r:[wire.initialization(r['state'])])
        self.assertEqual(self.q.snapshot()['active'][0]['objectives'],{47293:0})
        with self.assertRaises(ValueError):self.q.action('abandon',dict(quest=6990),'abandon-old',lambda r:[])

    def test_owner_isolation_and_atomic_real_collection_consumption(self):
        with self.assertRaises(ValueError):QuestState(self.path,account_id=2).snapshot()
        other=self.a.characters.create('其他任务角色',2,'other')
        self.action(0xee,6980);self.record('clear',30252,rank=None)
        self.assertEqual(QuestState(self.path,other['uid'],account_id=1).snapshot()['active'],[])
        # The hyper chain's real key must be present and consumed, not merely
        # a forged objective counter. Prepare only its preceding quest receipt.
        qid=next(q['m_iID'] for q in quest_catalog().quests.values() if 35370 in sequence(q['m_vecSubQuest']))
        q=quest_catalog().quest(qid);self.set_class(100,99)
        with closing(sqlite3.connect(self.path)) as db,db:
            for i in sequence(q['QuestCondition']['m_vecBeforeQuestID']):db.execute("INSERT OR IGNORE INTO completed_quests VALUES (1001,?,1,'{}')",(i,))
            from els_server.storage.inventory_state import grant_items
            key=grant_items(db,[dict(template=271310,metadata=0,group=5,quantity=1)])[0]
            grant_items(db,[dict(template=130208,metadata=2,group=4,quantity=3)])
        self.assertEqual(self.action(0xee,qid)[0].payload,bytes(4))
        self.assertEqual(self.action(0xf4,qid)[0].payload[:4],bytes(4))
        self.assertFalse(any(i['uid']==key['uid'] for i in self.a.get_inventory_snapshot()['items']))

    def test_all_fifteen_roles_have_native_roots_and_master_seal_chains(self):
        from els_server.domain.role_progression import catalog as roles
        from els_server.game_data import client_data
        from els_server.domain.skill_unlocks import catalog as books
        catalog=quest_catalog();groups={books()['books'][str(r['m_iItemID'])]['seal_group'] for q in catalog.quests.values() for r in sequence(q['Reward'].get('m_vecItem',{})) if str(r['m_iItemID']) in books()['books']}
        self.assertEqual(groups,set(range(1,12)))
        for typ in range(1,16):
            cls=next(int(k) for k in roles()['master_skills'] if client_data().unit(int(k))['unitType']==typ)
            c=dict(unit_type=typ,unit_class=cls,level=99,transcendence=True,master=True,skill_seal_groups=())
            eligible=[]
            for q in catalog.quests.values():
                try:require_eligible(c,q,set(),[])
                except ValueError:continue
                eligible.append(q)
            self.assertTrue(eligible,typ)
            master=[q for q in eligible if any(s in sequence(q.get('HIDE_QUEST_SKILL',{})) for s in books()['groups']['9']['skills'])]
            self.assertTrue(master,typ)

    def test_actual_dungeon_deaths_and_clear_drive_progress_without_replayed_credit(self):
        import uuid
        from els_server.domain.dungeon_routes import DungeonRun
        from tests.test_dungeon_routes import finish,load
        self.action(0xee,6980)
        s=LocalSession(self.a,True,True,'dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        s.role='game';s.phase='dungeon_active';s.reward_run_id=str(uuid.uuid4())
        s.dungeon_run=DungeonRun(30252,s.reward_run_id);s.dungeon_id=30252
        clock=[0.0];s.dungeon_run.clock=lambda:clock[0];load(s)
        finish(s,clock)
        self.assertEqual(self.q.snapshot()['active'][0]['objectives'],{47293:1})
        with closing(sqlite3.connect(self.path)) as db:
            count=db.execute("SELECT COUNT(*) FROM quest_progress_events WHERE event_id LIKE '%:clear'").fetchone()[0]
        self.assertEqual(count,1)
        from els_server.domain.quest_flow import observe
        self.assertEqual(observe(s),[])
        self.assertEqual(observe(self.s,[Event(0x201,kind=0xd9)])[0].kind,0x2b)

    def test_retire_from_the_finale_part_controller_completes_28110_once(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',
                       (1001,28110,1,1,json.dumps({'28110':0})))
        updated=self.record('retire',35250,npc=9470,tutorial_quest=28110,retired_by=9310)
        self.assertEqual([e.kind for e in updated],[0xf3])
        active={row['id']:row['objectives'] for row in self.q.snapshot()['active']}
        self.assertEqual(active[28110],{28110:1})
        # The same part condition cannot be replayed from another controller.
        self.assertEqual(self.record('retire',35250,npc=9470,tutorial_quest=28110,retired_by=9460),[])
        self.assertEqual({row['id']:row['objectives'] for row in self.q.snapshot()['active']}[28110],{28110:1})

if __name__=='__main__':unittest.main()
