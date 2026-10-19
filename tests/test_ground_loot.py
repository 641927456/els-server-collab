"""Native item bodies, issued ED authority, atomic pickup and food isolation."""
import hashlib,json,sqlite3,struct,sys,tempfile,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.drop_pickup import ground_pickup_request,native_modes,GROUND_TEMPLATES
from els_server.domain.dungeon_drops import ground_drop_notice,ground_pickup_notice
from els_server.domain.reward_rules import ground_loot
from els_server.domain.local_session import LocalSession,LocalAccount
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event
source=json.loads((ROOT/'analysis/client-6c6b5180/20261014-002737/world-drop-probe-snapshot.json').read_text(encoding='utf8'))
wire=bytes.fromhex(next(e['payload_hex'] for e in source['server'] if e.get('kind')==0xd0 and e.get('event')=='decoded_client_event'))
BODY=wire[:320];XYZ=tuple(source['issued'][0]['xyz'])

def request(template,drop_id=910001,mode=4,*,player_xyz=XYZ,drop_xyz=XYZ):
 out=b''
 for field in native_modes()[mode]['fields']:
  k=field['field'];mask=field.get('xor',0)
  if k=='item':out+=struct.pack('>I',template)+BODY[4:]
  elif k=='opaque':out+=struct.pack('>I',3)+b'abc'
  elif k=='drop_id':out+=struct.pack('>I',drop_id^mask)
  elif k=='flag':out+=bytes([mask])
  else:out+=struct.pack('>3f',*(player_xyz if k=='player_xyz' else drop_xyz))
 return Event(0x202,performers=(0,),kind=0xd0,payload=out)

def session(path):
 s=LocalSession(LocalAccount(LocalState(path)),enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,drop_probe=True,drop_test=True)
 s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True;s.reward_run_id=str(uuid.uuid4());return s

def issue(s,template,drop_id=910001,ed=0):
 s.world_drops[drop_id]=dict(run_id=s.reward_run_id,stage=0,npc_key=0,drop_id=drop_id,owner=1001,template=template,ed=ed,xyz=XYZ,payload_hex=ground_drop_notice(drop_id,XYZ,template=template).payload.hex(),death_proof_sha256=hashlib.sha256(b'verified death').hexdigest(),pickup_committed=False)

