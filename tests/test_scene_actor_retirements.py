"""Finite Memory2 retirement against current graphs, with native-shaped reports.

These are offline protocol/atomicity checks, not natural client scene evidence.
"""
import copy
import json
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain import scene_actor_retirements as target
from els_server.domain import dungeon_flow
from els_server.domain.dungeon_lifecycle import death_report
from els_server.protocol.protocol_codec import Event
from test_lithia_memory8_offfield_expiry import run_stage,actor,session,native255,OWNER


def fixture(key=12):
    run=run_stage(0,1,35260);s=session(run,part_end_notified=False)
    e=Event(0x202,performers=(0,),kind=0xad,payload=native255(key,actor(run,key)['hp']))
    return s,e,death_report(e.payload)


def call(s,e,r):
    with patch.object(target,'SCENE_ACTOR_RETIREMENTS_ENABLED',True):return target.handle(s,e,r)


class FiniteSceneRetirements(unittest.TestCase):
    def test_admission_is_enabled_and_code_recovery_preserves_reader(self):
        s,e,r=fixture()
        self.assertTrue(target.SCENE_ACTOR_RETIREMENTS_ENABLED)
        with patch.object(target,'SCENE_ACTOR_RETIREMENTS_ENABLED',False):
            self.assertIsNone(target.handle(s,e,r));self.assertFalse(s.dungeon_run.defeated)
        self.assertIsNotNone(target.source_rule(s.dungeon_run,actor(s.dungeon_run,12)))

    def test_original_native_ctor_map_writer_contract_is_consumed(self):
        # Exact original19E1ED0+1B17F50+2B4CCF0 output in private native memory.
        # UID1001 alive readiness and zero coordinates are explicit data inputs;
        # this fixture makes no claim of executing Game/TLS/GUI or natural play.
        raw=bytes.fromhex('0000000cffffffffffffffffffffffffffffffffff0000000000000000000000000000000000000000000000000146ebf600000000000000000100000000000003e9000000000000000000000000000000000000000000')
        s,e,r=fixture();self.assertEqual(e.payload,raw)
        self.assertEqual([x.kind for x in target.handle(s,e,death_report(raw))],[0xae,0xaf])
        self.assertFalse(actor(s.dungeon_run,12)['active'])
        self.assertIsNone(s.dungeon_run.next)

    def test_dispatcher_routes_before_story_without_quest_or_reward_access(self):
        for key in target.FLOWER_SOURCES:
            s,e,r=fixture(key)
            with patch('els_server.domain.story_controller_retirements.handle',side_effect=AssertionError('story swallowed flower')),patch('els_server.domain.quest_flow.store',side_effect=AssertionError('flower queried quests')):
                self.assertEqual([x.kind for x in dungeon_flow.handle(s,e)],[0xae,0xaf])
                self.assertEqual([x.kind for x in dungeon_flow.handle(s,e)],[0xae])
                changed=bytearray(e.payload);struct.pack_into('>f',changed,21,1.)
                self.assertEqual(dungeon_flow.handle(s,Event(0x202,performers=(0,),kind=0xad,payload=bytes(changed))),[])
            self.assertEqual(s.dungeon_run.defeated,{key:e.payload})

    def test_dispatcher_af_and_ba_encoder_failures_preserve_every_state(self):
        from els_server.protocol.protocol_codec import encode_event
        for failing in (0xaf,0xba):
            s,e,r=fixture();run=s.dungeon_run
            if failing==0xba:run.defeated[18]=b'separate accepted gate fixture'
            before=(copy.deepcopy(run.current),dict(run.defeated),run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started,dict(s.world_drops))
            def fail(reply):
                if reply.kind==failing:raise RuntimeError('controlled dispatcher encoder failure')
                return encode_event(reply)
            with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail):
                with self.assertRaisesRegex(RuntimeError,'controlled dispatcher encoder failure'):dungeon_flow.handle(s,e)
            self.assertEqual((run.current,run.defeated,run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started,s.world_drops),before)

    def test_all_six_original_sources_use_current_formal_hp_without_rewards(self):
        for key,(index,point) in target.FLOWER_SOURCES.items():
            with self.subTest(source=index):
                s,e,r=fixture(key);run=s.dungeon_run;npc=actor(run,key)
                self.assertEqual((npc['template'],npc['source_index'],npc['start_point']),(9323,index,point))
                self.assertEqual(npc['hp'],30203.0)
                with patch('els_server.domain.quest_flow.store') as q,patch('els_server.domain.dungeon_equipment_loot_flow.accepted_death') as loot,patch('els_server.domain.legacy_pve_exp.accepted_death') as xp:
                    self.assertEqual([x.kind for x in call(s,e,r)],[0xae,0xaf])
                    self.assertEqual([x.kind for x in call(s,e,r)],[0xae])
                    q.assert_not_called();loot.assert_not_called();xp.assert_not_called()
                self.assertEqual(run.defeated,{key:e.payload});self.assertFalse(npc['active'])
                self.assertFalse(s.clear_notified);self.assertFalse(s.world_drops)
                self.assertIsNone(run.next);self.assertFalse(s.part_end_notified)

    def test_flowers_do_not_replace_gate9324_or_create_unreported_actors(self):
        s,e,r=fixture();run=s.dungeon_run;before=copy.deepcopy(run.current['npcs'])
        for key in target.FLOWER_SOURCES:
            body=native255(key,actor(run,key)['hp']);e=Event(0x202,performers=(0,),kind=0xad,payload=body)
            self.assertEqual([x.kind for x in call(s,e,death_report(body))],[0xae,0xaf])
        self.assertEqual(run.current['conditions'][0]['required'],[9324])
        self.assertFalse(run.condition_ready(run.current['conditions'][0]));self.assertIsNone(run.next)
        self.assertTrue(actor(run,18)['active']);self.assertNotIn(18,run.defeated)
        self.assertEqual(len(run.current['npcs']),len(before))
        self.assertFalse(any(n.get('dynamic') for n in run.current['npcs']))

    def test_existing_accepted_gate_can_progress_only_after_original_reports(self):
        s,e,r=fixture();run=s.dungeon_run
        run.defeated[18]=b'separate accepted original9324 report'
        self.assertEqual([x.kind for x in call(s,e,r)],[0xae,0xaf,0xba])
        self.assertEqual((run.next['stage'],run.next['part']),(0,2));self.assertTrue(s.part_end_notified)
        self.assertFalse(s.clear_notified)

    def test_encoder_failure_preserves_all_actor_gate_clock_and_drop_state(self):
        s,e,r=fixture();run=s.dungeon_run;run.defeated[18]=b'accepted gate'
        before=(copy.deepcopy(run.current),dict(run.defeated),run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started,dict(s.world_drops))
        count=[0]
        from els_server.protocol.protocol_codec import encode_event
        def fail_last(reply):
            count[0]+=1
            if reply.kind==0xba:raise RuntimeError('controlled final reply failure')
            return encode_event(reply)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail_last):
            with self.assertRaisesRegex(RuntimeError,'controlled final reply failure'):call(s,e,r)
        self.assertEqual(count[0],3)
        self.assertEqual((run.current,run.defeated,run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started,s.world_drops),before)

    def test_source_identity_and_session_poisoning_rejects(self):
        changes=('source','point','template','active','team','ally','boss','no_drop','graph','graph_content','script','instance_hp','report_hp','owner','unit','lease','generation','phase','participants','transaction','performers','uid','duplicate')
        for change in changes:
            with self.subTest(change=change):
                s,e,r=fixture();run=s.dungeon_run;npc=actor(run,12)
                if change=='source':npc['source_index']=2
                if change=='point':npc['start_point']=11
                if change=='template':npc['template']=9324
                if change in ('active','team','ally','boss','no_drop'):npc[change]={'active':False,'team':0,'ally':True,'boss':True,'no_drop':True}[change]
                if change=='graph':run.graph['source_sha256']='0'*64
                if change=='graph_content':run.graph['stages']['0']['parts']['1']['conditions'][0]['required']=[9323]
                if change=='script':run.catalog=copy.copy(run.catalog);run.catalog.manifest=copy.deepcopy(run.catalog.manifest);run.catalog.manifest['source_sha256'][target.SCRIPT]='0'*64
                if change=='instance_hp':npc['hp']+=1
                if change=='report_hp':r['hp_bits']=struct.unpack('>I',struct.pack('>f',5000))[0]
                if change=='owner':r['readiness']={OWNER+1:0}
                if change=='unit':s.account.character=lambda:{'unit_type':16,'level':70}
                if change=='lease':s.application.playing[71]=object()
                if change=='generation':s.reward_run_id='other'
                if change=='phase':s.phase='town_ready'
                if change=='participants':s.dungeon_participants=frozenset((OWNER,OWNER+1))
                if change=='transaction':s.reward_transaction=object()
                if change=='performers':e=Event(0x202,performers=(1,),kind=0xad,payload=e.payload)
                if change=='uid':e=Event(0x202,performers=(0,),kind=0xad,payload=e.payload,uid=OWNER)
                if change=='duplicate':run.current['npcs'].append(dict(npc))
                self.assertEqual(call(s,e,r),[]);self.assertFalse(run.defeated)

    def test_native_shape_is_required_and_conflicting_replay_rejected(self):
        for name,value in (('flag',0),('status',0),('source',OWNER),('killer',OWNER),('last_uid',1),('extra_uid',1),('contribution',{OWNER:1.}),('counters',{OWNER:1})):
            s,e,r=fixture();r[name]=value
            self.assertEqual(call(s,e,r),[]);self.assertFalse(s.dungeon_run.defeated)
        s,e,r=fixture();call(s,e,r)
        raw=bytearray(e.payload);struct.pack_into('>f',raw,21,1.)
        e2=Event(0x202,performers=(0,),kind=0xad,payload=bytes(raw))
        self.assertEqual(call(s,e2,death_report(e2.payload)),[])
        self.assertEqual(s.dungeon_run.defeated,{12:e.payload})

    def test_other_scenes_gates_combat_and_dynamic_actors_are_not_admitted(self):
        s,e,r=fixture(18);self.assertIsNone(call(s,e,r))
        s,e,r=fixture();actor(s.dungeon_run,12)['dynamic']=True
        self.assertIsNone(call(s,e,r));self.assertFalse(s.dungeon_run.defeated)
        for dungeon in (35261,35270,35320):
            run=run_stage(0,0,dungeon);s=session(run)
            self.assertIsNone(call(s,e,r));self.assertFalse(run.defeated)


