"""Committed native part barriers and real region acceptance/claim storage."""
import asyncio,copy,json,sqlite3,struct,tempfile,unittest,uuid
from pathlib import Path
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalAccount
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain import pending_part_end as pending
from els_server.domain.region_quests import region_catalog,sequence
from els_server.domain.boosting_2026_region_entries import resume,ENTRIES
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import ensure,QuestState


def bb(s):return Event(0x202,kind=0xbb,payload=struct.pack('>b',s.dungeon_run.part))
def death(npc,uid):
    raw=struct.pack('>iBQQ6fBf',npc['key'],0,uid,uid,*([0.]*6),1,npc['hp'])
    raw+=struct.pack('>IIQBQIQ',0,1,uid,0,0,0,uid)
    return Event(0x202,performers=(0,),kind=0xad,payload=raw)


class SecondBatch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='secondbatch-',dir=Path(__file__).parent/'tmp')
        self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'own.sqlite3'
        self.a=LocalAccount(LocalState(self.path));self.a.enable_characters();self.a.enable_rewards()
        self.a.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(self.a.uid,));ensure(db)
        self.app=Application(ServerConfig(state_file=self.path));self.app.account=self.a
        self.addCleanup(self.app.close)
        self.s=asyncio.run(self.app.session());self.s.role='game'
        self.s.completed.update((0x28,0x225,0x227));self.s.phase='town_ready'
        self.t=[0.]

    def dungeon(self,identity=30092):
        s=self.s;epoch=str(uuid.uuid4());s.reward_run_id=epoch
        s.dungeon_run=DungeonRun(identity,epoch,clock=lambda:self.t[0])
        s.dungeon_id=identity;s.gate_stage=0;s.phase='dungeon_active'
        s.dungeon_participants=frozenset((self.a.uid,));s.dungeon_substage_synced=True
        s.gate_stage_loading=False;s.dungeon_failed=False;s.dungeon_run.loaded();s.dungeon_clock.resume()
        s.defeated_npcs=s.dungeon_run.defeated
        return s

    def kill_current(self):
        r=self.s.dungeon_run;messages=[]
        for npc in tuple(r.current['npcs']):
            if npc.get('team',1)==0:continue
            replies=self.s.handle(death(npc,self.a.uid),20+npc['key'])
            messages+=replies
            self.assertIn(0xae,[e.kind for e in replies],(r.identity,r.stage,r.part,npc['key']))
        self.t[0]+=100000
        return messages+self.s.periodic_notifications()

    def test_early_end_waits_for_actual_deaths_then_advances_once(self):
        s=self.dungeon();source=(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits)
        self.assertNotIn(0xbc,[e.kind for e in s.handle(bb(s),1)])
        self.assertIsNotNone(s.pending_native_part_end)
        self.assertEqual(source,(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits))
        replies=self.kill_current()
        self.assertIn(0xbc,[e.kind for e in replies]);self.assertIsNone(s.pending_native_part_end)
        self.assertNotEqual(source,(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits))
        after=(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits)
        s.periodic_notifications();self.assertEqual(after,(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits))

    def test_invalid_envelopes_and_old_part_never_queue(self):
        s=self.dungeon();event=bb(s)
        for bad in (replace(event,performers=(1001,)),replace(event,uid=1001),replace(event,target_uid=1001),
                    replace(event,payload_mode=1),replace(event,payload=b'\x7f'),replace(event,payload=b'')):
            pending.remember(s,bad,1);self.assertIsNone(getattr(s,'pending_native_part_end',None))

    def test_cursor_session_or_character_change_discards_pending(self):
        for change in ('stage','part','visits','session','account','run','phase','release'):
            with self.subTest(change=change):
                s=self.dungeon();pending.remember(s,bb(s),1)
                if change in ('stage','part','visits'):setattr(s.dungeon_run,change,getattr(s.dungeon_run,change)+1)
                elif change=='session':s.shop_session_id=str(uuid.uuid4())
                elif change=='account':s.account.account_id=2
                elif change=='run':s.dungeon_run=copy.copy(s.dungeon_run)
                elif change=='phase':s.phase='town_ready'
                else:s._c1_local_live=False
                s.part_end_notified=True
                self.assertEqual(pending.finish(s,[]),[]);self.assertIsNone(s.pending_native_part_end)
                s.account.account_id=1;s.part_end_notified=False;s._c1_local_live=True

    def test_transaction_shadow_cannot_consume_request(self):
        s=self.dungeon();pending.remember(s,bb(s),1);original=s.pending_native_part_end
        shadow=copy.copy(s);shadow.dungeon_run=copy.copy(s.dungeon_run)
        shadow.part_end_notified=True;shadow.reward_transaction=object()
        self.assertEqual(pending.finish(shadow,[]),[]);self.assertIs(s.pending_native_part_end,original)
        self.assertFalse(s.part_end_notified)

    def test_native_delay_and_condition_contact_still_required(self):
        s=self.dungeon();pending.remember(s,bb(s),1)
        for npc in s.dungeon_run.current['npcs']:s.dungeon_run.defeated[npc['key']]=b'owned-accepted-death'
        from els_server.domain.dungeon_flow import periodic
        before=(s.dungeon_run.stage,s.dungeon_run.part)
        periodic(s)
        if not s.part_end_notified:
            self.assertEqual(pending.finish(s,[]),[]);self.assertEqual(before,(s.dungeon_run.stage,s.dungeon_run.part))

    def entries(self,now=1800000000):
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            messages=resume(db,self.a.uid,self.a.account_id,now=now,location=('town',20013))
            for e in messages:encode_event(e)
            return messages

    def seed_completed(self,*quests):
        with closing(sqlite3.connect(self.path))as db,db:
            for qid in quests:db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(self.a.uid,qid,1000,'{}'))

    def test_all_eight_new_entries_require_real_predecessor_and_claim(self):
        self.assertEqual(ENTRIES,(26640,26650,26690,27540,27550,27560,27570,27580,27590,27600))
        self.seed_completed(26640,26650,26680);catalog=region_catalog();state=QuestState(self.path,self.a.uid,account_id=1)
        for index,qid in enumerate(ENTRIES[2:]):
            with self.subTest(quest=qid):
                replies=self.entries(1800000000+index*100)
                self.assertEqual([struct.unpack_from('>i',e.payload)[0]for e in replies],[qid])
                self.assertEqual(self.entries(1800000001+index*100),[])
                saved=state.snapshot();active=next(q for q in saved['active']if q['id']==qid)
                self.assertEqual(set(active['objectives'].values()),{0})
                q=catalog.data['quests'][str(qid)]['definition']
                for subid in sequence(q['m_vecSubQuest']):
                    sub=catalog.data['subquests'][str(subid)]['definition'];c=sub['m_ClearCondition']
                    maps=sequence(c.get('m_eDungeonID',{}))
                    for n in range(int(c['m_iDungeonClearCount'])):
                        state.record(f'{qid}:{subid}:{n}',dict(kind='clear',dungeon=maps[0],level=99,rank=5),b'owned-clear')
                request=dict(quest=qid,npc=q['m_eEndNPCID'],choices=())
                state.action('claim',request,f'claim:{qid}',lambda r:[],now=1800000050+index*100,location=('town',20013))
                cold=QuestState(self.path,self.a.uid,account_id=1).snapshot()
                self.assertIn(qid,{q['id']for q in cold['completed']})
                before=json.dumps(cold,sort_keys=True)
                state.action('claim',request,f'claim:{qid}',lambda r:[],now=1800000051+index*100,location=('town',20013))
                self.assertEqual(before,json.dumps(state.snapshot(),sort_keys=True))
        self.assertEqual(self.entries(1800002000),[])

    def test_region_rejects_level_owner_and_rolls_back_encode_failure(self):
        self.seed_completed(26640,26650,26680)
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=98 WHERE uid=?',(self.a.uid,))
        self.assertEqual(self.entries(),[])
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(self.a.uid,))
        with self.assertRaises(ValueError):
            with closing(sqlite3.connect(self.path))as db,db:resume(db,self.a.uid,2,now=1800000000,location=('town',20013))
        with patch(__name__+'.encode_event',side_effect=ValueError('owned encode failure')):
            with self.assertRaisesRegex(ValueError,'owned encode'):self.entries()
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('SELECT count(*)FROM character_quests WHERE owner=?',(self.a.uid,)).fetchone()[0],0)

    def party(self):
        from els_server.application import FriendsSession
        from els_server.storage.accounts import Accounts
        from els_server.storage.characters import Characters
        from els_server.domain.friends_dungeon import Room
        from els_server.domain.friends_spawns import capture_static_origin
        base=Path(self.tmp.name)
        config=ServerConfig(mode='friends',state_file=self.path,accounts_file=base/'accounts.sqlite3',
                            tls_cert=base/'unused.pem',tls_key=base/'unused-key.pem',friends_coop_enabled=True)
        app=Application(config);app.registry=Accounts(config.accounts_file);self.addCleanup(app.close)
        self.addCleanup(lambda:(app.registry.close(),setattr(app,'registry',None)))
        identities=[app.registry.create(n)for n in ('earlyalice','earlybob')]
        roots=[];members=[];epoch=str(uuid.uuid4())
        for index,identity in enumerate(identities):
            roster=Characters(self.path,identity['id']);uid=roster.create('Early'+str(index),1,'owned-'+str(index))['uid']
            account=LocalAccount(LocalState(self.path,uid),identity['id'],identity['name'])
            account.enable_characters();roots.append(account)
            account.enable_rewards();account.get_inventory_snapshot()
            with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(account.uid,))
            app.accounts[identity['id']]=account
            s=FriendsSession(app,identity,account,**config.session_options());app.playing[identity['id']]=s
            s.role='game';s.phase='dungeon_active';s.completed.update((0x28,0x225,0x227))
            s.reward_run_id=str(uuid.uuid5(uuid.UUID(epoch),'reward:'+str(account.uid)))
            s.dungeon_run=DungeonRun(30092,epoch,clock=lambda:self.t[0]);s.dungeon_id=30092
            s.dungeon_run.loaded();s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.dungeon_failed=False
            s.defeated_npcs=s.dungeon_run.defeated;s.dungeon_clock.resume();members.append(s)
        members=tuple(members);party=dict(members=members,leader=members[0],ready=set(members),run=None)
        room=Room(party,members,members[0],30092,epoch,phase='active');party['run']=room
        for s in members:
            s.dungeon_participants=frozenset(m.account.uid for m in members)
            app.world.party_of[s]=party;app.world.dungeons.rooms[s]=room
        capture_static_origin(room)
        self.party_roots=roots
        return app,room,members

    def shared_deaths(self,app,room,members):
        leader=members[0];messages=[]
        for npc in tuple(leader.dungeon_run.current['npcs']):
            if npc.get('team',1)==0:continue
            reply=leader.handle(death(npc,leader.account.uid),50+npc['key'])
            self.assertIn(0xae,[e.kind for e in reply]);messages+=reply
        self.t[0]+=100000
        app.world.dungeons.periodic(leader)
        return messages

    def test_shared_early_requests_keep_all_member_barrier(self):
        app,room,members=self.party();dispatcher=app.world.dungeons
        old=(members[0].dungeon_run.stage,members[0].dungeon_run.part,members[0].dungeon_run.visits)
        requests=[bb(s)for s in members]
        for s,e in zip(members,requests):self.assertEqual(dispatcher.end_part(room,s,e),[])
        self.assertEqual(len(room.pending_native_part_ends),2)
        self.assertFalse(room.ended)
        messages=self.shared_deaths(app,room,members)
        self.assertFalse(room.pending_native_part_ends)
        cursors={(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits)for s in members}
        self.assertEqual(len(cursors),1);self.assertNotIn(old,cursors)
        for s,e in zip(members,requests):
            self.assertIn([m.kind for m in dispatcher.end_part(room,s,e)],([], [0xbc]))
        self.assertEqual(cursors,{(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits)for s in members})

    def test_one_early_member_still_waits_for_other_members_native_end(self):
        app,room,members=self.party();d=app.world.dungeons
        source=(members[0].dungeon_run.stage,members[0].dungeon_run.part,members[0].dungeon_run.visits)
        d.end_part(room,members[0],bb(members[0]));self.shared_deaths(app,room,members)
        self.assertEqual(room.phase,'part_end');self.assertEqual(room.ended,{members[0]})
        self.assertEqual(source,(members[0].dungeon_run.stage,members[0].dungeon_run.part,members[0].dungeon_run.visits))
        self.assertEqual([e.kind for e in d.end_part(room,members[1],bb(members[1]))],[0xbc])
        self.assertNotEqual(source,(members[0].dungeon_run.stage,members[0].dungeon_run.part,members[0].dungeon_run.visits))

    def test_stale_shared_lease_or_forged_request_cannot_be_replayed(self):
        app,room,members=self.party();d=app.world.dungeons;s=members[0]
        pending.remember_shared(d,room,s,replace(bb(s),performers=(999,)))
        self.assertFalse(getattr(room,'pending_native_part_ends',{}))
        pending.remember_shared(d,room,s,bb(s));app.playing.pop(s.identity['id'])
        for m in members:m.part_end_notified=True
        d.part_wait(room)
        self.assertFalse(room.ended);self.assertFalse(room.pending_native_part_ends)

    def test_full_solo_clear_through_queued_native_ends_is_not_paid_twice(self):
        s=self.dungeon();seen=set();clear_replies=[]
        while not s.clear_notified:
            run=s.dungeon_run;cursor=(run.stage,run.part,run.visits)
            self.assertNotIn(cursor,seen);seen.add(cursor)
            s.handle(bb(s),100+len(seen))
            replies=self.kill_current();clear_replies+=replies
            if not s.dungeon_substage_synced:s.handle(Event(0x202,kind=0xb3,payload=bytes(9)))
        self.assertEqual(sum(e.kind==0xc1 for e in clear_replies),1)
        before=self.a.get_inventory_snapshot()
        s.handle(bb(s),999);s.periodic_notifications()
        self.assertEqual(before,self.a.get_inventory_snapshot())
        self.assertEqual(before,LocalAccount(LocalState(self.path)).get_inventory_snapshot())

    def growth_binding(self):
        from els_server.domain.boosting_2026_quests import BoostingQuestBinding
        raw=(Path(__file__).parent/'runtime/els_server/data/selected2026/growth-growth.json').read_bytes()
        return BoostingQuestBinding(raw,clock=lambda:1800000000,campaign_open=lambda s,now:True)

    def bind_growth(self,binding):
        from els_server.storage.boosting_2026_participation import BoostingParticipation
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            participation=BoostingParticipation(db,binding.original);participation.initialize()
            binding._store(db).initialize()
            participation.record_binding(account=1,character=self.a.uid,operation='owned-bound-fixture',joined_at=1799999000)

    def test_region_scheduler_only_uses_bound_growth_role_and_open_campaign(self):
        binding=self.growth_binding();self.seed_completed(26640,26650,26680)
        self.assertEqual(binding._resume_region_entries(self.s,[]),[])
        self.bind_growth(binding)
        other=self.a.characters.create('RegionAlt',1,'owned-region-alt')['uid']
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(other,))
        self.s.account=self.a.for_character(other)
        self.assertEqual(binding._resume_region_entries(self.s,[]),[])
        self.s.account=self.a;binding.campaign_open=lambda s,now:False
        self.assertEqual(binding._resume_region_entries(self.s,[]),[])
        binding.campaign_open=lambda s,now:True
        messages=binding._resume_region_entries(self.s,[])
        self.assertEqual([struct.unpack_from('>i',e.payload)[0]for e in messages],[26690])
        self.assertEqual(binding._resume_region_entries(self.s,[]),[])

    def test_region_preview_and_writer_share_current_fifty_quest_limit(self):
        from els_server.domain.seal_quests import quest_catalog,ACTIVE_QUEST_LIMIT
        binding=self.growth_binding();self.bind_growth(binding);self.seed_completed(26640,26650,26680)
        catalog=quest_catalog();ids=[int(k)for k in catalog.quests if int(k)not in ENTRIES][:ACTIVE_QUEST_LIMIT]
        with closing(sqlite3.connect(self.path))as db,db:
            for q in ids[:49]:db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(self.a.uid,q,1799990000,1799990000,'{}'))
        self.assertTrue(binding._automatic_work(self.s,'region'))
        self.assertEqual([struct.unpack_from('>i',e.payload)[0]for e in self.entries()],[26690])
        self.assertFalse(binding._automatic_work(self.s,'region'))
        self.assertEqual(self.entries(),[])
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('SELECT count(*)FROM character_quests WHERE owner=?',(self.a.uid,)).fetchone()[0],ACTIVE_QUEST_LIMIT)

    def test_failed_death_encoding_keeps_cursor_request_and_database(self):
        s=self.dungeon();s.handle(bb(s),1)
        actor=next(n for n in s.dungeon_run.current['npcs']if n['active']and not n['no_drop'])
        with closing(sqlite3.connect(self.path))as db:before=tuple(db.iterdump())
        cursor=(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits)
        defeated=dict(s.dungeon_run.defeated);request=s.pending_native_part_end
        self.assertIsNotNone(request)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('owned death encode failure')):
            try:replies=s.handle(death(actor,self.a.uid),80)
            except ValueError:replies=[]
        self.assertNotIn(0xbc,[e.kind for e in replies])
        self.assertEqual(cursor,(s.dungeon_run.stage,s.dungeon_run.part,s.dungeon_run.visits))
        self.assertEqual(defeated,s.dungeon_run.defeated);self.assertIs(s.pending_native_part_end,request)
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(before,tuple(db.iterdump()))
        replies=s.handle(death(actor,self.a.uid),80)
        self.assertIn(0xae,[e.kind for e in replies])
        self.assertIn(0xbc,[e.kind for e in self.kill_current()])

    def test_unowned_nonpersistent_session_does_not_retain_request(self):
        s=self.dungeon();s.account.store=None
        pending.remember(s,bb(s),1)
        self.assertIsNone(getattr(s,'pending_native_part_end',None))
