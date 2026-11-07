"""One housing scenario for selected private, public and actual local runtimes."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.protocol import housing_messages as room_wire,housing_preset_messages as preset_wire
from els_server.protocol.housing_layout_messages import REQUEST,encode,decode
from els_server.storage.shop_state import catalog

def _schema(value):
 if isinstance(value,str):return('vec','B')if value=='pet_placements'else value
 if value[0]in('tuple','vec','map'):return(value[0],*(_schema(v)for v in value[1:]))
 return('tuple',*(_schema(v)for key,v in value))

def entry(payload):
 values=decode(_schema(room_wire.ACK),payload);result=dict(zip((key for key,s in room_wire.ACK),values))
 # This reader is used only before placement or after retrieval; it does not
 # assign an invented format to nonempty native pet-placement records.
 assert result['1b4']==[]
 return result

async def scenario(values,snapshot,report):
 assert len(values)==1
 a=values[0];peers=[]
 async def current():return(await asyncio.to_thread(snapshot))[0]
 async def use(peer,uid,target=0):
  answer=await peer.query(0x219,struct.pack('>QQiiIB',uid,target,0,0,0,0));assert answer.payload[:4]==bytes(4)
 async def save(peer,layout,selected):
  answer=await peer.query(0x935,encode(REQUEST,(*layout,selected)));assert answer.payload[:4]==bytes(4)
 async def floor(peer,n):
  body=struct.pack('>fffIBBHBiiBi',0.,0.,0.,0,0,0,0,0,0,0,0,n)
  assert len(body)==34;await peer.send(0x92b,body);await peer.query(0x48d,reply=0x48f)
 async def npc(peer,entries):
  body=struct.pack('>BHI',0,0,len(entries))+b''.join(struct.pack('>ii',*row)for row in entries)+struct.pack('>i',10018)
  answer=await peer.query(0xea,body,0xeb);assert answer.payload[:4]==bytes(4)
 async def enter(peer):
  answer=await peer.query(0x923,struct.pack('>Qi3fB',0,26000,0.,0.,0.,1),0x924)
  value=entry(answer.payload);assert value['000']==0
  ready=await peer.query(0x92e,struct.pack('>fff',0.,0.,0.),0x92f);assert ready.payload[:8]==struct.pack('>iI',0,1)
  return value
 try:
  baseline=await current();assert baseline['balance'][0]==600000000 and baseline['room']is None
  p=await connect(a,peers)
  await p.query(0x80d,struct.pack('>i',1),0x80e)
  offers={r['template']:r for r in catalog()};quantities={136030:1,136031:1,136032:1,136033:1,136241:2,136245:1}
  assert all(offers[t]['price']==50 for t in quantities)
  body=struct.pack('>I',len(quantities))+b''.join(struct.pack('>IH',offers[t]['sku'],n)for t,n in quantities.items())
  assert(await p.query(0x80f,body,0x810)).payload[:4]==bytes(4)
  for q in(99,99,2):await npc(p,[(570014,q)])
  await npc(p,[(570011,1),(570012,1),(570015,1),(570016,1),(570234,1)])
  row=await current();expected_ED=162499650
  assert row['balance'][0]==expected_ED and len([i for i in row['items']if i['group']==25])==205
  report['checks'].append('Seven50ED tickets and205furniture through actual storefront/NPC purchases; native prices and exact ED delta')
  await use(p,a['first_contract_uid']);await enter(p)
  row=await current();tickets={t:[i['uid']for i in row['items']if i['template']==t]for t in quantities}
  for n,t in enumerate((136030,136031,136032,136033),1):await use(p,tickets[t][0],0)
  for n,uid in enumerate(tickets[136241],2):await use(p,uid,n)
  await use(p,tickets[136245][0])
  row=await current();assert row['room']['layout']==[(0,(4,4)),(1,(0,0)),(2,(0,0))]or row['room']['layout']==[[0,[4,4]],[1,[0,0]],[2,[0,0]]]
  assert row['extra_presets']==1
  chairs=sorted((i for i in row['items']if i['template']==570014),key=lambda i:i['uid'])
  legacy=[(i['uid'],(1,i['uid'],570014,n%24,n//24,0))for n,i in enumerate(chairs)]
  layout=(legacy,[],[],0,0);await save(p,layout,4)
  row=await current();assert{375,376,377,378}<={r['id']for r in row['achievement']['completed']}
  # Completed definitions are carried by the completion vector.
  assert len(row['layouts']['0'if '0'in row['layouts']else 0]['layout'][0])==200
  preset=(0,'OwnedHouse',4,[(1,570014,n%24,n//24)for n in range(200)],[])
  assert(await p.query(0xd37,encode(preset_wire.REQUEST,(preset,False)),0xd38)).payload[:4]==bytes(4)
  renamed=(0,'OwnedRenamed',*preset[2:]);assert(await p.query(0xd37,encode(preset_wire.REQUEST,(renamed,True)),0xd38)).payload[:4]==bytes(4)
  await save(p,([],[],[],0,0),4);await save(p,layout,4)
  row=await current();assert{375,376,377,378}<={r['id']for r in row['achievement']['completed']}
  report['checks'].append('Three floors/five stages/two preset slots;200actual purchased furniture;375..378completion;nativeD37save/rename and935clear/restore')
  mat=next(i for i in row['items']if i['template']==570234);await floor(p,1)
  upper=([(mat['uid'],(1,mat['uid'],570234,0,0,1))],[],[],0,1);await save(p,upper,0)
  pet_body=struct.pack('>BQ',1,a['pet_uid']);assert(await p.query(0xa38,pet_body,0xa39)).payload[:4]==bytes(4)
  row=await current();assert len(row['placed_pets'])==1
  assert(await p.query(0x935,encode(REQUEST,([],[],[],0,1,0)),0x936)).payload[:4]==struct.pack('>i',-1)
  assert len((await current())['placed_pets'])==1
  assert(await p.query(0xa3a,pet_body,0xa3b)).payload[:4]==bytes(4)
  assert(await current())['placed_pets']==[]
  await p.close();peers.remove(p);await current();p=await connect(a,peers);cold=await enter(p)
  assert cold['0da']==[(0,(4,4)),(1,(0,0)),(2,(0,0))]and cold['0ea']==1
  assert len(dict(cold['0f7'])[0][0])==200 and len(dict(cold['0f7'])[1][0])==1
  assert dict(cold['1c5'])[0]==renamed
  row=await current();assert row['balance'][0]==expected_ED and row['pets'][0]['growth']==0
  assert row['placed_pets']==[]and{375,376,377,378}<={r['id']for r in row['achievement']['completed']}
  assert not any(i['template']in quantities or i['template']==713275 for i in row['items'])
  report['checks'].append('Upper-floor small mat place/retrieve;busy-mat removal rejected without state loss;no premature growth;cold native924 restores layouts/preset/entitlements and exact economy')
  report.update(ok=True,connected_source_types=49,connected_definitions=322,remaining_source_types=11,unresolved_original_reward_groups=53,
   expected_ED=expected_ED,actual_NPC_furniture=205,house_floors=3,maximum_visible_stage=5,preset_slots=2,new_schema_definitions=4,
   natural_GUI=False,native_Game=False,natural_battle=False,first_contract_level_ED_pet_fixtures=True,normal_furniture_and_expansion_acquisition=True,production_clock_patch=False)
 finally:
  for peer in reversed(peers):await peer.close()
