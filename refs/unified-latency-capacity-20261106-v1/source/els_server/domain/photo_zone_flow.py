"""Finite original studio rooms and current-owned camera admission, the existing world lock.

Rooms are transient. Unlock tickets use the shared atomic inventory receipt;
map ownership survives reconnection. Acquisition remains in existing systems.
"""
from contextlib import closing,ExitStack
from pathlib import Path
import sqlite3,struct,time,uuid
from els_server.domain.housing_room_flow import identity,world_state,scene
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import photo_zone_messages as wire
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.photo_zone_catalog import catalog
from els_server.storage import photo_zone_state as storage
# The original studio admits eight members. Each keeps its peer port while
# others leave or join; Team row order never changes a survivor's endpoint.
MAX_MEMBERS=8

def app_of(s):return s.application
def rooms_of(s):
 app=app_of(s)
 if not hasattr(app,'photo_zones'):app.photo_zones={};app.photo_zone_next=700001
 return app,app.photo_zones
def _capture(s):
 refs,values=identity(s);wr,wv=world_state(s);context=getattr(s,'photo_zone',None);phase=s.phase;active=s.active_map;pending=s.pending_map
 source=s.account.get_location()['map']
 if context is None:
  from els_server.domain.housing_access_flow import capture
  capture(s)
  if getattr(s,'guild_agit',None)is not None or getattr(s,'housing_own_room',None)is not None or getattr(s,'town_warp_transition',None)is not None:raise ValueError('PhotoZone competing scene')
  scene(s,source,None)
 else:
  if len(refs)!=len(context['refs'])or any(a is not b for a,b in zip(refs,context['refs']))or values!=context['values']or source!=context['source']:raise ValueError('PhotoZone selected actor generation')
  if phase not in('photo_zone_admitted','photo_zone_lobby'):raise ValueError('PhotoZone current native phase')
  room=context['room'];expected=source if room is None else room['value']['world']
  if active!=pending or active!=expected:raise ValueError('PhotoZone native world identity')
  if room is not None and(s not in room['members']or app_of(s).photo_zones.get(room['id'])is not room):raise ValueError('PhotoZone current membership')
  world=app_of(s).world
  if world.dungeons.room(s)is not None or s in world.members or any(s in row for row in world.towns.values()):raise ValueError('PhotoZone admitted actor must leave ordinary town')
 def same():
  try:r,v=identity(s);r2,v2=world_state(s)
  except(ValueError,AttributeError,KeyError,TypeError):return False
  return(v==values and len(r)==len(refs)and all(a is b for a,b in zip(r,refs))and v2==wv and all(a is b for a,b in zip(r2,wr))and getattr(s,'photo_zone',None)is context and(s.phase,s.active_map,s.pending_map)==(phase,active,pending))
 def guard(db):
  if not same():raise ValueError('PhotoZone late actor/scene change')
  from els_server.storage.item_actor import require_active_character
  require_active_character(db,values[0])
  if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(values[0],)).fetchone()!=(values[1],):raise ValueError('PhotoZone saved ownership')
  if db.execute('SELECT town FROM location WHERE uid=?',(values[0],)).fetchone()!=(source,):raise ValueError('PhotoZone saved source town')
 return refs,values,source,same,guard
def _snapshot(s):
 character=s.account.character();items=s.account.get_inventory_snapshot()['items']
 from els_server.domain.item_expiration import expired
 now=int(time.time());camera=any(i['template']in catalog()['cameras']and i['count']>0 and not expired(i,now=now)for i in items)
 return character,items,camera
def _full(s,index,projection=None):
 from els_server.protocol.dungeon_messages import member
 character,items,camera=_snapshot(s)if projection is None else projection
 return member(s.account.get_skills(),character,items,account_id=s.account.account_id,peer_port=21100+index),camera
def _roster(members,ports,own=None,projection=None):return tuple(_full(s,ports[s],projection if s is own else None)[0]for s in members)

