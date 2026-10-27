"""Mount packet admission, exhaustion and release through proposed session hooks."""
import inspect,sqlite3,struct,sys,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.protocol.protocol_codec import Event
from els_server.domain import mount_flow

class MountFlowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);path=Path(self.temp.name)/'save.sqlite3'
  clock=patch('els_server.storage.mount_state.time.time',return_value=1000);self.clock=clock.start();self.addCleanup(clock.stop)
  a=LocalAccount(LocalState(path));a.enable_characters();a.get_inventory_snapshot()
  with closing(sqlite3.connect(path)) as db,db:items=grant_items(db,[dict(template=550431,metadata=VERIFIED_TEMPLATES[550431],group=4,quantity=1)])
  activate(path,1001,0x432,struct.pack('>Q',items[0]['uid']),'activate');self.path=path
  self.uid=next(p['uid'] for p in snapshot(path,1001)['companions'] if p['kind']=='mount')
  self.session=LocalSession(a,client_build='dx11_260923',enter_dungeon=True,npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True);self.session.role='game';self.session.phase='town_ready'
 def request(self,kind,payload,sequence=10):return Event(0x202,kind=kind,payload=payload),sequence
 def summon(self):
  e,n=self.request(0x42c,struct.pack('>QB',self.uid,1));return mount_flow.handle(self.session,e,n)
 def test_native_admission_and_no_fake_skill_rpc(self):
  self.session.phase='dungeon_loading';self.assertEqual(struct.unpack_from('>i',self.summon()[0].payload)[0],-1)
  self.session.phase='town_ready';reply=self.summon();self.assertEqual(reply[0].kind,0x42d)
  # Ordinary attacks stay in the original riding state/script; this handler
  # must not steal an unverified ordinary combat event.
  self.assertIsNone(mount_flow.handle(self.session,Event(0x202,kind=0x100,payload=b'x'),11))
 def test_late_dismount_after_exhaustion_is_harmless(self):
  self.summon();self.clock.return_value=1300
  self.assertEqual([x.kind for x in mount_flow.periodic(self.session)],[0x430])
  self.clock.return_value=1301;e,n=self.request(0x42f,struct.pack('>Qi',self.uid,0),12)
  reply=mount_flow.handle(self.session,e,n);self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
 def test_close_settles_and_never_drains_offline(self):
  self.summon();self.clock.return_value=1024;mount_flow.close(self.session);mount_flow.close(self.session)
  self.assertFalse(self.session.mount_touched)
  with closing(sqlite3.connect(self.path)) as db:self.assertAlmostEqual(db.execute('SELECT stamina FROM mount_runtime').fetchone()[0],110,places=4)
 def test_character_switch_closes_original_owner(self):
  self.summon();self.clock.return_value=1024
  self.session.account=SimpleNamespace(uid=1002,store=SimpleNamespace(path=self.path))
  mount_flow.observe(self.session)
  with closing(sqlite3.connect(self.path)) as db:
   self.assertEqual(db.execute('SELECT owner,mount,mounted FROM companion_active').fetchall(),[(1001,0,0)])
   self.assertEqual(db.execute('SELECT owner,ridden FROM mount_runtime').fetchall(),[(1001,0)])
 def test_session_hooks_when_installed(self):
  # This case is run by mount_test_integration.py with only the five reviewed
  # shared candidates imported. Direct base-source execution skips the gate.
  if 'mount_flow' not in inspect.getsource(LocalSession.periodic_notifications):self.skipTest('Run tools/mount_test_integration.py for proposed shared hooks')
  e,n=self.request(0x42c,struct.pack('>QB',self.uid,1));reply=self.session.handle(e,n)
  self.assertEqual(reply[0].kind,0x42d);self.clock.return_value=1300
  self.assertIn(0x430,[x.kind for x in self.session.periodic_notifications()])
  self.assertEqual(snapshot(self.path,1001)['mount'],0)

if __name__=='__main__':unittest.main()
