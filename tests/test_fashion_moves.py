"""Equip, occupied-slot swaps, unequip, forged destinations and SQL rollback."""
import json,sqlite3,struct,sys,tempfile,uuid
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reward_state import RewardState
from inventory_state import InventoryState
from inventory_items import FASHION_EQUIP_SLOTS
from fashion_state import move_fashion,move_request,equipment_map
from dungeon_messages import return_user_sync
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event

def request(sg,ss,dg,ds):return struct.pack('>BiBiB',sg,ss,dg,ds,0)
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'save.sqlite3';rewards=RewardState(path);inventory=InventoryState(path)
 rewards.grant(str(uuid.uuid4()),b'two outfits',200,50,lambda _:b'ok',item_plan=[dict(template=t,metadata=0,quantity=1,group=27) for t in (81021,81101,81025)])
 original=inventory.snapshot();uids={i['template']:i['uid'] for i in original['items']}
 ack=move_fashion(path,request(27,0,9,2));assert len(ack)==656 and ack[:4]==struct.pack('>I',2) and ack[-4:]==bytes(4)
 state=inventory.snapshot();assert state['balances']==original['balances']
 assert next(i for i in state['items'] if i['uid']==uids[81021])['group']==9
 # A repeated equip from the now-empty slot cannot move or mint another item.
 try:move_fashion(path,request(27,0,9,2))
 except ValueError:pass
 else:raise AssertionError('Empty source accepted')
 assert inventory.snapshot()==state
 move_fashion(path,request(27,1,9,2));state=inventory.snapshot()
 assert {(i['template'],i['group'],i['slot']) for i in state['items']}=={(81021,27,1),(81101,9,2),(81025,27,2)}
 assert equipment_map(state['items'])[:19]==struct.pack('>IiQBh',1,2,uids[81101],9,2)
 assert InventoryState(path).snapshot()==state
 assert len(return_user_sync(None,None,state['balances'],state['items']).payload)>1000
 before=state
 for payload in (request(27,2,9,2),request(9,2,9,0),request(27,35,9,2),request(27,1,6,0),request(27,-1,9,2),b'bad',request(27,1,9,2)[:-1]+b'\1'):
  try:move_fashion(path,payload)
  except ValueError:pass
  else:raise AssertionError('Forged/incompatible move accepted')
  assert inventory.snapshot()==before
 # Unequip to free slot, UID and item count unchanged.
 move_fashion(path,request(9,2,27,0));state=inventory.snapshot()
 assert not any(i['group']==9 for i in state['items']) and equipment_map(state['items'])==bytes(4)
 # An encoder failure or SQL failure cannot leave a deleted source behind.
 with closing(sqlite3.connect(path)) as db,db:
  db.execute("CREATE TRIGGER fail_move BEFORE INSERT ON fashion_moves BEGIN SELECT RAISE(ABORT,'test failure'); END")
 try:move_fashion(path,request(27,0,9,2))
 except sqlite3.IntegrityError:pass
 else:raise AssertionError('Failure not injected')
 assert inventory.snapshot()==state and {i['uid'] for i in state['items']}==set(uids.values())
 assert state['balances']==original['balances']
 # Real session gate: no unauthenticated or in-dungeon mutation.
 with closing(sqlite3.connect(path)) as db,db:db.execute('DROP TRIGGER fail_move')
 account=LocalAccount(LocalState(path))
 s=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
 ev=Event(0x202,kind=0x104,payload=request(27,0,9,2))
 assert s.handle(ev)[0].payload==bytes(4)+struct.pack('>i',-1)
 assert inventory.snapshot()==state
 s.role='game';s.phase='town_ready';answer=s.handle(ev)
 assert len(answer)==1 and answer[0].kind==0x105 and answer[0].payload[-4:]==bytes(4)
 equipped=inventory.snapshot();assert any(i['group']==9 for i in equipped['items'])
 s.phase='dungeon_active';assert s.handle(Event(0x202,kind=0x104,payload=request(9,2,27,0)))[0].payload[-4:]==struct.pack('>i',-1)
 assert inventory.snapshot()==equipped
 # A real scene-ready transition sends exactly one fresh equipment snapshot;
 # it does not replay a move or increment any persistence records.
 s.phase='square_accepted';s.pending_map=20000;s.inventory_town_sync_sent=True
 ready=Event(0x202,kind=0x227,payload=struct.pack('>fffBH',0,0,0,0,0))
 sync=s.handle(ready);assert [e.kind for e in sync]==[0x228,0x105]
 sync=sync[1:]
 assert sync[0].payload[:4]==struct.pack('>I',1) and sync[0].payload[-4:]==bytes(4)
 assert s.periodic_notifications()==[] and inventory.snapshot()==equipped
 assert [e.kind for e in s.handle(ready)]==[0x228]
 assert s.periodic_notifications()==[]
 # Initial D9 must precede 105, even when shop availability is also pending.
 s.phase='square_accepted';s.inventory_town_sync_sent=False;s.shop_test=True
 assert [e.kind for e in s.handle(ready)]==[0x228,0xd9,0x105]
 assert all(e.kind!=0x105 for e in s.periodic_notifications())
 assert inventory.snapshot()==equipped
print('PASS: fashion equip/swap/unequip, UID conservation, durable recovery, invalid slots and transaction rollback.')
