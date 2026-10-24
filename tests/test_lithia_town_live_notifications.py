"""Native live notifications must not reset the finite Lithia town guide."""
import struct,unittest
from unittest.mock import patch
from tests.test_lithia_first_entry_handoff import Flow as FirstEntryFixture
from els_server.domain.tutorial_quests import restore_initialization
from els_server.protocol import quest_messages as wire
class TownNotificationFlow(FirstEntryFixture):
 # Do not inherit and rerun unchanged old tests.
 def test_live_town_and_retry(self):
  for qid in (28000,28010,28020,28030):
   if qid==28030:self.send(0xfd,struct.pack('>i',10394))
   reply=self.claim(qid);kinds=[e.kind for e in reply]
   self.assertNotIn(0x2b,kinds)
   expected={28000:[28010,164993],28010:[28020],28020:[28030],28030:[28040]}[qid]
   self.assertEqual([struct.unpack_from('>i',e.payload)[0]for e in reply if e.kind==0xf0],expected)
   saved=self.a.get_inventory_snapshot();state=self.q.snapshot()
   retry=self.claim(qid)
   self.assertEqual(self.a.get_inventory_snapshot(),saved);self.assertEqual(self.q.snapshot(),state)
   self.assertEqual([e for e in retry if e.kind==0xf0],[])
   self.assertEqual(retry[0].payload[-1],0)
   self.assertNotIn(0x2b,[e.kind for e in retry])
  cold,_=restore_initialization(self.q);self.assertEqual(cold.kind,0x2b)
  # First-entry patch remains in the actual parent and progresses naturally.
  self.enter();self.assertIn(28040,self.q.completed())
  e=self.retirement(500,1);self.s.handle(e,self.seq+1);self.claim(28050)
  self.assertIn(28050,self.q.completed())
 def test_finite_original_F5_and_economy(self):
  r=self.claim(28000);self.assertEqual(r[0].kind,0xf5);self.assertEqual(r[0].payload[-2:],bytes(2))
  snapshot=self.a.get_inventory_snapshot()
  self.assertEqual(sum(i['count']for i in snapshot['items']if i['template']==79063),20)
  self.assertEqual(sum(i['count']for i in snapshot['items']if i['template']==79064),20)
  self.assertEqual(self.a.get_reward_balances()['ed'],0)
 def test_encode_failure_rolls_back_first_claim_and_successors(self):
  before=self.dump();original=wire.accepted
  def fail(row):
   if row['id']==28010:raise ValueError('injected successor preencoding error')
   return original(row)
  with patch.object(wire,'accepted',fail):reply=self.send(0xf4,struct.pack('>iiI5B',28000,0,0,0,0,1,1,0))
  self.assertNotEqual(reply[0].payload[:4],bytes(4));self.assertEqual(before,self.dump())
  self.claim(28000);self.assertIn(28000,self.q.completed())
for name in list(FirstEntryFixture.__dict__):
 if name.startswith('test_'):setattr(TownNotificationFlow,name,None)