def _rooms_guard(app):
 # Freeze cache identities and values across projection/encoding callbacks.
 # The world lock serializes room changes; this also rejects a
 # callback replacing a room, source roster, counter or a member generation.
 table=app.photo_zones;counter=app.photo_zone_next
 def state():
  return tuple((key,id(room),room['epoch'],tuple(sorted(room['value'].items())),
   tuple(id(p)for p in room['members']),
   tuple(sorted((id(p),raw)for p,raw in room['sources'].items())),
   tuple(sorted((id(p),port)for p,port in room['ports'].items())))
   for key,room in sorted(table.items()))
 before=state()
 def same():
  try:return app.photo_zones is table and app.photo_zone_next==counter and state()==before
  except(KeyError,TypeError,AttributeError):return False
 return same
def _descriptor(room,members=None,*,listing=False,bootstrap_port=0):
 value=dict(room['value'])
 if listing:value['password']=''
 return wire.room(**value,room_id=room['id'],state=3,max_slots=MAX_MEMBERS,join_slots=len(room['members']if members is None else members),bootstrap_port=bootstrap_port)
def _peer_guards(members,db):
 for p in members:_capture(p)[4](db)
def _own_room(s):
 ctx=getattr(s,'photo_zone',None)
 return None if ctx is None else ctx['room']
def disconnect(s):
 context=getattr(s,'photo_zone',None)
 if context is None:return
 room=context['room'];s.photo_zone=None
 if room is None:return
 if s in room['members']:room['members'].remove(s)
 app=app_of(s)
 room['sources'].pop(s,None);room['ports'].pop(s,None)
 if not room['members']:app.photo_zones.pop(room['id'],None);return
 # Teardown does not borrow a stale departing actor as a producer. Remaining
 # rows are the accepted immutable admission sources; normal requests reread.
 roster=tuple(room['sources'][p]for p in room['members'])
 notice=wire.left(3,context['values'][0],_teams(room['members'],room['ports'],roster));encode_event(notice)
 from els_server.cleanup import cleanup_all
 cleanup_all(*(lambda p=p:app.world.send(p,notice)for p in tuple(room['members'])))

def _teams(members,ports,roster):
 return wire.teams([(ports[p],raw,index==0)for index,(p,raw)in enumerate(zip(members,roster))])

def _prepare(deliveries,response,locks):
 for p in sorted({p for p,_ in deliveries},key=lambda p:p.account.uid):
  locks.enter_context(p.mailbox.lock)
 return _prepared_boxes(deliveries,response)

def chat(s,text,now):
 from els_server.protocol import social_messages as social
 try:
  _,_,_,same,guard=_capture(s);room=_own_room(s)
  if room is None:raise ValueError('PhotoZone chat requires room membership')
  cache_same=_rooms_guard(app_of(s));members=tuple(room['members'])
  with ExitStack()as locks,closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
   db.execute('BEGIN');guard(db);_peer_guards(members,db)
   response=[social.chat_ack()]
   notice=social.chat_notice(s.account.character(),s.identity['id'],text,0)
   boxes=_prepare([(p,[notice])for p in members],response,locks)
   guard(db);_peer_guards(members,db)
   if not cache_same():raise ValueError('PhotoZone chat room changed while encoding')
   s.chat_times.append(now)
   for p,box in boxes.items():p.mailbox=box
   return response
 except(ValueError,sqlite3.Error,KeyError,TypeError,AttributeError,OverflowError,UnicodeError):
  return []if 'same'in locals()and not same()else[social.chat_ack(-1)]

def manifest(app,account_id):
 s=app.playing.get(account_id)
 room=None if s is None else _own_room(s)
 if room is None:return None
 try:
  for p in room['members']:_capture(p)
 except(ValueError,AttributeError,KeyError,TypeError):return None
 return dict(epoch=room['epoch'],uid=s.account.uid,peers=[dict(uid=p.account.uid,port=21100+room['ports'][p])for p in room['members']])

