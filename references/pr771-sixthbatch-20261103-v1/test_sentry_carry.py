"""Real solo/shared stage handlers, isolated stores and original summon DTOs."""
from pathlib import Path
import sys,json,struct,unittest
from dataclasses import replace
from unittest.mock import patch
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime'
sys.path[:0]=[str(R),str(B)]
import test_secondbatch as base
from els_server.domain import dungeon_flow
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_npcs import encode_npc
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.friends_spawns import capture_static_origin

def request(uid):
    dto=bytearray.fromhex(json.loads((ROOT/'analysis/skills-clear-20261015/sentry-request.json').read_bytes())['dto'])
    struct.pack_into('<Q',dto,0x6d,uid)
    return Event(0x202,kind=0x2ce,performers=(0,),payload=struct.pack('>I',1)+encode_npc(dto,0))

def expiry(key,uid):
    raw=struct.pack('>iBQQ6fBf',key,255,2**64-1,2**64-1,*([0.]*6),1,500.)
    raw+=struct.pack('>IIQBQIQ',0,1,uid,0,0,0,0)
    return Event(0x202,kind=0xad,performers=(0,),payload=raw)

class Carry(unittest.TestCase):
    setUp=base.SecondBatch.setUp
    dungeon=base.SecondBatch.dungeon
    party=base.SecondBatch.party

    def complete_part(self,s):
        # Accepted enemy facts only set up the real transition being tested.
        run=s.dungeon_run;run.defeated={n['key']:b'owned stage setup'for n in run.current['npcs']}
        s.defeated_npcs=run.defeated;run.started_at=0.;self.t[0]+=10000
        dungeon_flow.periodic(s);self.assertTrue(s.part_end_notified)

    def test_solo_live_actor_and_receipts_survive_real_stage_without_respawn(self):
        s=self.dungeon(30302);e=request(s.account.uid)
        with patch('els_server.domain.summons.player_summon_templates',return_value=frozenset((384,))):
            self.assertEqual([m.kind for m in s._handle(e,1701)],[0x2cf,0x2d0])
            key=next(iter(s.summon_keys));high=s.summon_next_key
            self.complete_part(s);replies=dungeon_flow.handle(s,base.bb(s))
            self.assertIn(0xb2,[m.kind for m in replies]);self.assertNotIn(0x2d0,[m.kind for m in replies])
            self.assertEqual(s.summon_keys,{key});self.assertEqual(s.summon_next_key,high)
            self.assertFalse(s.summon_keys&s.dungeon_run.reserved_keys)
            replies=dungeon_flow.handle(s,Event(0x202,kind=0xb3,payload=bytes(9)))
            self.assertNotIn(0x2d0,[m.kind for m in replies])
            self.assertEqual(s._handle(e,1701)[0].payload,bytes(4));self.assertEqual(s.summon_next_key,high)
            self.assertEqual([m.kind for m in s._handle(expiry(key,s.account.uid),1702)],[0xae,0xaf])
            self.assertEqual([m.kind for m in s._handle(expiry(key,s.account.uid),1702)],[0xae])
            self.assertFalse(s.dungeon_run.defeated);self.assertFalse(s.world_drops);self.assertFalse(s.part_end_notified)

    def test_solo_owner_expiry_during_stage_loading_frees_only_its_actor(self):
        s=self.dungeon(30302);e=request(s.account.uid)
        with patch('els_server.domain.summons.player_summon_templates',return_value=frozenset((384,))):
            s._handle(e,1801);key=next(iter(s.summon_keys));self.complete_part(s)
            dungeon_flow.handle(s,base.bb(s));self.assertTrue(s.gate_stage_loading)
            self.assertEqual(s._handle(expiry(key,s.account.uid+1),1802),[])
            self.assertEqual(s._handle(e,1803)[0].payload,struct.pack('>i',-1))
            self.assertEqual([m.kind for m in s._handle(expiry(key,s.account.uid),1804)],[0xae,0xaf])
            self.assertEqual(set(s.summon_deaths),{key});self.assertFalse(s.dungeon_run.defeated)

    def test_identity_is_reserved_above_the_whole_route_not_only_current_stage(self):
        s=self.dungeon(30302);e=request(s.account.uid)
        with patch('els_server.domain.summons.player_summon_templates',return_value=frozenset((384,))):s._handle(e,1901)
        key=next(iter(s.summon_keys));run=s.dungeon_run
        for stage in run.graph['stages']:
            run._load_stage(int(stage))
            self.assertFalse({key}&run.reserved_keys,(stage,key))

    def test_shared_stage_preserves_each_owner_and_expiry_during_loading(self):
        app,room,members=self.party();room.identity=30302;dispatcher=app.world.dungeons
        for s in members:
            s.dungeon_run=DungeonRun(30302,room.seed,clock=lambda:self.t[0]);s.dungeon_id=30302
            s.dungeon_run.loaded();s.defeated_npcs=s.dungeon_run.defeated
        capture_static_origin(room);leader,guest=members;e=request(guest.account.uid)
        with patch('els_server.domain.friends_spawns.player_summon_templates',return_value=frozenset((384,))):
            from els_server.domain.friends_spawns import spawn
            self.assertEqual([m.kind for m in spawn(dispatcher,room,guest,e,2001)],[0x2cf,0x2d0])
            key=next(iter(guest.summon_keys));owner=room.shared_actors.owners[key]
            for s in members:self.complete_part(s)
            dispatcher.part_wait(room)
            before=[len(s.mailbox.messages)for s in members]
            for s in members:dispatcher.end_part(room,s,base.bb(s))
            self.assertEqual(room.phase,'substage');self.assertEqual(room.shared_actors.owners[key],owner)
            for s in members:
                self.assertEqual(s.summon_keys,{key});self.assertFalse(s.summon_keys&s.dungeon_run.reserved_keys)
            for s,n in zip(members,before):
                self.assertNotIn(0x2d0,[m.kind for m in list(s.mailbox.messages)[n:]])
            self.assertEqual(dispatcher.death(room,leader,expiry(key,guest.account.uid)),[])
            self.assertEqual([m.kind for m in dispatcher.death(room,guest,expiry(key,guest.account.uid))],[0xae,0xaf])
            for s in members:
                self.assertEqual(set(s.summon_deaths),{key});self.assertFalse(s.dungeon_run.defeated)
            self.assertEqual([m.kind for m in dispatcher.death(room,guest,expiry(key,guest.account.uid))],[0xae])
            for s in members:dispatcher.loaded(room,s,Event(0x202,kind=0xb3,payload=bytes(9)))
            self.assertEqual(room.phase,'active')
            self.assertEqual([m.kind for m in spawn(dispatcher,room,guest,e,2001)],[0x2cf])
            self.assertEqual(spawn(dispatcher,room,guest,e,2001)[0].payload,bytes(4))
            changed=replace(e,payload=e.payload+b'x')
            self.assertEqual(spawn(dispatcher,room,guest,changed,2001)[0].payload,struct.pack('>i',-1))
            high=guest.summon_next_key
            self.assertEqual([m.kind for m in spawn(dispatcher,room,guest,e,2002)],[0x2cf,0x2d0])
            self.assertGreater(max(guest.summon_keys),key);self.assertGreaterEqual(max(guest.summon_keys),high)
            for s in members:
                self.assertFalse(s.dungeon_run.defeated);self.assertFalse(s.world_drops)
                for m in s.mailbox.messages:encode_event(m)

if __name__=='__main__':unittest.main(verbosity=2)
