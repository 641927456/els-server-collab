"""Pet gesture protocol never grants skills or replays a movement on retry."""
import struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage.companion_state import handle,snapshot
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event
import sqlite3
from contextlib import closing

with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'pet.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters();a.get_inventory_snapshot()
 s=LocalSession(a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True);s.role='game';s.phase='town_ready'
 req=Event(0x202,kind=0x2ef,payload=bytes((13,255,0,0,0)))
 assert s.handle(req,1)[0].payload==struct.pack('>i',-1)
 with closing(sqlite3.connect(path)) as db:
  item=grant_items(db,[dict(template=550427,metadata=VERIFIED_TEMPLATES[550427],group=TEMPLATE_BAG_GROUPS[550427],quantity=1)])[0];db.commit()
 handle(path,1001,0x2e8,struct.pack('>Q',item['uid'])+wstring('Pet'),'activate')
 pet=snapshot(path,1001)['companions'][0]
 handle(path,1001,0x2ec,struct.pack('>Q',pet['uid']),'summon')
 before=snapshot(path,1001);reply=s.handle(req,2)
 assert [r.kind for r in reply]==[0x2f0,0x2f1]
 assert reply[1].payload==struct.pack('>QBBB',1001,13,255,0)
 assert [r.kind for r in s.handle(req,2)]==[0x2f0]
 assert s.handle(Event(0x202,kind=0x2ef,payload=bytes((4,255,0,0,0))),2)[0].payload==struct.pack('>i',-1)
 assert snapshot(path,1001)==before
 for raw in (b'',bytes((26,255,0,0,0)),bytes((13,2,0,0,0)),bytes((13,255,2,0,0))):
  assert s.handle(Event(0x202,kind=0x2ef,payload=raw),3)[0].payload==struct.pack('>i',-1)
 s.phase='dungeon_loading';assert s.handle(req,4)[0].payload==struct.pack('>i',-1)
 s.phase='dungeon_active';assert [r.kind for r in s.handle(req,5)]==[0x2f0,0x2f1]
 handle(path,1001,0x2ec,struct.pack('>Q',0),'cancel')
 assert s.handle(req,6)[0].payload==struct.pack('>i',-1)
print('PASS: owned active pet gesture, original wire, phases, duplicate suppression and no persistent skill grants.')
