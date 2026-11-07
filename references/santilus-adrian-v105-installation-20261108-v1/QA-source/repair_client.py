"""Ordinary admission and source-gated progress to the two affected rooms.

Synthetic owned protocol reports, not natural GUI battle or a server scene edit.
"""
import asyncio,math,struct
from protocol_client import connect
from els_server.domain.dungeon_routes import route_catalog,npc_initialization
from els_server.domain.dungeon_npcs import MODE0_FIELDS
from els_server.domain.formal_npc_hp import f32,initialization_factor
from els_server.domain.scene_retirement_sources import RULES
from els_server.game_data import client_data
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

def stage_actors(event,dungeon):
 stage,reserved,count=struct.unpack_from('>iiI',event.payload);assert reserved==0 and 1<=count<=32
 position=12;parts={};catalog=route_catalog()
 for _ in range(count):
  part,opaque,n=struct.unpack_from('>iII',event.payload,position);position+=12;assert opaque==0 and 0<=n<=128
  actors=[]
  for _ in range(n):
   dto=bytearray(0xa4)
   for offset,size,xor,kind in MODE0_FIELDS:
    raw=event.payload[position:position+size];assert len(raw)==size;position+=size
    if kind=='empty':assert int.from_bytes(raw,'big')==0;continue
    dto[offset:offset+size]=b''.join(raw[i:i+4][::-1]for i in(0,4,8))if size==12 else(int.from_bytes(raw,'big')^xor).to_bytes(size,'little')
   actors.append(dict(key=struct.unpack_from('<i',dto)[0],template=struct.unpack_from('<i',dto,4)[0],
       key_code=struct.unpack_from('<i',dto,0x4f)[0],point=struct.unpack_from('<i',dto,0x15)[0],active=bool(dto[0x4e]),team=0 if dto[0x66]else 1))
  parts[part]=actors
 for actors in parts.values():
  for npc in actors:
   init=npc_initialization(catalog,npc['template'],1.0)
   tag=struct.pack('>i',npc['key'])+init[:-98];offset=event.payload.find(tag)
   assert offset>=0 and event.payload.find(tag,offset+1)<0
   base=struct.unpack_from('>f',event.payload,offset+len(tag)+4)[0]
   npc['hp']=f32(base*initialization_factor(dungeon));assert math.isfinite(npc['hp'])and npc['hp']>0
 return stage,parts

def death(npc,uid,retirement=False,scripted=False):
 if retirement or scripted:
  return(struct.pack('>iBQQ6fBf',npc['key'],255 if retirement else 0,2**64-1,2**64-1,*([0.]*6),1,npc['hp'])
      +bytes(4)+struct.pack('>IQB',1,uid,0)+bytes(20))
 return(struct.pack('>iBQQ6fBf',npc['key'],0,uid,uid,*([0.]*6),0,npc['hp'])
     +struct.pack('>IIQBQIQ',0,1,uid,0,0,0,uid))

async def existing_or_until(peer,kind,mark):
 old=next((e for e in peer.received[mark:]if e.kind==kind),None)
 return old if old is not None else await peer.until(kind)

async def admitted(peer,dungeon):
 await peer.send(0x7d4,struct.pack('>ii',1,dungeon));assert(await peer.until(0x7d5)).payload[:4]==bytes(4)
 await peer.send(0x382,ENTRY);assert(await peer.until(0x383)).payload[:4]==bytes(4);await peer.until(0x14a)
 await peer.send(0x91,struct.pack('>ii',100,0));event=await peer.until(0xb2)
 await peer.send(0xb3,bytes(9));await peer.until(0xbd)
 return stage_actors(event,dungeon)

