"""Native finite GuildAgit admission; ordinary saved login town stays durable.

Every stage rereads actual guild membership and binds the current selected
actor/application graph. No administrative joins or client success injection.
"""
from contextlib import closing
from pathlib import Path
import math,sqlite3,struct
from els_server.domain.housing_room_flow import identity,world_state,scene
from els_server.protocol import guild_agit_messages as wire
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.guild_membership_state import snapshot as membership

def _capture(s,*,bank=False):
 refs,values=identity(s);wr,wv=world_state(s);context=getattr(s,'guild_agit',None)
 if(context is None or len(context['refs'])!=len(refs)or any(a is not b for a,b in zip(context['refs'],refs))or context['values']!=values
    or s.phase not in('guild_agit_admitted','guild_agit_loaded','guild_agit_ready','guild_agit_returning')
    or s.active_map!=25000 or s.pending_map!=25000):raise ValueError('GuildAgit current native admission')
 if bank and s.phase!='guild_agit_ready':raise ValueError('GuildAgit warehouse before native505')
 if getattr(s,'application',None)is None:
  from els_server.domain.housing_room_flow import local_application
  app=local_application(s);world=app.world
  if world.dungeons.room(s)is not None or s in world.members or any(s in room for room in world.towns.values()):raise ValueError('GuildAgit standalone cannot borrow friends world')
 else:scene(s,context['source'],context)
 phase=s.phase
 def same():
  try:r,v=identity(s);r2,v2=world_state(s)
  except(ValueError,AttributeError,KeyError,TypeError):return False
  return(v==values and len(r)==len(refs)and all(a is b for a,b in zip(r,refs))
   and v2==wv and all(a is b for a,b in zip(r2,wr))and getattr(s,'guild_agit',None)is context
   and(s.phase,s.active_map,s.pending_map)==(phase,25000,25000))
 def guard(db):
  if not same():raise ValueError('GuildAgit actor generation changed')
  if db.execute('SELECT town FROM location WHERE uid=?',(values[0],)).fetchone()!=(context['source'],):raise ValueError('GuildAgit source town changed')
  from els_server.storage.item_actor import require_active_character
  require_active_character(db,values[0]);saved=membership(db,values[0],values[1])
  if saved is None or saved['id']!=context['guild']:raise ValueError('GuildAgit membership changed')
 return same,guard

def bank_capture(s):return _capture(s,bank=True)

def _peers(s,guild):
 app=getattr(s,'application',None)
 if app is None:return []
 result=[]
 for p in tuple(app.playing.values()):
  if p is s or p.phase!='guild_agit_ready':continue
  context=getattr(p,'guild_agit',None)
  if context is None or context['guild']!=guild:continue
  if Path(p.account.store.path).resolve()!=Path(s.account.store.path).resolve():raise ValueError('GuildAgit different databases')
  same,guard=_capture(p,bank=True)
  result.append((p,same,guard))
 return result

def _row(s,location=None):
 return s.account.character(),location or s.guild_agit['location'],s.account.get_inventory_snapshot()['items']

def disconnect(s):
 # Normal Application and FriendsWorld teardown; idempotent, no SQL writes.
 context=getattr(s,'guild_agit',None)
 if context is None:return
 # Revoke the departing actor's context even if encoding/a peer fails.
 s.guild_agit=None
 app=getattr(s,'application',None)
 if app is not None and s.phase=='guild_agit_ready':
  from els_server.cleanup import cleanup_all
  notice=wire.removed(context['values'][0]);encode_event(notice)
  peers=[p for p in tuple(app.playing.values()) if p is not s and p.phase=='guild_agit_ready'
      and getattr(p,'guild_agit',None) is not None and p.guild_agit['guild']==context['guild']]
  cleanup_all(*(lambda p=p:app.world.send(p,notice) for p in peers))

