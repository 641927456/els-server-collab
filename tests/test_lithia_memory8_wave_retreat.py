"""A partial or complete wave never invents an unreported 9452 death."""
import unittest
from els_server.domain import dungeon_flow
from test_lithia_memory8_offfield_expiry import run_stage,session

class UnreportedSentinel(unittest.TestCase):
    def test_partial_or_eight_member_wave_cannot_satisfy_original_kind3(self):
        for dungeon,stage in ((35320,3),(35321,2),(35322,0)):
            for count in (1,8):
                with self.subTest(dungeon=dungeon,count=count):
                    run=run_stage(stage,0,dungeon);s=session(run,part_end_notified=False)
                    sentinel=next(n for n in run.current['npcs'] if n['template']==9452)
                    for key in range(100,100+count):
                        run.current['npcs'].append(dict(key=key,template=9432,dynamic=True,active=False,team=1))
                        run.defeated[key]=b'accepted-wave-report'
                    self.assertFalse(run.condition_ready(run.current['conditions'][0]))
                    self.assertEqual(dungeon_flow.periodic(s),[])
                    self.assertNotIn(sentinel['key'],run.defeated)
                    self.assertFalse(s.part_end_notified);self.assertIsNone(run.next)
                    self.assertFalse(hasattr(dungeon_flow,'wave_retreat'))

if __name__=='__main__':unittest.main()