class GroundLootTests(unittest.TestCase):
 def test_remote_pet_pickup_requires_active_owned_entitlement(self):
  from els_server.storage.inventory_state import grant_items
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
  from els_server.storage.companion_state import handle as companion,snapshot
  from els_server.storage.pet_support import handle as support
  from els_server.protocol.local_messages import wstring
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'pet.sqlite3';s=session(path);a=s.account
   a.enable_characters();a.get_inventory_snapshot();issue(s,127000,ed=10)
   remote=request(127000,player_xyz=(5000,0,0),drop_xyz=(5005,-10,8))
   self.assertEqual(s.handle(remote),[])
   with closing(sqlite3.connect(path)) as db,db:
    items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1) for t in (550427,500720)])
   petitem=next(i for i in items if i['template']==550427);coupon=next(i for i in items if i['template']==500720)
   companion(path,1001,0x2e8,struct.pack('>Q',petitem['uid'])+wstring('Collector'),'activate')
   pet=snapshot(path,1001)['companions'][0]['uid']
   self.assertEqual(s.handle(remote),[])
   support(path,1001,0x219,struct.pack('>QQiiIB',coupon['uid'],pet,0,0,0,0),'unlock')
   companion(path,1001,0x2ec,struct.pack('>Q',0),'cancel')
   self.assertEqual(s.handle(remote),[])
   companion(path,1001,0x2ec,struct.pack('>Q',pet),'summon')
   self.assertEqual(s.handle(request(127000,player_xyz=(5000,0,0),drop_xyz=(5011,0,0))),[])
   self.assertEqual(s.handle(request(127000,910002,player_xyz=(5000,0,0),drop_xyz=(5005,-10,8))),[])
   self.assertEqual([e.kind for e in s.handle(remote)],[0xd1,0xd2])
   self.assertEqual([e.kind for e in s.handle(remote)],[0xd1])
   self.assertEqual(a.reward_store.balances()['ed'],10)

 def test_native_modes_and_reject_forgery(self):
  for template in GROUND_TEMPLATES:
   for mode in range(20):
    decoded=ground_pickup_request(request(template,mode=mode).payload)
    self.assertEqual((decoded['template'],decoded['native_mode'],decoded['drop_id']),(template,mode,910001))
  for offset in (4,8,100,319):
   bad=bytearray(request(127000).payload);bad[offset]^=1
   with self.assertRaises(ValueError):ground_pickup_request(bytes(bad))
  with self.assertRaises(ValueError):ground_pickup_request(request(274333).payload)

 def test_ed_receipt_no_inventory_and_current_retry(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';s=session(path);issue(s,127000,ed=10);issue(s,127010,910002,ed=50)
   before=s.account.get_inventory_snapshot()['items']
   first=s.handle(request(127000));self.assertEqual([e.kind for e in first],[0xd1,0xd2])
   self.assertEqual(struct.unpack_from('>ii',first[-1].payload,38),(10,0))
   self.assertEqual(s.handle(request(70000)),[])
   s.handle(request(127010,910002));self.assertEqual(s.account.reward_store.balances()['ed'],60)
   self.assertEqual([e.kind for e in s.handle(request(127000))],[0xd1])
   self.assertEqual(s.account.get_inventory_snapshot()['items'],before)
   self.assertEqual(LocalAccount(LocalState(path)).get_reward_balances()['ed'],60)
   with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('select count(*) from reward_receipts').fetchone()[0],2)

 def test_food_and_concurrent_coin_pickup_once(self):
  with tempfile.TemporaryDirectory() as d:
   s=session(Path(d)/'save.sqlite3');issue(s,70040);issue(s,127020,910002,100)
   before=s.account.get_inventory_snapshot()['items']
   self.assertEqual([e.kind for e in s.handle(request(70040))],[0xd1,0xd2])
   self.assertEqual([e.kind for e in s.handle(request(70040))],[0xd1])
   with ThreadPoolExecutor(max_workers=6) as pool:replies=list(pool.map(lambda _:s.handle(request(127020,910002)),range(6)))
   self.assertEqual(sum(any(e.kind==0xd2 for e in r) for r in replies),1)
   self.assertEqual(s.account.reward_store.balances()['ed'],100)
   self.assertEqual(s.account.get_inventory_snapshot()['items'],before)

 def test_currency_transaction_rollback(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';s=session(path);issue(s,127000,ed=10)
   with closing(sqlite3.connect(path)) as db,db:db.execute("CREATE TRIGGER fail_coin BEFORE INSERT ON reward_receipts BEGIN SELECT RAISE(ABORT,'injected'); END")
   with self.assertRaises(sqlite3.IntegrityError):s.handle(request(127000))
   self.assertEqual(s.account.reward_store.balances()['ed'],0);self.assertFalse(s.world_drops[910001]['pickup_committed'])

 def test_native_chest_and_no_drop_rules(self):
  run=str(uuid.uuid4());npc=dict(key=1,template=20,active=False,no_drop=False)
  loot=ground_loot(30000,npc,run,2,0)
  self.assertEqual(loot,ground_loot(30000,npc,run,2,0));self.assertEqual(len(loot),1)
  self.assertIn(loot[0]['template'],(70000,70010,70020,70030,70040,70050));self.assertEqual(loot[0]['ed'],0)
  self.assertEqual(ground_loot(30000,{**npc,'no_drop':True},run,2,0),[])
  self.assertEqual(ground_loot(30000,{**npc,'template':625},run,2,0),[])
  mob={**npc,'template':618,'active':True}
  self.assertEqual(ground_loot(30000,mob,run,0,0)[0],dict(template=127000,ed=10,quantity=0))
  self.assertEqual(ground_loot(30000,{**mob,'template':5},run,2,1),[dict(template=127010,ed=50,quantity=0)])
  self.assertEqual(len(ground_loot(30000,mob,run,0,0)),1)
  self.assertEqual(ground_loot(30000,{**mob,'template':123456},run,0,0),[])

if __name__=='__main__':unittest.main()