async def advance(peer,uid,dungeon,stage,part,parts):
 mark=len(peer.received);conditions=route_catalog().graph(dungeon)['stages'][str(stage)]['parts'][str(part)]['conditions']
 required_templates={t for c in conditions if c['kind']==3 for t in c['required']}
 required_keys={t for c in conditions if c['kind']in(1,2)for t in c['required']}
 actors=parts[part]
 targets=[n for n in actors if n['team']!=0 and(n['active']or n['template']in required_templates or n['key_code']in required_keys)]
 # Ordinary combat first; script-owned terminal sources retain their own DTO.
 for npc in sorted(targets,key=lambda n:n['key_code']in required_keys or n['template']in required_templates):
  finite=any((r['dungeon'],r['stage'],r['part'],r['source']['template'])==(dungeon,stage,part,npc['template'])for r in RULES)
  native=client_data().npc(npc['template']);scripted=not npc['active']and native['class_id']==100
  await peer.send(0xad,death(npc,uid,finite,scripted));assert(await peer.until(0xae)).payload==bytes(4)
  await peer.until(0xaf)
 if any(c['kind']==5 for c in conditions):
  payload=struct.pack('>iiHI',stage,part,0,len(conditions))+bytes([1]*len(conditions))+b'\0'
  await peer.send(0x471,payload);assert(await peer.until(0x472)).payload[:4]==bytes(4)
 if any(c['kind']==6 for c in conditions):
  # This source explicitly waits ten seconds; do not use the fixture's 8s
  # reply deadline as a substitute for the original dungeon condition.
  await asyncio.sleep(max(c['seconds']for c in conditions if c['kind']==6))
 target=conditions[0]['next'][0]
 if target['kind']==0:
  opened=await existing_or_until(peer,0xb7,mark);next_part=struct.unpack('>b',opened.payload)[0]
  await peer.send(0xb8,opened.payload);assert(await peer.until(0xb9)).payload==bytes(4)
  await peer.until(0xba);await peer.send(0xbb,opened.payload);assert(await peer.until(0xbc)).payload==bytes(4);await peer.until(0xbd)
  return stage,next_part,parts
 assert target['kind']==1,'This owned route stops before settlement'
 await existing_or_until(peer,0xba,mark);await peer.send(0xbb,struct.pack('>b',part));assert(await peer.until(0xbc)).payload==bytes(4)
 event=await peer.until(0xb2);await peer.send(0xb3,bytes(9));await peer.until(0xbd)
 new_stage,new_parts=stage_actors(event,dungeon);assert new_stage==target['stage']
 return new_stage,0,new_parts

async def retire(peer,npc,uid):
 body=death(npc,uid,True);await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4)
 af=await peer.until(0xaf);assert struct.unpack('>iiBQII?iiI',af.payload)==(npc['key'],0,0,2**64-1,0,0,False,0,0,0)
 await peer.query(0x48d,reply=0x48f);mark=len(peer.received)
 await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4);await peer.query(0x48d,reply=0x48f)
 assert not any(e.kind==0xaf for e in peer.received[mark:])

async def scenario(values,snapshot,report,expire=None,completed_checks=()):
 peers=[];checks=list(completed_checks);report['checks']=checks
 try:
  assert len(values)==2 and all(v['unit_type']==1 for v in values)
  for value,dungeon,stop in zip(values,(33881,33242),((1,1),(3,0))):
   if any(v['dungeon']==dungeon for v in completed_checks):continue
   peer=await connect(value,peers);uid=value['uid'];stage,parts=await admitted(peer,dungeon);part=0;transitions=0
   while(stage,part)!=stop:
    report['current_owned_route']=dict(dungeon=dungeon,stage=stage,part=part)
    stage,part,parts=await advance(peer,uid,dungeon,stage,part,parts);transitions+=1
    assert transitions<12
   before=snapshot();actors=parts[part]
   if dungeon==33242:
    trigger=next(n for n in actors if n['template']==1395)
    targets=[n for n in actors if n['template']not in(1391,1395)]
    mark=len(peer.received);await peer.send(0xad,death(targets[0],uid,True));await peer.query(0x48d,reply=0x48f)
    assert not any(e.kind in(0xae,0xaf)for e in peer.received[mark:])
    await retire(peer,trigger,uid)
   else:targets=[next(n for n in actors if n['template']==2316)]
   for npc in targets:await retire(peer,npc,uid)
   assert snapshot()==before
   checks.append(dict(dungeon=dungeon,stage=stage,part=part,ordinary_transitions=transitions,
       retired=len(targets),first_AE_empty_AF=True,retry_AE_only=True,retirements_economy_unchanged=True))
   await peer.close();peers.remove(peer)
  report.update(ok=True,checks=checks,actual_Application=True,actual_authenticated_TLS=True,ordinary_source_admission_and_transitions=True,
      forced_server_scene=False,natural_GUI=False,natural_battle=False,experimental_send_hook_loaded=False)
 finally:
  for peer in reversed(peers):await peer.close()
