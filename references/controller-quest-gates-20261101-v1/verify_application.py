"""Disposable Application/SQLite coverage; reports model native inputs, not combat."""
import argparse
from pathlib import Path
import sys
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime',type=Path,required=True)
parser.add_argument('--scratch',type=Path,required=True)
parser.add_argument('--participants',choices=('all','1','2'),default='all')
parser.add_argument('--case',action='append',default=[],help='Optional dungeon:stage:part:template filter')
args=parser.parse_args()
TASK=Path(__file__).resolve().parent
BASE=args.runtime.resolve()
SCRATCH=args.scratch.resolve();SCRATCH.mkdir(parents=True,exist_ok=True)
sys.dont_write_bytecode=True;sys.path.insert(0,str(BASE))
import els_server.domain
els_server.domain.__path__.insert(0,str(TASK/'source/els_server/domain'))
import asyncio
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import sys
import unittest
import uuid
from unittest.mock import patch

from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain import story_controller_retirements as target
from els_server.domain.dungeon_lifecycle import death_report
from els_server.domain.dungeon_npcs import resource_dto,encode_npc
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.local_messages import wstring
from els_server.storage.characters import Characters
from els_server.storage.lifecycle import prepare_database
from els_server.storage.seal_quests import QuestState

ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')


def expiry(npc,owners):
    absent=2**64-1
    payload=struct.pack('>iBQQ6fBf',npc['key'],255,absent,absent,0,0,0,0,0,0,1,npc['hp'])
    payload+=struct.pack('>II',0,len(owners))+b''.join(struct.pack('>QB',uid,0)for uid in sorted(owners))
    return payload+struct.pack('>QIQ',0,0,0)


def combat(npc,uid):
    return struct.pack('>iBQQ6fBf',npc['key'],1,uid,uid,0,0,0,0,0,0,0,npc['hp'])+struct.pack('>IIQIQ',0,0,0,0,uid)


