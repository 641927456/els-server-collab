"""Native scene-change companion release (542) mirrors the ride state.

Evidence (analysis/client-6c6b5180): every witnessed 1346 follows a
dismount ack or arrives on entering a dungeon while mounted, and the
server never answered it. Leaving mounted=1 drained ride stamina while
the client no longer showed the pet, so later town summons failed as
exhausted (session 20261026-231058 15:14:50 server-initiated 0x430).
"""
import sqlite3,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.storage.mount_state import handle,recall,attach
from els_server.domain.mount_flow import handle as flow
from els_server.protocol.protocol_codec import Event

def fake_session(account,phase='dungeon_active'):
 class Session:
  item_test=True;client_build='dx11_260923';role='game'
  def __init__(self):
   self.account=account;self.phase=phase
 return Session()

class RecallTests(unittest.TestCase):
 def setUp(self):
  clock=patch('els_server.storage.mount_state.time.time',return_value=1000);clock.start();self.addCleanup(clock.stop)
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'save.sqlite3'
  self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.account.get_inventory_snapshot()
  with closing(sqlite3.connect(self.path)) as db,db:
   items=grant_items(db,[dict(template=550431,metadata=VERIFIED_TEMPLATES[550431],group=4,quantity=2)])
  for i,item in enumerate(items):activate(self.path,1001,0x432,struct.pack('>Q',item['uid']),'activate'+str(i))
  self.uid=next(p['uid'] for p in snapshot(self.path,1001)['companions'] if p['kind']=='mount')
 def active(self):
  with closing(sqlite3.connect(self.path)) as db:
   return db.execute('SELECT mount,mounted FROM companion_active WHERE owner=1001').fetchone() or (0,0)
 def saved(self,now):
  with closing(sqlite3.connect(self.path)) as db,db:
   pets=snapshot(self.path,1001)['companions'];attach(db,1001,pets,now=now)
   return {p['uid']:p for p in pets}
 def ride(self,now=1000):return handle(self.path,1001,0x42c,struct.pack('>QB',self.uid,1),'ride',now=now)
 def down(self,now=1024):return handle(self.path,1001,0x42f,struct.pack('>Qi',self.uid,0),'down',now=now)
 def five42(self,phase='dungeon_active'):
  session=fake_session(self.account,phase)
  replies=flow(session,Event(0x202,kind=0x542,payload=b'\0'*8),1)
  return session,replies

 def test_recall_after_ride_settles_and_releases(self):
  self.ride(now=1000)
  mount=recall(self.path,1001,now=1024)
  self.assertEqual(mount['uid'],self.uid)
  self.assertEqual(self.active(),(0,0))
  # 24 ridden seconds at 2.4 s per point: 110 remain, clock committed.
  self.assertAlmostEqual(self.saved(1024)[self.uid]['stamina'],110,places=4)
  self.assertFalse(self.saved(1024)[self.uid]['ridden'])
  # A second recall is a no-op; stamina keeps recovering on foot.
  self.assertIsNone(recall(self.path,1001,now=1096))
  self.assertAlmostEqual(self.saved(1096)[self.uid]['stamina'],120,places=4)

 def test_recall_without_mount_is_noop(self):
  self.assertIsNone(recall(self.path,1001,now=1000))
  self.assertEqual(self.active(),(0,0))

 def test_recall_after_manual_dismount_is_noop(self):
  self.ride();self.down()
  self.assertIsNone(recall(self.path,1001,now=1024))
  self.assertEqual(self.active(),(0,0))

 def test_flow_consumes_542_silently_and_releases(self):
  self.ride(now=1000)
  session,replies=self.five42()
  self.assertEqual(replies,[])
  self.assertEqual(self.active(),(0,0))
  self.assertTrue(session.mount_touched)
  self.assertEqual(session._mount_rejection,None)

 def test_flow_consumes_542_when_on_foot(self):
  session,replies=self.five42()
  self.assertEqual(replies,[])
  self.assertEqual(self.active(),(0,0))

 def test_flow_542_outside_play_phases_keeps_state(self):
  self.ride(now=1000)
  session,replies=self.five42(phase='closing')
  self.assertEqual(replies,[])
  self.assertEqual(self.active(),(self.uid,1))

 def test_flow_542_does_not_disturb_town_dismount_cycle(self):
  # Town cycle: 42C up, 42F down, then the client's own 542 notice.
  self.ride();self.down(now=1024)
  session,replies=self.five42()
  self.assertEqual(replies,[])
  self.assertAlmostEqual(self.saved(1024)[self.uid]['stamina'],110,places=4)
  # Re-summon after the notice still works.
  session=fake_session(self.account,'town_ready');session.shop_session_id='shop'
  answers=flow(session,Event(0x202,kind=0x42c,payload=struct.pack('>QB',self.uid,1)),2)
  self.assertEqual([a.kind for a in answers],[0x42d])
  self.assertEqual(self.active(),(self.uid,1))

 def test_flow_542_stops_the_phantom_ride_drain(self):
  # Riding into a dungeon: client auto-releases and sends 542; without the
  # mirror the clock kept draining to exhaustion during the dungeon run.
  self.ride(now=1000)
  self.five42()
  # A later summon succeeds without the exhaustion refusal.
  answer=handle(self.path,1001,0x42c,struct.pack('>QB',self.uid,1),'again',now=1096)
  self.assertEqual(answer.kind,0x42d)

if __name__=='__main__':unittest.main()
