"""Verify phase/preview authorization and transport-operation replay at the router."""
import sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_session import LocalAccount,LocalSession
from local_state import LocalState
from inventory_state import grant_items,load_items
from protocol_codec import Event
args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,ice_test=True)
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'ice.sqlite3';account=LocalAccount(LocalState(path));session=LocalSession(account,**args)
 session.role='game';session.phase='town_ready'
 with closing(sqlite3.connect(path)) as db,db:
  uid=grant_items(db,[dict(template=800000,metadata=2,group=4,quantity=2)])[0]['uid']
 use=Event(0x202,kind=0x196,payload=struct.pack('>QBBBIi',uid,0,0,0,0,0))
 preview=Event(0x202,kind=0x559,payload=struct.pack('>iIiBB',800000,1,0,0,0))
 result=lambda packets:struct.unpack_from('>i',packets[-1].payload)[0]
 assert result(session.handle(use,10))!=0
 assert result(session.handle(preview,11))==0
 for seq in (None,0,-1,2**32,True):assert result(session.handle(use,seq))!=0
 session.phase='dungeon_active';assert result(session.handle(use,12))!=0
 session.phase='town_ready';first=session.handle(use,12);assert result(first)==0
 assert [e.kind for e in first]==[0xad8,0x197]
 assert struct.unpack_from('>I',first[0].payload)[0]==2 and len(first[0].payload)==652
 assert session.handle(use,12)==first
 with closing(sqlite3.connect(path)) as db:
  assert next(i for i in load_items(db) if i['uid']==uid)['count']==1
  assert db.execute('SELECT COUNT(*) FROM ice_draw_receipts').fetchone()[0]==1
  before=list(db.iterdump())
 conflict=Event(0x202,kind=0x196,payload=struct.pack('>QBBBIi',uid+1,0,0,0,0,0))
 assert result(session.handle(conflict,12))!=0
 with closing(sqlite3.connect(path)) as db:assert list(db.iterdump())==before
print('PASS: phase/preview/sequence guards, session replay, conflicting request rollback.')
