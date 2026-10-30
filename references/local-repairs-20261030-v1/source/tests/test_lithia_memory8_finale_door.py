"""The finale room never settles while its own boss stands; it hands the client
the next resource part instead.

35320 stage3, 35321 stage2 and 35322 stage0 share one actor table and have no
next stage in the pinned graph. The client opens the room's gate itself and
then waits for the server to select the next area, while the source sentinel
9452 only retires after the fight behind that gate.
"""
import struct
import unittest
from els_server.domain import dungeon_flow
from els_server.protocol.protocol_codec import Event
from test_lithia_memory8_offfield_expiry import run_stage,session,gate

BOSS=9431
ROOMS=((35320,3),(35321,2),(35322,0))

def boss_key(run):
    return next(n for n in run.current['npcs'] if n['template']==BOSS)['key']

def clear_near_side(run):
    boss=boss_key(run)
    for key in gate(run):
        if key!=boss:run.defeated[key]=b'accepted-report'
    return boss

class FinaleBossGuard(unittest.TestCase):
    def test_near_side_clear_selects_the_next_area_once(self):
        for dungeon,stage in ROOMS:
            with self.subTest(dungeon=dungeon,stage=stage):
                run=run_stage(stage,0,dungeon);s=session(run,part_end_notified=False)
                boss=clear_near_side(run)
                self.assertTrue(dungeon_flow.finale_area_cleared(run))
                self.assertTrue(dungeon_flow.finale_boss_pending(run))
                replies=dungeon_flow.periodic(s)
                self.assertEqual([r.kind for r in replies],[0xb7,0xbd])
                self.assertEqual(replies[0].payload,struct.pack('>b',dungeon_flow.FINALE_AREA_PART))
                self.assertEqual(replies[1].payload[0],dungeon_flow.FINALE_AREA_PART)
                # The same roster is passed through: no actor is invented.
                entries={n['key']:n['template'] for n in run.current['npcs']}
                self.assertEqual(entries[boss],BOSS)
                self.assertFalse(s.part_end_notified)
                self.assertFalse(s.clear_notified)
                self.assertEqual(dungeon_flow.periodic(s),[])
                # Only the reported boss death ends the room afterwards.
                run.defeated[boss]=b'accepted-boss-report'
                self.assertFalse(dungeon_flow.finale_boss_pending(run))
                self.assertEqual([r.kind for r in dungeon_flow.periodic(s)],[0xba])

    def test_near_side_still_busy_keeps_the_room(self):
        for dungeon,stage in ROOMS:
            with self.subTest(dungeon=dungeon,stage=stage):
                run=run_stage(stage,0,dungeon);s=session(run,part_end_notified=False)
                self.assertFalse(dungeon_flow.finale_area_cleared(run))
                self.assertEqual(dungeon_flow.periodic(s),[])
                self.assertFalse(getattr(s,'finale_area_entered',False))

    def test_other_rooms_and_other_dungeons_are_untouched(self):
        for dungeon,stage in ((35320,0),(35320,2),(35321,0),(35300,0)):
            with self.subTest(dungeon=dungeon,stage=stage):
                run=run_stage(stage,0,dungeon)
                self.assertFalse(dungeon_flow.finale_boss_pending(run))
                self.assertFalse(dungeon_flow.finale_area_cleared(run))

    def test_part_request_never_settles_while_the_boss_stands(self):
        run=run_stage(0,0,35322);s=session(run,part_end_notified=False)
        s.gate_stage_loading=False;s.previous_dungeon_part=None
        ask=Event(0x202,performers=(0,),kind=0xbb,payload=struct.pack('>b',0))
        self.assertEqual(dungeon_flow.handle(s,ask),[])
        self.assertFalse(s.clear_notified)

if __name__=='__main__':unittest.main()