def relay_target(app,account_id,epoch,target):
 value=manifest(app,account_id)
 if value is None or value['epoch']!=epoch:return None
 s=app.playing[account_id];room=_own_room(s)
 p=next((p for p in room['members']if p is not s and p.account.uid==target),None)
 return None if p is None else(p.account.account_id,s.account.uid)

def handle(s,event,sequence):
 context=getattr(s,'photo_zone',None)
 kinds=(0x5ac,0x5a2,0x5a4,0x5b4,0x5b8,0xe44)
 if event.event_id!=0x202 or(event.kind not in kinds and not(context is not None and event.kind in(0x67,0x225,0x490,0x233))):return None
 if event.kind==0xe44 and(len(event.payload)<4 or event.payload[-4:]!=struct.pack('>i',21)):return None
 locks=ExitStack()
 try:
  if event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('PhotoZone native envelope')
  refs,values,source,same,guard=_capture(s);app,rooms=rooms_of(s);room=_own_room(s)
  old_same,old_guard=same,guard;cache_same=_rooms_guard(app)
  same=lambda:old_same()and cache_same()
  def guard(db):
   old_guard(db)
   if not cache_same():raise ValueError('PhotoZone late room cache generation')
  if event.kind==0x5b8:
   if room is not None:raise ValueError('Studio map unlock requires lobby')
   operation=values[2]+':photo-zone:'+str(values[0])+':'+str(sequence)
   return storage.use(s.account.store.path,values[0],values[1],event.payload,operation,guard)
  # Materialize expensive projections before the short readonly snapshot.
  own_projection=_snapshot(s);own_full,camera=_full(s,0,own_projection)
  with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
   db.execute('BEGIN');guard(db)
   if event.kind==0xe44:
    if room is not None:raise ValueError('PhotoZone creation name check requires lobby')
    correlation,name=wire.name_request(event.payload)
    answer=[wire.name_checked(correlation,name)]
   elif event.kind==0x5ac:
    if room is not None or len(event.payload)!=6:raise ValueError('PhotoZone native lobby list')
    page,world=struct.unpack('>iH',event.payload)
    if page<1 or world!=65535 and str(world)not in catalog()['maps']:raise ValueError('PhotoZone list page/world')
    current=[r for r in rooms.values()if world==65535 or r['value']['world']==world]
    pages=max(1,(len(current)+9)//10)
    answer=[wire.unlocked(storage.snapshot(db,values[0],values[1])),wire.listed([_descriptor(r,listing=True)for r in current[(page-1)*10:page*10]],pages,total=len(current))]
   elif event.kind in(0x5a2,0x5a4):
    if room is not None:raise ValueError('PhotoZone already admitted')
    if event.kind==0x5a2:
     value=wire.creation(event.payload)
     if value['world']not in storage.snapshot(db,values[0],values[1]):raise ValueError('Studio background is not unlocked for this character')
     selected=dict(id=app.photo_zone_next,epoch=str(uuid.uuid4()),value=value,members=[],sources={},ports={});members=[s];ports={s:0}
    else:
     key,password=wire.joining(event.payload);selected=rooms.get(key)
     if selected is None or selected['value']['password']!=password and not selected['value']['public']or len(selected['members'])>=MAX_MEMBERS:raise ValueError('PhotoZone room/password/transport capacity')
     members=[*selected['members'],s];_peer_guards(selected['members'],db)
     ports={**selected['ports'],s:next(i for i in range(MAX_MEMBERS)if i not in selected['ports'].values())}
    roster=_roster(members,ports,s,own_projection);descriptor=_descriptor(selected,members,bootstrap_port=s.port_probe_port)
    answer=[wire.created(descriptor,_teams(members,ports,roster),camera)]if event.kind==0x5a2 else[wire.joined(descriptor,roster[-1],_teams(members,ports,roster),camera)]
    added=Event(0x201,kind=0x5a6,payload=wire.team(ports[s],roster[-1],False))
    boxes=_prepare([(p,[added])for p in selected['members']],answer,locks)
    _peer_guards(selected['members'],db);guard(db)
    for p,box in boxes.items():p.mailbox=box
    selected['members']=members;selected['sources']=dict(zip(members,roster));selected['ports']=ports;rooms[selected['id']]=selected
    if event.kind==0x5a2:app.photo_zone_next+=1
    s.photo_zone=dict(refs=refs,values=values,source=source,room=selected)
    s.phase='photo_zone_admitted';s.active_map=s.pending_map=selected['value']['world'];return answer
   elif event.kind==0x5b4:
    if room is None or room['members'][0]is not s:raise ValueError('PhotoZone settings current room master')
    value=wire.settings(event.payload)
    if value['world']not in storage.snapshot(db,values[0],values[1]):raise ValueError('Studio background is not unlocked for the room master')
    peers=[p for p in room['members']if p is not s];_peer_guards(peers,db)
    answer=[wire.changed(value,stamp=int(time.time()))];boxes=_prepare([(p,[wire.change_notice(value)])for p in peers],answer,locks)
    _peer_guards(peers,db);guard(db)
    for p,box in boxes.items():p.mailbox=box
    room['value']=value
    for p in room['members']:p.active_map=p.pending_map=value['world']
    return answer
   else:
    if event.kind==0x67:
     if room is None or not 100<=len(event.payload)<=8192 or struct.unpack_from('>i',event.payload)[0]<0:raise ValueError('PhotoZone original generic67 exit body')
     # Native Game v270 sends opaque statistics. Studio exit grants no loot,
     # XP, money, item usage, durable location change or attribute update.
     from els_server.protocol.dungeon_messages import end_ack
     answer=[end_ack()]
    elif event.kind==0x225:
     if room is not None or event.payload not in(struct.pack('>iB',source,0),struct.pack('>iB',source,1)):raise ValueError('PhotoZone normal source-town return')
     answer=[]
    else:
     if event.payload:raise ValueError('PhotoZone native selection/exit body')
     answer=[]
    peers=[]if room is None else[p for p in room['members']if p is not s];_peer_guards(peers,db)
    remaining=_roster(peers,room['ports'])if room is not None else();notice=wire.left(3,values[0],_teams(peers,room['ports'],remaining)if room is not None else wire.teams(()))
    boxes=_prepare([(p,[notice])for p in peers],answer,locks);_peer_guards(peers,db);guard(db)
    for p,box in boxes.items():p.mailbox=box
    if room is not None:
     room['members']=peers;room['sources']=dict(zip(peers,remaining));room['ports']={p:room['ports'][p]for p in peers}
     if not peers:rooms.pop(room['id'],None)
    s.active_map=s.pending_map=source
    if event.kind==0x67:s.photo_zone['room']=None;s.phase='photo_zone_lobby';return answer
    s.photo_zone=None;s.phase='town_ready'if event.kind in(0x225,0x490)else'map_loading';return None
   for e in answer:encode_event(e)
   guard(db);return answer
 except(ValueError,sqlite3.Error,KeyError,TypeError,AttributeError,OverflowError,UnicodeError)as error:
  s._photo_zone_rejection=str(error)
  if 'same'in locals()and not same():return []
  if event.kind==0x5b8:return[wire.unlocked_ack(result=0xb28)]
  if event.kind==0xe44:
   correlation=struct.unpack_from('>Q',event.payload)[0]if len(event.payload)>=8 else 0
   return[wire.name_checked(correlation,'',result=0xb28)]
  if event.kind==0x5ac:return[wire.listed([],result=0xb28)]
  if event.kind==0x5b4:return[wire.changed(dict(name='',password='',public=True,world=0),result=0xb28)]
  if event.kind in(0x5a2,0x5a4)and'own_full'in locals():
   empty=wire.room(world=0,name='');teams=wire.teams(())
   return[wire.created(empty,teams,False,result=0xb28)]if event.kind==0x5a2 else[wire.joined(empty,own_full,teams,False,result=0xb28)]
  return []

 finally:
  locks.close()