class VariantApplication(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=SCRATCH);self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.path=self.root/'owned-game.sqlite3';prepare_database(self.path)
        self.app=Application(ServerConfig(mode='friends',state_file=self.path,
            accounts_file=self.root/'owned-accounts.sqlite3',tls_cert=self.root/'unused-cert',
            tls_key=self.root/'unused-key',log_dir=self.root/'logs',friends_coop_enabled=True))
        self.addCleanup(self.app.close);await self.app.start()
        self.sessions=[];self.sequences={};self.clock=[0.]

    async def role(self,unit=13,level=99):
        index=len(self.sessions)
        account=self.app.registry.create('variant'+str(index))
        identity=self.app.registry.authenticate(account['name'],account['token'])
        uid=Characters(self.path,identity['id']).create('Variant'+str(index),unit,'variant:'+str(index))['uid']
        QuestState(self.path,uid,account_id=identity['id']).snapshot()
        from els_server.domain.region_quests import region_catalog
        data=region_catalog().data
        requirements={data['regions'][str(i)]['requirement'].get('RequireQuestID')
            for i in data['dungeons'][str(self.identity)] if str(i)in data['regions']}-{0,None}
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET level=? WHERE uid=?',(level,uid))
            db.executemany('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',[(uid,q,1,'{}')for q in requirements])
        s=await self.app.session(identity=identity);self.sessions.append(s)
        self.addAsyncCleanup(self.app.release,s);self.sequences[s]=0
        s.role='game';s.phase='characters_ready'
        await self.send(s,0x28,struct.pack('>Q',uid))
        for kind in (0x6e9,0x5bf,0x32):await self.send(s,kind,bytes(8)if kind==0x5bf else b'')
        await self.send(s,0x225,struct.pack('>iB',20000,0))
        await self.send(s,0x227,struct.pack('>fffBH',0,0,0,0,0))
        self.assertEqual(s.phase,'town_ready')
        return s

    async def send(self,s,kind,payload=b''):
        self.sequences[s]+=1
        events=await self.app.call(s.handle,Event(0x202,performers=(0,),kind=kind,payload=payload),self.sequences[s])
        for e in events:encode_event(e)
        # Inspect actual mailbox state in group assertions before clearing it.
        return events

    async def enter(self,members):
        leader=members[0]
        if len(members)>1:
            for guest in members[1:]:
                uid=guest.account.uid
                data=struct.pack('>Q',uid)+wstring(guest.account.character()['name'])+struct.pack('>iBi',0,1,30000)+bytes(6)+wstring('')+bytes(15)
                self.assertEqual((await self.send(leader,0x136,data))[0].payload[:4],bytes(4))
                await self.send(guest,0x139,struct.pack('>QQBiBQ',leader.account.uid,uid,1,0,0,0))
            changed=await self.send(leader,0x145,struct.pack('>ibb',self.identity,0,0))
            self.assertEqual(next(e for e in changed if e.kind==0x146).payload,bytes(4))
            for guest in members[1:]:await self.send(guest,0x14c,b'\1'+bytes(4))
        selection=await self.send(leader,0x7d4,struct.pack('>ii',1,self.identity))
        reply=next(e for e in selection if e.kind==0x7d5)
        self.assertEqual(reply.payload[:4],bytes(4),reply.payload.hex())
        mode=struct.unpack_from('>i',reply.payload,4)[0]
        await self.send(leader,0x382 if mode==1 else 0x37f,ENTRY)
        # Controlled current-room fixture, before the actual B2/B3 load handshake.
        # No natural traversal or AI/wave claim is made by these cases.
        for s in members:
            run=s.dungeon_run
            if run.stage!=self.stage:run._load_stage(self.stage)
            run.part=self.part
            s.gate_stage=self.stage
        if len(members)>1:
            from els_server.domain.friends_spawns import capture_static_origin
            capture_static_origin(self.app.world.dungeons.room(leader))
        for s in members:await self.send(s,0x91,struct.pack('>ii',100,0))
        for s in members:
            self.assertIsNotNone(s.dungeon_run)
            s.dungeon_run.clock=lambda:self.clock[0]
        for s in members:await self.send(s,0xb3,bytes(9))
        self.assertTrue(all(s.dungeon_substage_synced for s in members))
        return self.app.world.dungeons.room(leader)

    async def advance(self,members):
        run=members[0].dungeon_run
        self.assertTrue(all(s.part_end_notified for s in members),(run.stage,run.part))
        old=(run.stage,run.part)
        replies=[]
        for s in members:replies+=await self.send(s,0xbb,struct.pack('>b',run.part))
        if members[0].clear_notified:return replies
        if old[0]!=run.stage:
            for s in members:await self.send(s,0xb3,bytes(9))
        self.assertTrue(all(s.dungeon_substage_synced for s in members))
        return replies

    def saved(self,members):
        return [(s.account.get_inventory_snapshot(),s.account.get_reward_balances(),
                 copy.deepcopy(s.world_drops),s.world_drop_sequence)for s in members]

    async def case(self,row,count=1):
        from els_server.domain import public_controller_rules as public
        from els_server.domain import story_controller_retirements as retirement
        from els_server.domain.dungeon_flow import periodic
        self.identity=row['dungeon'];self.stage=row['stage'];self.part=row['part']
        unit=row['unit'];members=[await self.role(unit=unit)for _ in range(count)]
        room=await self.enter(members);s=members[0];run=s.dungeon_run
        npc=next(n for n in run.current['npcs']if n['template']==row['template']and n['source_index']==row['source']['source_index'])
        body=expiry(npc,[m.account.uid for m in members])
        # A legitimate admitted role does not own the optional map story tasks.
        with closing(sqlite3.connect(self.path))as db:
            for member in members:
                done={q for q, in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(member.account.uid,))}
                active={q for q, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(member.account.uid,))}
                self.assertFalse((done|active)&set(row['map_quests']))
        baseline=list(public.RULES[:135])
        before=self.saved(members);progress=[dict(m.dungeon_run.defeated)for m in members]
        with patch.object(public,'RULES',baseline):
            reply=await self.send(s,0xad,body)
            self.assertFalse(any(e.kind in(0xae,0xaf,0xba)for e in reply),(row['dungeon'],row['template']))
        self.assertEqual(self.saved(members),before)
        self.assertEqual([dict(m.dungeon_run.defeated)for m in members],progress)
        # Only the exact native255 is accepted; ordinary combat cannot kill the invulnerable controller.
        self.assertFalse(any(e.kind in(0xae,0xaf,0xba)for e in await self.send(s,0xad,combat(npc,s.account.uid))))
        reply=await self.send(s,0xad,body)
        self.assertTrue(any(e.kind==0xae for e in reply),(row['dungeon'],row['template'],[hex(e.kind)for e in reply]))
        self.assertTrue(all(m.dungeon_run.defeated.get(npc['key'])==body for m in members))
        self.assertEqual(self.saved(members),before)
        replay=await self.send(s,0xad,body)
        # Application may attach its independent timed activity-list synchronization.
        # It cannot add another death notice, gate, drop or economic increment.
        self.assertTrue(all(e.kind in(0xae,0x2af)for e in replay))
        self.assertEqual([e.kind for e in replay if e.kind!=0x2af],[0xae])
        self.assertEqual(self.saved(members),before)
        self.assertTrue(all(m.dungeon_run.defeated.get(npc['key'])==body for m in members))
        # Remaining declared hostile combat actors must retain their original gate.
        for actor in tuple(run.current['npcs']):
            if s.part_end_notified:break
            if actor is npc or actor.get('team',1)==0 or not actor['active']:continue
            reply=await self.send(s,0xad,combat(actor,s.account.uid))
            self.assertTrue(any(e.kind==0xae for e in reply),(self.identity,actor['template']))
        self.clock[0]+=86401
        if room is None:
            for m in members:await self.app.call(m.periodic_notifications)
        else:await self.app.call(self.app.world.dungeons.periodic,s)
        self.assertTrue(all(m.part_end_notified for m in members),(self.identity,self.stage,self.part))
        target=copy.deepcopy(run.next)
        replies=await self.advance(members)
        if target['kind']==4:
            self.assertTrue(all(m.clear_notified for m in members))
            self.assertTrue(any(e.kind==0xc1 for e in replies)or count>1)
        else:
            self.assertEqual((run.stage,run.part),(target['stage'],target['part']))
        return dict(dungeon=row['dungeon'],stage=row['stage'],part=row['part'],template=row['template'],participants=count,
            baseline_rejected=True,candidate_accepted=True,duplicate_only_AE=True,next=target,controlled_checkpoint=True)

    async def run_rows(self,count=1):
        rows=json.loads((TASK/'cases.json').read_bytes());results=[]
        if args.case:
            keys={tuple(map(int,value.split(':')))for value in args.case}
            self.assertTrue(keys<={(r['dungeon'],r['stage'],r['part'],r['template'])for r in rows})
            rows=[r for r in rows if(r['dungeon'],r['stage'],r['part'],r['template'])in keys]
        for row in rows:
            with self.subTest(source=(row['dungeon'],row['stage'],row['part'],row['template']),participants=count):
                results.append(await self.case(row,count))
        self.assertEqual(len(results),len(rows))

    async def test_all_solo_sources(self):await self.run_rows()
    async def test_all_two_member_sources(self):await self.run_rows(2)

if __name__=='__main__':
    names=['test_all_solo_sources','test_all_two_member_sources'] if args.participants=='all' else ['test_all_solo_sources' if args.participants=='1' else 'test_all_two_member_sources']
    suite=unittest.TestSuite(VariantApplication(n)for n in names)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps(dict(ok=result.wasSuccessful(),source_positions=11,participant_modes=args.participants,controlled_room_checkpoints=True,natural_battle=False)))
    raise SystemExit(not result.wasSuccessful())
