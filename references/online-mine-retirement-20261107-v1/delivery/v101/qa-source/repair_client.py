"""Exercise ordinary30252 admission, first-room combat and real mine retirement."""
import math,struct,uuid
from protocol_client import connect
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.formal_npc_hp import f32,initialization_factor
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

def emitted_npc(n,stage):
 init=n.get('init')or bytes.fromhex(n['init_hex']);tag=struct.pack('>i',n['key'])+init[:-98]
 offset=stage.payload.find(tag);assert offset>=0 and stage.payload.find(tag,offset+1)<0
 base_hp=struct.unpack_from('>f',stage.payload,offset+len(tag)+4)[0]
 # B2 supplies the base. Original1AE1290 applies this already verified
 # ordinary-route difficulty factor before DYING_END reports current HP.
 hp=f32(base_hp*initialization_factor(30252));assert math.isfinite(hp)and hp>0
 return dict(n,hp=hp)

def death(n,uid,mine=False):
 if mine:
  return(struct.pack('>iBQQ6fBf',n['key'],255,2**64-1,2**64-1,*([0.]*6),1,n['hp'])
   +bytes(4)+struct.pack('>IQB',1,uid,0)+bytes(20))
 return(struct.pack('>iBQQ6fBf',n['key'],0,uid,uid,*([0.]*6),0,n['hp'])
  +struct.pack('>IIQBQIQ',0,1,uid,0,0,0,uid))

async def scenario(values,snapshot,report,expire=None):
 peers=[]
 try:
  assert len(values)==1 and values[0]['unit_type']==1
  p=await connect(values[0],peers);uid=values[0]['uid'];run=DungeonRun(30252,str(uuid.uuid4()))
  await p.send(0x7d4,struct.pack('>ii',1,30252));assert(await p.until(0x7d5)).payload[:4]==bytes(4)
  await p.send(0x382,ENTRY);assert(await p.until(0x383)).payload[:4]==bytes(4);await p.until(0x14a)
  await p.send(0x91,struct.pack('>ii',100,0));stage=await p.until(0xb2)
  await p.send(0xb3,bytes(9));await p.until(0xbd)
  first=[emitted_npc(n,stage)for n in run.current['npcs']if n['active']and n.get('team',1)!=0]
  for npc in first:
   await p.send(0xad,death(npc,uid));assert(await p.until(0xae)).payload==bytes(4)
  assert(await p.until(0xb7)).payload==b'\1'
  await p.send(0xb8,b'\1');assert(await p.until(0xb9)).payload==bytes(4);assert(await p.until(0xba)).payload==b'\1'
  await p.send(0xbb,b'\1');assert(await p.until(0xbc)).payload==bytes(4);await p.until(0xbd)
  run.part=1
  mines=[emitted_npc(n,stage)for n in run.current['npcs']if n['template']==241]
  assert len(mines)==2
  before=snapshot()
  for npc in mines:
   body=death(npc,uid,True);await p.send(0xad,body);assert(await p.until(0xae)).payload==bytes(4);await p.until(0xaf)
   await p.query(0x48d,reply=0x48f);mark=sum(e.kind==0xaf for e in p.received)
   await p.send(0xad,body);assert(await p.until(0xae)).payload==bytes(4)
   await p.query(0x48d,reply=0x48f);assert sum(e.kind==0xaf for e in p.received)==mark
  after=snapshot();assert before==after
  report.update(ok=True,actual_Application=True,actual_authenticated_TLS=True,ordinary_30252_admission=True,
   ordinary_first_part_combat_and_transition=True,mines_retired=len(mines),mine_keys=[n['key']for n in mines],
   first_AE_empty_AF=True,retry_AE_only=True,mine_economy_unchanged=True,connection_kept=True,
   forced_server_scene=False,natural_GUI=False,natural_battle=False,experimental_send_hook_loaded=False)
 finally:
  for p in reversed(peers):await p.close()
