"""Owned isolated runtime regressions; native reports, no natural game claims."""
from pathlib import Path
import sys,json,copy,struct,unittest,sqlite3,uuid
from contextlib import closing
from unittest.mock import patch
W=Path(__file__).resolve().parent;ROOT=Path('G:/els');B=W.parent/'pr771-firstbatch-20261103-v1';R=B/'runtime'
sys.path[:0]=[str(R),str(B),str(ROOT/'tools')]
import test_secondbatch as second
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain import dungeon_flow
from els_server.protocol.protocol_codec import Event,encode_event
RULES=json.loads((W/'master-source-census.json').read_bytes())['rules']

def expiry(npc,owners):
    body=struct.pack('>iBQQ6fBf',npc['key'],255,2**64-1,2**64-1,0,0,0,0,0,0,1,npc['hp'])
    body+=struct.pack('>II',0,len(owners))+b''.join(struct.pack('>QB',o,0)for o in owners)+struct.pack('>QIQ',0,0,0)
    return Event(0x202,kind=0xad,performers=(0,),payload=body)

class Remaining(unittest.TestCase):
    setUp=second.SecondBatch.setUp
    dungeon=second.SecondBatch.dungeon
    party=second.SecondBatch.party

    def test_current_sixteen_master_gates_and_resource_delays_already_work(self):
        for rule in RULES:
            with self.subTest(dungeon=rule['dungeon']):
                s=self.dungeon(rule['dungeon']);run=s.dungeon_run
                npc=next(n for n in run.current['npcs']if n['template']==rule['source']['template'])
                bosses={n['key']:n['hp']for n in run.current['npcs']if n['boss']}
                self.assertFalse(run.poll_ready());e=expiry(npc,(s.account.uid,))
                reply=dungeon_flow.handle(s,e);delay=run.current['conditions'][0]['delay']
                self.assertEqual([x.kind for x in reply],[0xae,0xaf]+([0xba]if delay==0 else []))
                self.assertEqual(run.defeated,{npc['key']:e.payload});self.assertTrue(run.condition_ready(run.current['conditions'][0]))
                self.assertEqual([x.kind for x in dungeon_flow.handle(s,e)],[0xae])
                if delay:
                    self.t[0]+=delay-0.1;self.assertEqual(dungeon_flow.periodic(s),[])
                    self.t[0]+=0.1;self.assertEqual([x.kind for x in dungeon_flow.periodic(s)],[0xba])
                self.assertTrue(s.part_end_notified);self.assertTrue(run.poll_ready())
                self.assertEqual(bosses,{n['key']:n['hp']for n in run.current['npcs']if n['boss']})
                self.assertFalse(set(bosses)&set(run.defeated))
                s.part_end_notified=False

    def test_current_master_native_floor_does_not_authorize_a_clear(self):
        s=self.dungeon(34390);run=s.dungeon_run;boss=next(n for n in run.current['npcs']if n['boss'])
        e=expiry(boss,(s.account.uid,));raw=bytearray(e.payload);struct.pack_into('>f',raw,46,boss['hp']/1000)
        self.assertEqual(dungeon_flow.handle(s,Event(0x202,kind=0xad,performers=(0,),payload=bytes(raw))),[])
        npc=next(n for n in run.current['npcs']if n['template']==7803)
        self.assertEqual(dungeon_flow.handle(s,expiry(npc,(s.account.uid+1,))),[])
        self.assertFalse(run.defeated);self.assertFalse(s.part_end_notified)

    def test_current_shared_master_gate_uses_existing_all_member_writer(self):
        from els_server.domain.friends_spawns import capture_static_origin
        app,room,members=self.party();room.identity=34390
        for s in members:
            s.dungeon_run=DungeonRun(34390,room.seed,clock=lambda:self.t[0]);s.dungeon_id=34390
            s.dungeon_run.loaded();s.defeated_npcs=s.dungeon_run.defeated
        capture_static_origin(room);leader=members[0]
        npc=next(n for n in leader.dungeon_run.current['npcs']if n['template']==7803)
        e=expiry(npc,tuple(s.account.uid for s in members))
        reply=app.world.dungeons.death(room,leader,e)
        self.assertTrue({0xae,0xaf,0xba}<=set(x.kind for x in reply))
        self.assertEqual(room.phase,'part_end')
        for s in members:
            self.assertEqual(s.dungeon_run.defeated,{npc['key']:e.payload});self.assertTrue(s.part_end_notified)
        before=[tuple(s.mailbox.messages)for s in members]
        self.assertEqual([x.kind for x in app.world.dungeons.death(room,leader,e)],[0xae])
        self.assertEqual(before,[tuple(s.mailbox.messages)for s in members])

    def test_stage_transition_never_reuses_a_previous_player_summon_identity(self):
        f=json.loads((ROOT/'analysis/skills-clear-20261015/sentry-request.json').read_bytes())
        dto=bytearray.fromhex(f['dto']);struct.pack_into('<Q',dto,0x6d,self.a.uid)
        from els_server.domain.dungeon_npcs import encode_npc
        request=Event(0x202,kind=0x2ce,performers=(0,),payload=struct.pack('>I',1)+encode_npc(dto,0))
        s=self.dungeon(30302)
        with patch('els_server.domain.summons.player_summon_templates',return_value=frozenset((384,))):
            reply=s._handle(request,1701);self.assertEqual([x.kind for x in reply],[0x2cf,0x2d0])
            first=next(iter(s.summon_keys));ceiling=s.summon_next_key
            # Supply accepted enemy facts only to reach the actual BB/B3 path.
            run=s.dungeon_run;run.defeated={n['key']:b'owned gate fixture'for n in run.current['npcs']}
            run.started_at=0.;self.t[0]+=10000;dungeon_flow.periodic(s)
            self.assertTrue(s.part_end_notified)
            reply=dungeon_flow.handle(s,second.bb(s));self.assertIn(0xb2,[x.kind for x in reply])
            self.assertEqual(s.summon_next_key,ceiling);self.assertFalse(s.summon_keys)
            dungeon_flow.handle(s,Event(0x202,kind=0xb3,payload=bytes(9)))
            self.assertEqual([x.kind for x in s._handle(request,1701)],[0x2cf])
            self.assertFalse(s.summon_keys);self.assertEqual(s.summon_next_key,ceiling)
            reply=s._handle(request,1702);self.assertEqual([x.kind for x in reply],[0x2cf,0x2d0])
            new=next(iter(s.summon_keys));self.assertGreater(new,first)
            self.assertEqual(s._handle(expiry(dict(key=first,hp=500.),(s.account.uid,)),1703),[])
            self.assertFalse(s.summon_deaths);self.assertEqual(s.summon_keys,{new})

if __name__=='__main__':unittest.main(verbosity=2)
