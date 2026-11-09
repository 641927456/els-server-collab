"""Original403 pair visuals for actual ready-scene observers; no skill grant.

Readonly snapshot plus original serial worker; no external writer commit fence.
Every request rechecks the current pair and scene. Native receiver ignores the
two actual participants, whose own3FF already initializes their local effects.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
from els_server.protocol import relationship_messages as wire
from els_server.storage import relationships as storage
from els_server.domain.party_commands import _prepared_boxes

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x403:return None
 try:
  from els_server.domain.relationship_flow import capture
  same,guard=capture(s);app=getattr(s,'application',None)
  if app is None:raise ValueError('Couple visual needs actual online observers')
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
     or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Couple visual original envelope')
  owner,peer,kind=wire.visual_request(event.payload)
  if owner!=s.account.uid:raise ValueError('Couple visual current owned UID')
  world=app.world;context=getattr(s,'guild_agit',None)
  if context is not None:
   from els_server.domain.guild_agit_flow import _peers
   candidates=_peers(s,context['guild'])
   def room_same():return getattr(s,'guild_agit',None)is context and context['guild']==s.guild_agit['guild']
  else:
   key=world.members.get(s);room=world.towns.get(key)
   if key!=(1,s.active_map)or not isinstance(room,dict)or s not in room:raise ValueError('Couple visual actual town room')
   people=tuple(room)
   def room_same():return app.world is world and world.members.get(s)==key and world.towns.get(key)is room and tuple(room)==people
   candidates=[]
   for p in people:
    if p is s:continue
    if world.members.get(p)!=key:raise ValueError('Couple visual stale room member')
    ps,pg=capture(p);candidates.append((p,ps,pg))
  candidates=[(p,ps,pg)for p,ps,pg in candidates if p.account.uid not in(owner,peer)]
  for p,ps,pg in candidates:
   if Path(p.account.store.path).resolve()!=Path(s.account.store.path).resolve():raise ValueError('Couple visual shared DB')
  with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True,timeout=5))as db:
   db.execute('BEGIN');guard(db)
   saved=storage.snapshot(db,owner,s.account.account_id)
   if saved is None or(saved['kind'],saved['peer_uid'])!=(1,peer):raise ValueError('Couple visual exact current pair')
   if not room_same():raise ValueError('Couple visual scene changed')
   for p,ps,pg in candidates:pg(db)
   notice=wire.visual(owner,peer,kind);boxes=_prepared_boxes([(p,[notice])for p,ps,pg in candidates],[])
   guard(db)
   if not room_same()or storage.snapshot(db,owner,s.account.account_id)!=saved:raise ValueError('Couple visual late source changed')
   for p,ps,pg in candidates:pg(db)
  # Same original worker, no await boundary between final guards and publish.
  for p,box in boxes.items():p.mailbox=box
  return[]
 except(ValueError,sqlite3.Error,OverflowError,AttributeError,KeyError,TypeError):return[]