def handle(s,event,sequence):
 context=getattr(s,'guild_agit',None)
 if event.event_id!=0x202 or(event.kind not in(0x4fb,0x504,0x4fe)and not(context is not None and event.kind in(0x225,0x227,0x490,0x233))):return None
 try:
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
     or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('GuildAgit native envelope')
  if context is None:
   if event.kind!=0x4fb:raise ValueError('GuildAgit entry required')
   position=wire.entry_request(event.payload)
   from els_server.domain.housing_access_flow import capture
   same,guard=capture(s);refs,values=identity(s);source=s.account.get_location()['map'];scene(s,source,None)
   if getattr(s,'town_warp_transition',None)is not None or getattr(s,'housing_own_room',None)is not None:raise ValueError('GuildAgit competing transition')
   # Admission is linearized by the actual single business worker and this
   # read snapshot; it is not an external-writer commit fence. Every next
   # stage rechecks membership. Bank economic writers use their own immediate
   # transactions and fresh membership guard, never this read snapshot.
   with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
    db.execute('BEGIN');guard(db);saved=membership(db,s.account.uid,s.account.account_id)
    if saved is None:raise ValueError('GuildAgit actual membership required')
    answer=[wire.entered(position)]
    for e in answer:encode_event(e)
    guard(db)
    s.guild_agit=dict(refs=refs,values=values,source=source,guild=saved['id'],operation=(sequence,event.payload),location=dict(map=25000,board=0,progress=0,xyz=list(position)))
    s.phase='guild_agit_admitted';s.active_map=25000;s.pending_map=25000
    return answer
  same,guard=_capture(s);phase=s.phase
  with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
   db.execute('BEGIN');guard(db)
   if event.kind in(0x490,0x233):
    if event.payload:raise ValueError('GuildAgit native selection/exit payload')
    peers=_peers(s,context['guild']);answer=[]
    from els_server.domain.party_commands import _prepared_boxes
    boxes=_prepared_boxes([(p,[wire.removed(s.account.uid)])for p,_,_ in peers]if phase=='guild_agit_ready'else[],answer)
    for p,ps,pg in peers:pg(db)
    guard(db)
    for p,box in boxes.items():p.mailbox=box
    s.guild_agit=None;s.active_map=context['source'];s.pending_map=context['source']
    # Delegate the existing 490 channel response/lease transition, or the
    # original233 exit path already allowed while map_loading. No role is
    # selected and no client state is fabricated by this finite cleanup.
    s.phase='town_ready'if event.kind==0x490 else'map_loading'
    return None
   if event.kind==0x4fb:
    if phase!='guild_agit_admitted'or context['operation']!=(sequence,event.payload):raise ValueError('GuildAgit duplicate changed request')
    answer=[wire.entered(context['location']['xyz'])]
   elif event.kind==0x225:
    if event.payload==struct.pack('>iB',context['source'],0)and phase in('guild_agit_ready','guild_agit_returning'):
     peers=_peers(s,context['guild']);answer=[]
     from els_server.domain.party_commands import _prepared_boxes
     boxes=_prepared_boxes([(p,[wire.removed(s.account.uid)])for p,_,_ in peers]if phase=='guild_agit_ready'else[],answer)
     for p,ps,pg in peers:pg(db)
     guard(db)
     for p,box in boxes.items():p.mailbox=box
     s.guild_agit=None;s.phase='town_ready';s.active_map=context['source'];s.pending_map=context['source']
     return None
    if event.payload not in(struct.pack('>iB',25000,0),struct.pack('>iB',25000,1))or phase not in('guild_agit_admitted','guild_agit_loaded'):raise ValueError('GuildAgit original225 admission')
    answer=[wire.loaded()]
   elif event.kind==0x504:
    if phase not in('guild_agit_loaded','guild_agit_ready'):raise ValueError('GuildAgit ready before original226')
    from els_server.storage.local_state import scene_ready_location
    board,progress,xyz=scene_ready_location(event.payload)
    if not 0<=board<255 or not 0<=progress<=100 or any(not math.isfinite(v)or abs(v)>1000000 for v in xyz):raise ValueError('GuildAgit original504 position')
    if phase=='guild_agit_ready'and context['readiness']!=(sequence,event.payload):raise ValueError('GuildAgit already ready generation')
    location=dict(map=25000,board=board,progress=progress,xyz=list(xyz));peers=_peers(s,context['guild'])
    answer=[wire.ready([_row(p)for p,_,_ in peers])]
    from els_server.domain.party_commands import _prepared_boxes
    boxes=_prepared_boxes([(p,[wire.added(_row(s,location))])for p,_,_ in peers]if phase!='guild_agit_ready'else[],answer)
    for p,ps,pg in peers:pg(db)
    guard(db)
    for p,box in boxes.items():p.mailbox=box
    context['location']=location;context['readiness']=(sequence,event.payload);s.phase='guild_agit_ready'
    return answer
   elif event.kind==0x4fe:
    if event.payload or phase not in('guild_agit_ready','guild_agit_returning'):raise ValueError('GuildAgit original leave')
    peers=_peers(s,context['guild']);answer=[Event(0x201,kind=0x4ff,payload=bytes(4))]
    from els_server.domain.party_commands import _prepared_boxes
    boxes=_prepared_boxes([(p,[wire.removed(s.account.uid)])for p,_,_ in peers]if phase=='guild_agit_ready'else[],answer)
    for p,ps,pg in peers:pg(db)
    guard(db)
    for p,box in boxes.items():p.mailbox=box
    s.phase='guild_agit_returning';return answer
   else:raise ValueError('GuildAgit uses504, ordinary227 cannot ready it')
   for e in answer:encode_event(e)
   guard(db)
   if event.kind==0x225:s.phase='guild_agit_loaded'
   return answer
 except(ValueError,sqlite3.Error,OverflowError,KeyError,AttributeError,TypeError):
  if 'same'in locals()and not same():return []
  if event.kind in(0x490,0x233):return []
  # Rejections never mutate source town, membership, inventory or admission.
  answer=[wire.entered((0.,0.,0.),result=0xb28)]if event.kind==0x4fb else[wire.ready(result=0xb28)]if event.kind==0x504 else[wire.loaded(result=0xb28)]if event.kind==0x225 else[Event(0x201,kind=0x4ff if event.kind==0x4fe else 0x228,payload=struct.pack('>i',0xb28))]
  for e in answer:encode_event(e)
  return answer
