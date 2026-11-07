"""Ordinary33242 entry/transition, original summon positions and real controllers."""
import math,struct
from protocol_client import connect
from els_server.domain.dungeon_routes import route_catalog,npc_initialization
from els_server.domain.dungeon_npcs import MODE0_FIELDS,resource_dto,encode_npc
from els_server.domain.formal_npc_hp import f32,initialization_factor
from els_server.domain.dungeon_lifecycle import empty_reward_death_notice
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
POSITIONS=((158188,635,-61369),(157998,329,-61369),(160270,681,-61369),(160435,346,-61369))

def npc_vector(payload,position,count):
 rows=[]
 for _ in range(count):
  dto=bytearray(0xa4)
  for offset,size,xor,kind in MODE0_FIELDS:
   raw=payload[position:position+size];assert len(raw)==size;position+=size
   if kind=='empty':assert int.from_bytes(raw,'big')==0;continue
   value=b''.join(raw[i:i+4][::-1]for i in(0,4,8))if size==12 else(int.from_bytes(raw,'big')^xor).to_bytes(size,'little')
   dto[offset:offset+size]=value
  rows.append(dict(key=struct.unpack_from('<i',dto)[0],template=struct.unpack_from('<i',dto,4)[0],active=bool(dto[0x4e]),team=0 if dto[0x66]else 1))
 return rows,position

def stage_actors(stage):
 stage_id,reserved,count=struct.unpack_from('>iiI',stage.payload);assert stage_id==reserved==0 and count==3
 position=12;parts={};catalog=route_catalog()
 for _ in range(count):
  part,opaque,n=struct.unpack_from('>iII',stage.payload,position);position+=12;assert opaque==0 and 0<=n<=80
  parts[part],position=npc_vector(stage.payload,position,n)
 for actors in parts.values():
  for npc in actors:
   init=npc_initialization(catalog,npc['template'],1.0)
   tag=struct.pack('>i',npc['key'])+init[:-98];offset=stage.payload.find(tag)
   assert offset>=0 and stage.payload.find(tag,offset+1)<0
   base=struct.unpack_from('>f',stage.payload,offset+len(tag)+4)[0]
   npc['hp']=f32(base*initialization_factor(33242));assert math.isfinite(npc['hp'])and npc['hp']>0
 return parts

def death(npc,uid,retirement=False):
 if retirement:
  return(struct.pack('>iBQQ6fBf',npc['key'],255,2**64-1,2**64-1,*([0.]*6),1,npc['hp'])
      +bytes(4)+struct.pack('>IQB',1,uid,0)+bytes(20))
 return(struct.pack('>iBQQ6fBf',npc['key'],0,uid,uid,*([0.]*6),0,npc['hp'])
     +struct.pack('>IIQBQIQ',0,1,uid,0,0,0,uid))

def summons():
 raw=bytearray.fromhex(route_catalog()._data['spawn_seed']);struct.pack_into('<ii',raw,0,-1,1375)
 dto=bytearray(resource_dto(raw));struct.pack_into('<Q',dto,0x6d,2**64-1)
 for offset in(0x4e,0x54,0x61,0x65,0x66):dto[offset]=0
 dto[0x4e]=1;rows=[]
 for xyz in POSITIONS:
  row=bytearray(dto);struct.pack_into('<fff',row,9,*xyz);rows.append(encode_npc(row,0))
 return struct.pack('>I',len(rows))+b''.join(rows)

async def scenario(values,snapshot,report,expire=None):
 peers=[]
 try:
  assert len(values)==1 and values[0]['unit_type']==1
  p=await connect(values[0],peers);uid=values[0]['uid']
  await p.send(0x7d4,struct.pack('>ii',1,33242));assert(await p.until(0x7d5)).payload[:4]==bytes(4)
  await p.send(0x382,ENTRY);assert(await p.until(0x383)).payload[:4]==bytes(4);await p.until(0x14a)
  await p.send(0x91,struct.pack('>ii',100,0));stage=await p.until(0xb2)
  await p.send(0xb3,bytes(9));await p.until(0xbd);parts=stage_actors(stage)
  first=[n for n in parts[0]if n['active']and n['team']!=0]
  for npc in first:
   await p.send(0xad,death(npc,uid));assert(await p.until(0xae)).payload==bytes(4)
  assert(await p.until(0xb7)).payload==b'\1'
  await p.send(0xb8,b'\1');assert(await p.until(0xb9)).payload==bytes(4);assert(await p.until(0xba)).payload==b'\1'
  await p.send(0xbb,b'\1');assert(await p.until(0xbc)).payload==bytes(4);await p.until(0xbd)
  before=snapshot();await p.send(0x2ce,summons());assert(await p.until(0x2cf)).payload==bytes(4)
  notice=await p.until(0x2d0);assert struct.unpack_from('>I',notice.payload)[0]==4
  spawned,_=npc_vector(notice.payload,4,4)
  assert len({n['key']for n in spawned})==4 and all(n['template']==1375 for n in spawned)
  assert not{n['key']for n in spawned}&{n['key']for a in parts.values()for n in a}
  actors=[n for n in parts[1]if n['template']in(1394,1455,1456,1457)];assert len(actors)==4
  for npc in actors:
   body=death(npc,uid,True);await p.send(0xad,body);assert(await p.until(0xae)).payload==bytes(4)
   assert(await p.until(0xaf)).payload==empty_reward_death_notice(npc['key'],2**64-1).payload
   await p.query(0x48d,reply=0x48f);mark=sum(e.kind==0xaf for e in p.received)
   await p.send(0xad,body);assert(await p.until(0xae)).payload==bytes(4)
   await p.query(0x48d,reply=0x48f);assert sum(e.kind==0xaf for e in p.received)==mark
  assert snapshot()==before
  report.update(ok=True,actual_Application=True,actual_authenticated_TLS=True,ordinary_33242_admission=True,
      ordinary_first_part_combat_and_transition=True,first_part_hostiles=len(first),original_spawn_positions=4,
      spawned=len(spawned),controllers_retired=4,controller_templates=sorted(n['template']for n in actors),
      first_AE_empty_AF=True,retry_AE_only=True,affected_actions_economy_unchanged=True,connection_kept=True,
      forced_server_scene=False,natural_GUI=False,natural_battle=False,experimental_send_hook_loaded=False)
 finally:
  for peer in reversed(peers):await peer.close()