class PrivateApplicationFlowers(unittest.IsolatedAsyncioTestCase):
    """Real Application/session/lease and disposable owned SQLite only.

    Level70 and active28140 are explicit starting-save fixtures. Original
    28/initialization/town/7D4/37F/91/B3/AD/BB paths reach the flower sources;
    no DungeonRun, part, defeated state or actor is substituted into session.
    """
    async def asyncSetUp(self):
        from els_server.application import Application
        from els_server.config import ServerConfig
        from els_server.storage.characters import Characters
        from els_server.storage.lifecycle import prepare_database
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.path=root/'private-owned-game.sqlite3';prepare_database(self.path)
        self.app=Application(ServerConfig(mode='friends',state_file=self.path,
            accounts_file=root/'private-owned-accounts.sqlite3',tls_cert=root/'unused-cert',
            tls_key=root/'unused-key',log_dir=root/'logs'))
        self.addCleanup(self.app.close)
        await self.app.start()
        enrollment=self.app.registry.create('flowerfixture')
        identity=self.app.registry.authenticate(enrollment['name'],enrollment['token'])
        c=Characters(self.path,identity['id']).create('FlowerFlow',15,'private-create')
        self.uid=c['uid'];self.identity=identity;self.seq=0
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=70 WHERE uid=?',(self.uid,))
        self.s=await self.app.session(identity=identity)
        self.addAsyncCleanup(self.app.release,self.s)
        self.s.role='game';self.s.phase='characters_ready'
        await self.send(0x28,struct.pack('>Q',self.uid))
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(self.uid,28140,1,1,json.dumps({28140:0})))
        for kind in (0x6e9,0x5bf,0x32):await self.send(kind,bytes(8) if kind==0x5bf else b'')
        await self.send(0x225,struct.pack('>iB',20014,0))
        await self.send(0x227,struct.pack('>fffBH',0.,0.,0.,0,0))
        self.assertEqual(self.s.phase,'town_ready')
        from test_lithia_first_entry_handoff import ENTRY
        self.assertEqual((await self.send(0x7d4,struct.pack('>ii',2,35260)))[0].payload[:4],bytes(4))
        self.assertEqual((await self.send(0x37f,ENTRY))[0].kind,0x380)
        await self.send(0x91,struct.pack('>ii',100,0));await self.send(0xb3,bytes(9))
        run=self.s.dungeon_run
        gate=next(n for n in run.current['npcs'] if n['template']==9319)
        self.assertEqual((await self.send(0xad,native255(gate['key'],gate['hp'],owner=self.uid)))[0].kind,0xae)
        # Eleven original combat actors must report their own accepted deaths;
        # the controller alone never advances the part.
        self.assertFalse(self.s.part_end_notified)
        for npc in tuple(run.current['npcs']):
            if npc['template']==9319:continue
            body=bytearray(native255(npc['key'],npc['hp'],owner=self.uid));body[4]=0
            for offset in (5,13,len(body)-8):struct.pack_into('>Q',body,offset,self.uid)
            self.assertEqual((await self.send(0xad,bytes(body)))[0].kind,0xae)
        self.assertTrue(self.s.part_end_notified)
        self.assertEqual((await self.send(0xbb,b'\0'))[0].kind,0xbc)
        await self.send(0xb3,bytes(9))
        self.assertEqual((run.identity,run.stage,run.part),(35260,0,1))
        self.assertEqual([(n['key'],n['template'],n['source_index'],n['start_point']) for n in run.current['npcs']],
            [(key,9323,index,point) for key,(index,point) in target.FLOWER_SOURCES.items()]+[(18,9324,7,10)])
        from els_server.domain.dungeon_equipment_loot_flow import current_lease
        self.assertTrue(current_lease(self.s));self.assertIs(self.app.playing[self.identity['id']],self.s)
        self.assertTrue(self.s.dungeon_substage_synced)

    async def send(self,kind,payload=b''):
        self.seq+=1
        return await self.app.call(self.s.handle,Event(0x202,performers=(0,),kind=kind,payload=payload),self.seq)

    async def death(self,body):
        # The real outer session may append its independent original2AF
        # notification and1CE online-title clock notice, including after a
        # stale lease resumes. Inspect all death/gate replies separately.
        replies=await self.send(0xad,body)
        self.assertTrue(all(e.kind in (0xae,0xaf,0xba,0x2af,0x1ce) for e in replies),[hex(e.kind) for e in replies])
        from els_server.domain.dungeon_lifecycle import empty_reward_death_notice
        key=death_report(body)['index']
        for e in replies:
            if e.kind==0xaf:self.assertEqual(e.payload,empty_reward_death_notice(key,2**64-1).payload)
        return [e for e in replies if e.kind in (0xae,0xaf,0xba)]

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            # Application.call observes real elapsed online time around every
            # request, independently of AD success. Keep that existing clock
            # running; reject any clear/kill fact and protect all other rows.
            for payload, in db.execute('SELECT payload FROM activity518_facts'):
                fact=json.loads(payload)
                self.assertEqual(fact['kind'],'online')
                self.assertEqual(fact['character'],str(self.uid))
                self.assertGreater(fact['ends'],fact['starts'])
            self.assertFalse(db.execute('SELECT 1 FROM activity518_progress WHERE dungeon_clears<>0').fetchone())
            self.assertFalse(db.execute('SELECT 1 FROM activity518_tasks WHERE clears<>0 OR ready_at IS NOT NULL').fetchone())
            for account,character,starts,ends in db.execute('SELECT account,character,starts,ends FROM online2026_spans'):
                self.assertEqual((account,character),(self.identity['id'],self.uid))
                self.assertGreater(ends,starts)
            online_rows=('activity518_facts','activity518_progress','activity518_tasks','online2026_spans')
            protected=tuple(line for line in db.iterdump() if not any(
                line.startswith('INSERT INTO "'+table+'" ') for table in online_rows))
            # Only seconds may change in the already accepted attendance task.
            task_fields=tuple(db.execute('SELECT campaign,account,accepted_period,accepted_at,fact_floor,clears,ready_at FROM activity518_tasks ORDER BY campaign,account'))
            return protected,task_fields

    async def test_real_lease_six_reports_retry_conflict_and_no_gate_or_sql_reward(self):
        run=self.s.dungeon_run;before=self.dump();drops=copy.deepcopy(self.s.world_drops)
        for key in target.FLOWER_SOURCES:
            body=native255(key,actor(run,key)['hp'],owner=self.uid)
            self.assertEqual([e.kind for e in await self.death(body)],[0xae,0xaf])
            self.assertEqual([e.kind for e in await self.death(body)],[0xae])
            changed=bytearray(body);struct.pack_into('>f',changed,21,1.)
            self.assertEqual(await self.death(bytes(changed)),[])
            self.assertFalse(actor(run,key)['active'])
        self.assertEqual(self.dump(),before);self.assertEqual(self.s.world_drops,drops)
        self.assertTrue(actor(run,18)['active']);self.assertNotIn(18,run.defeated)
        self.assertIsNone(run.next);self.assertFalse(self.s.part_end_notified)
        # Flower HP/identity cannot replace the independent9324 gate report.
        self.assertEqual(await self.death(native255(18,30203.,owner=self.uid)),[])
        self.assertEqual(self.dump(),before);self.assertIsNone(run.next)

    async def test_real_session_af_failure_and_stale_or_foreign_report_preserve_state(self):
        from els_server.protocol.protocol_codec import encode_event
        run=self.s.dungeon_run;body=native255(12,actor(run,12)['hp'],owner=self.uid)
        before=(self.dump(),copy.deepcopy(run.current),dict(run.defeated),run.next,run.ready_at,self.s.part_end_notified,copy.deepcopy(self.s.world_drops))
        def fail(reply,*a,**kw):
            if reply.kind==0xaf:raise RuntimeError('private AF encoder failure')
            return encode_event(reply,*a,**kw)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'private AF encoder failure'):await self.death(body)
        self.assertEqual(await self.death(native255(12,30203.,owner=self.uid+1)),[])
        lease=self.app.playing.pop(self.identity['id'])
        try:self.assertEqual(await self.death(body),[])
        finally:self.app.playing[self.identity['id']]=lease
        self.assertEqual((self.dump(),run.current,run.defeated,run.next,run.ready_at,self.s.part_end_notified,self.s.world_drops),before)
        self.assertEqual([e.kind for e in await self.death(body)],[0xae,0xaf])


if __name__=='__main__':unittest.main()
