"""Level-task progress through admitted dungeon dispatch; no live combat."""
import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event
from tests.test_dungeon_routes import ENTRY,load,finish

class SealLevelFlowTests(unittest.TestCase):
    def run_clear(self,level,*,level_up=False):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'level.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters()
            def set_level(value):
                with closing(sqlite3.connect(path)) as db,db:
                    db.execute('UPDATE characters SET unit_class=100,level=? WHERE uid=1001',(value,))
                    db.execute('UPDATE reward_balances SET experience=? WHERE uid=1001',(client_data().thresholds[value-1],))
            set_level(level)
            s=LocalSession(a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
            s.role='game';s.phase='town_ready';q=QuestState(path,account_id=1)
            self.assertEqual(s.handle(Event(0x202,performers=(0,),kind=0xee,payload=struct.pack('>ii',6980,10025)),1)[0].payload,bytes(4))
            self.assertEqual(s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30242)))[0].payload[:4],bytes(4))
            self.assertEqual(s.handle(Event(0x202,kind=0x382,payload=ENTRY))[0].payload[:4],bytes(4))
            s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))
            clock=[0.0];s.dungeon_run.clock=lambda:clock[0];load(s)
            # An early completion packet cannot advance the task.
            s.handle(Event(0x202,kind=0xbb,payload=bytes((s.dungeon_run.part,))))
            self.assertEqual(q.snapshot()['active'][0]['objectives'],{47293:0})
            if level_up:set_level(level+1)
            rooms=finish(s,clock)
            self.assertGreater(rooms,1);self.assertIsNotNone(s.reward_receipt)
            expected=int(level==32)
            self.assertEqual(q.snapshot()['active'][0]['objectives'],{47293:expected})
            self.assertEqual(s._quest_run_levels[s.dungeon_run.run_id],level)
            self.assertEqual(QuestState(path,account_id=1).snapshot(),q.snapshot())
            for _ in range(3):s.periodic_notifications()
            self.assertEqual(q.snapshot()['active'][0]['objectives'],{47293:expected})

    def test_boundary32_counts_after_admitted_full_route_and_reward(self):
        self.run_clear(32)

    def test_outside33_does_not_count_after_admitted_full_route(self):
        self.run_clear(33)

    def test_entry_level_snapshot_survives_level_up_before_clear(self):
        self.run_clear(32,level_up=True)

if __name__=='__main__':unittest.main()
