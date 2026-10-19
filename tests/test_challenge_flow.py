"""Protocol replay of every challenge node; death reports are test fixtures."""
import struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.dungeon_routes import route_catalog
from els_server.storage.local_state import LocalState
from els_server.storage.challenge_state import ChallengeState
from els_server.protocol.protocol_codec import Event
from test_dungeon_routes import start,finish
from test_dungeon_routes import ENTRY
from unittest.mock import patch

def town(path):
 s=LocalSession(LocalAccount(LocalState(path)),True,True,'dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
 s.role='game';s.phase='town_ready';return s

class ChallengeFlowTests(unittest.TestCase):
 def test_local_client_gets_owned_room_before_phase_and_clears_it_on_give_up(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';s=town(path);s.account.enable_characters()
   # Region prerequisites have separate integration coverage. This fixture
   # isolates ownership/room lifecycle from those tasks.
   with patch('els_server.domain.region_quests.account_dungeon_allowed',return_value=True):
    begin=Event(0x202,kind=0xae2,payload=struct.pack('>ii',4,1))
    reply=s.handle(begin);self.assertEqual([e.kind for e in reply],[0xae3,0x13b,0xae6])
    room=s.solo_challenge_party;self.assertEqual(room['members'][0].account.uid,s.account.uid)
    denied=s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30092)))
    self.assertEqual(denied[0].payload[:4],struct.pack('>i',2224))
    s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,34850)))
    reply=s.handle(Event(0x202,kind=0x382,payload=ENTRY))
    self.assertEqual([e.kind for e in reply],[0x383,0x14a,0xae6])
    self.assertEqual(struct.unpack_from('>Q',reply[1].payload,3)[0],room['id'])
    s.phase='town_ready'
    reply=s.handle(Event(0x202,kind=0xae7,payload=bytes([255])*8))
    self.assertEqual([e.kind for e in reply],[0xae8,0x13c,0xae6]);self.assertIsNone(s.solo_challenge_party)
    self.assertEqual(s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30092)))[0].payload[:4],bytes(4))

 def test_every_phase_completes_and_can_start_again(self):
  for p in route_catalog()._data['challenges']:
   with self.subTest(phase=(p['challenge'],p['phase'])),tempfile.TemporaryDirectory() as d:
    path=Path(d)/'save.sqlite3';s=town(path);begin=Event(0x202,kind=0xae2,payload=struct.pack('>ii',p['challenge'],p['phase']))
    reply=s.handle(begin);self.assertEqual([e.kind for e in reply],[0xae3,0xae6]);self.assertEqual(reply[0].payload[:4],bytes(4))
    ledger=ChallengeState(path,1001);attempt=ledger.current()['attempt']
    final=p['nodes'][-1]['dungeon'];bad=s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,final)))
    self.assertEqual(bad[0].payload[:4],struct.pack('>i',817))
    clears=0
    for node in p['nodes']:
     for _ in range(node['count']):
      running,t=start(node['dungeon'],path);finish(running,t);clears+=1
      self.assertIsNotNone(running.reward_receipt);self.assertFalse(getattr(running,'dungeon_failed',False))
    self.assertTrue(ledger.current()['complete']);self.assertEqual(running.account.get_reward_balances()['ed'],120*clears)
    s=town(path);s.handle(begin);self.assertNotEqual(ledger.current()['attempt'],attempt);self.assertEqual(ledger.current()['progress'],0)
    self.assertEqual([e.kind for e in s.handle(Event(0x202,kind=0xae7,payload=bytes([255])*8))],[0xae8,0xae6])
    self.assertIsNone(ledger.current())

 def test_expiry_and_stale_phase_admission_fail_without_rewards(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';s=town(path);s.handle(Event(0x202,kind=0xae2,payload=struct.pack('>ii',4,1)))
   running,t=start(34850,path);running.challenge_deadline=0
   reply=running.periodic_notifications();self.assertTrue(any(e.kind==0xc1 and e.payload[16]==0 for e in reply))
   self.assertTrue(running.dungeon_failed);self.assertIsNone(running.reward_receipt);self.assertEqual(running.account.get_reward_balances()['ed'],0)
   self.assertFalse(any(e.kind==0xc1 for e in running.periodic_notifications()))
   ledger=ChallengeState(path,1001);ledger.abandon()
   reply=s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,34850)))
   self.assertEqual(reply[0].payload[:4],struct.pack('>i',817))

if __name__=='__main__':unittest.main()
