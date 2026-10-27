"""Persistent stamina conservation across riding, reconnect and rollback."""
import json,sqlite3,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.storage.mount_state import handle,attach,tick,login
from els_server.domain.mount_rules import advance,catalog

class MountTests(unittest.TestCase):
 def setUp(self):
  clock=patch('els_server.storage.mount_state.time.time',return_value=1000);clock.start();self.addCleanup(clock.stop)
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'save.sqlite3'
  self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.account.get_inventory_snapshot()
  with closing(sqlite3.connect(self.path)) as db,db:
   items=grant_items(db,[dict(template=550431,metadata=VERIFIED_TEMPLATES[550431],group=4,quantity=2)])
  for i,item in enumerate(items):activate(self.path,1001,0x432,struct.pack('>Q',item['uid']),'activate'+str(i))
  self.mounts=[p for p in snapshot(self.path,1001)['companions'] if p['kind']=='mount'];self.uid=self.mounts[0]['uid']
 def ride(self,uid=None,op='ride',now=1000):return handle(self.path,1001,0x42c,struct.pack('>QB',uid or self.uid,1),op,now=now)
 def down(self,op='down',now=1024):return handle(self.path,1001,0x42f,struct.pack('>Qi',self.uid,0),op,now=now)
 def saved(self,now):
  with closing(sqlite3.connect(self.path)) as db,db:
   pets=snapshot(self.path,1001)['companions'];attach(db,1001,pets,now=now)
   return {p['uid']:p for p in pets}
 def test_conservation_and_reconnect(self):
  self.ride();self.down();saved=self.saved(1024);self.assertAlmostEqual(saved[self.uid]['stamina'],110,places=4)
  self.assertFalse(saved[self.uid]['ridden'])
  with closing(sqlite3.connect(self.path)) as db,db:login(db,1001,now=1024)
  self.assertAlmostEqual(self.saved(1096)[self.uid]['stamina'],120,places=4)
  self.ride(op='again',now=1096);self.down(op='again-down',now=1120)
  self.assertAlmostEqual(self.saved(1120)[self.uid]['stamina'],110,places=4)
 def test_retry_switch_and_foreign_owner(self):
  self.ride();self.ride(now=1024);self.assertAlmostEqual(self.saved(1024)[self.uid]['stamina'],110,places=4)
  with self.assertRaises(ValueError):self.ride(uid=self.mounts[1]['uid'],now=1024)
  other=self.mounts[1]['uid'];self.ride(uid=other,op='switch',now=1024)
  states=self.saved(1096);self.assertEqual(states[self.uid]['stamina'],120);self.assertAlmostEqual(states[other]['stamina'],90,places=4)
  with self.assertRaises(ValueError):self.ride(op='ride',now=1096)
  with self.assertRaises(ValueError):handle(self.path,1002,0x42c,struct.pack('>QB',other,1),'steal',now=1096)
 def test_exhaustion_forces_down_once(self):
  self.ride();notices=tick(self.path,1001,now=1300)
  self.assertEqual([n.kind for n in notices],[0x430]);self.assertEqual(tick(self.path,1001,now=1300),[])
  self.assertEqual(self.saved(1300)[self.uid]['stamina'],0)
  with self.assertRaises(ValueError):self.ride(op='empty',now=1300)
  self.ride(op='rested',now=1372);self.assertAlmostEqual(self.saved(1372)[self.uid]['stamina'],10,places=4)
 def test_encoding_failure_rolls_back_state_and_clock(self):
  self.ride()
  def rows():
   with closing(sqlite3.connect(self.path)) as db:return {t:db.execute('SELECT * FROM '+t).fetchall() for t in ('mount_runtime','companion_active','mount_operations','inventory_items')}
  old=rows()
  with patch('els_server.protocol.mount_messages.dismounted',side_effect=ValueError('injected')):
   with self.assertRaises(ValueError):self.down()
   with self.assertRaises(ValueError):tick(self.path,1001,now=1300)
  self.assertEqual(rows(),old);self.down();self.assertAlmostEqual(self.saved(1024)[self.uid]['stamina'],110,places=4)
 def test_disconnect_no_offline_drain_and_clock_rollback(self):
  self.ride();tick(self.path,1001,now=1024,disconnect=True)
  self.assertAlmostEqual(self.saved(1024)[self.uid]['stamina'],110,places=4)
  self.assertEqual(self.saved(1096)[self.uid]['stamina'],120)
  self.ride(op='clock',now=2000);self.assertEqual(self.saved(1900)[self.uid]['stamina'],120)
  self.assertAlmostEqual(self.saved(2024)[self.uid]['stamina'],110,places=4)
 def test_rule_replay_matches_native_and_rejects_nan(self):
  proof=Path(__file__).resolve().parents[1]/'analysis/mount-combat-20261015/native-stamina-proof.json'
  unit=next(int(k) for k,v in catalog()['templates'].items() if v['recovery_rate']==120)
  for case in json.loads(proof.read_text(encoding='utf8'))['cases']:
   result=advance(unit if case['recovery_rate']==120 else 105,case['initial'],case['seconds'],case['ridden'])
   self.assertAlmostEqual(result,case['result'],places=5)
  for stamina in (float('nan'),float('inf'),-1,121):
   with self.assertRaises(ValueError):advance(105,stamina,1,True)
 def test_legacy_empty_save_is_not_mutated_by_periodic(self):
  path=Path(self.temp.name)/'empty.sqlite3';sqlite3.connect(path).close()
  self.assertEqual(tick(path,1001,now=1000),[])
  with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[])

if __name__=='__main__':unittest.main()
