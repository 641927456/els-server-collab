"""Decode real native mode0 DTO/wire pairs and grant/replay their issued drops."""
import json,struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from drop_pickup import potion_pickup_request,native_modes
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
w=json.loads((ROOT/'analysis/client-6c6b5180/20261014-015631/d0-current-process-layout-witness.json').read_text(encoding='utf8'))
assert len(native_modes())==20
for e in w['witnesses']:
 b=bytes.fromhex(e['native']['wire_hex']);r=potion_pickup_request(b);n=e['native']
 assert r['native_mode']==0 and r['drop_id']==n['drop_id'] and r['template']==n['template'] and r['quantity']==n['quantity']
 assert r['player_xyz']==tuple(n['xyz'][:3]) and r['drop_xyz']==tuple(n['xyz'][3:])
 for bad in (b[:-1],b+b'\0'):
  try:potion_pickup_request(bad)
  except ValueError:pass
  else:raise AssertionError('New native mode accepted a truncated/extended payload')
args={'enter_town':True,'enter_dungeon':True,'client_build':'dx11_260923','npc_slot_test':True,'gate_test':True,'population_test':True,'clear_test':True,'reward_test':True,'item_test':True,'drop_probe':True,'drop_test':True}
with tempfile.TemporaryDirectory() as directory:
 s=LocalSession(LocalAccount(LocalState(Path(directory)/'save.sqlite3')),**args);s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True;s.reward_run_id=w['witnesses'][0]['issued']['run_id']
 for e in w['witnesses']:
  d=dict(e['issued']);s.world_drops[d['drop_id']]=d
  reply=s.handle(Event(0x202,performers=(0,),kind=0xd0,payload=bytes.fromhex(e['native']['wire_hex'])))
  assert [r.kind for r in reply]==[0xd1,0xd2,0xd3]
 snap=s.account.get_inventory_snapshot();assert snap['items'][0]['count']==2 and snap['items'][0]['group']==6 and snap['balances']['revision']==2
 e=w['witnesses'][0];payload=bytes.fromhex(e['native']['wire_hex']);retry=s.handle(Event(0x202,performers=(0,),kind=0xd0,payload=payload))
 assert [r.kind for r in retry]==[0xd1,0xd3] and s.account.get_inventory_snapshot()==snap
 assert s.handle(Event(0x202,performers=(0,),kind=0xd0,payload=payload,payload_mode=1))==[]
print('PASS: real mode0 native DTO/network pairs, issued-drop grants to potion bag, latest-state replay and tagged-mode rejection.')
