"""Original3FB/3FE mutual current-session couple transaction; no UI injection."""
from contextlib import closing
from pathlib import Path
import sqlite3
from els_server.protocol import relationship_messages as wire
from els_server.storage import relationships as storage
from els_server.domain.party_commands import _prepared_boxes

def capture(s):
 app=getattr(s,'application',None)
 if app is not None and app.playing.get(s.account.account_id)is not s:raise ValueError('Couple current online account lease')
 if getattr(s,'guild_agit',None)is not None:
  from els_server.domain.guild_agit_flow import bank_capture
  same,guard=bank_capture(s)
 else:
  from els_server.domain.housing_access_flow import capture as town_capture
  same,guard=town_capture(s)
 def facts():
  box=getattr(s,'mailbox',None)
  return(app,s.account,s.account.root,box,getattr(s,'identity',None),getattr(app,'playing',None)),(s.account.uid,s.account.account_id,s.shop_session_id,tuple(box.messages)if box is not None else(),tuple(box.moves.items())if box is not None else(),box.bytes if box is not None else 0)
 refs,values=facts()
 def current():
  r,v=facts()
  return(same()and(app is None or app.registry.enabled(values[1])and app.playing.get(values[1])is s)
   and all(a is b for a,b in zip(refs,r))and values==v)
 def check(db):
  if not current():raise ValueError('Couple current actor/mailbox changed')
  guard(db)
 return current,check

def handle(s,event,sequence):
 if event.event_id==0x202 and event.kind in(0x41a,0x41c):
  from els_server.domain.couple_farewell_flow import handle as farewell_handle
  return farewell_handle(s,event,sequence)
 if event.event_id==0x202 and event.kind==0x403:
  from els_server.domain.relationship_visual_flow import handle as visual_handle
  return visual_handle(s,event,sequence)
 if event.event_id!=0x202 or event.kind not in(0x3fb,0x3fe):return None
 try:
  same,guard=capture(s)
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
     or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Couple native envelope')
  if getattr(s,'application',None)is None:raise ValueError('Standalone LOCAL has no second authenticated account peer')
  parsed=wire.propose_request(event.payload)if event.kind==0x3fb else wire.answer_request(event.payload)
  matches=[]
  for p in tuple(s.application.playing.values()):
   if p is s:continue
   if event.kind==0x3fb:
    if p.account.character_identity()['name']!=parsed:continue
   elif p.account.uid!=parsed['proposer']:continue
   ps,pg=capture(p)
   if Path(p.account.store.path).resolve()!=Path(s.account.store.path).resolve():raise ValueError('Couple peers must share actual server character DB')
   matches.append((p,ps,pg))
  if len(matches)!=1:raise ValueError('Couple exact online peer missing')
  peer,peer_same,peer_guard=matches[0];boxes={}
  def both(db):guard(db);peer_guard(db)
  # Parse pinned definitions before taking the financial writer.
  from els_server.game_data import client_data
  if(client_data().item(269710)['item_type'],client_data().item(269710)['metadata'])!=(7,0):raise ValueError('Couple pinned ring category changed')
  operation=s.shop_session_id+':couple:'+str(s.account.uid)+':'+str(sequence)
  with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');both(db)
   if event.kind==0x3fb:
    def encode(a,b,repeat,changes):
     nonlocal boxes
     answer=[wire.proposed(b['name'])];boxes=_prepared_boxes([(peer,[wire.invitation(a['name'],a['uid'],b['name'])])],answer);return answer
    answer=storage.propose(db,s.account.uid,s.account.account_id,peer.account.uid,peer.account.account_id,s.shop_session_id,peer.shop_session_id,event.payload,operation,guard=both,encode=encode)
   else:
    def encode(a,b,repeat,changes):
     nonlocal boxes
     saved=storage.snapshot(db,s.account.uid,s.account.account_id)if parsed['answer']==0 else None
     stamp=0 if saved is None else saved['created_at']
     answer=[wire.answered(a,stamp,answer=parsed['answer'],target_name=b['name'])]
     boxes=_prepared_boxes([]if repeat else[(peer,[wire.answered(b,stamp,changes,answer=parsed['answer'],target_name=b['name'])])],answer);return answer
    answer=storage.answer(db,s.account.uid,s.account.account_id,peer.account.uid,peer.account.account_id,s.shop_session_id,peer.shop_session_id,event.payload,operation,guard=both,encode=encode)
   both(db)
  # All reply bytes, mailbox admission and both guards precede COMMIT. The
  # actual business worker performs these assignments with no await boundary.
  for p,box in boxes.items():p.mailbox=box
  return answer
 except(ValueError,sqlite3.Error,OverflowError,AttributeError,KeyError,TypeError):
  if 'same'not in locals()or not same():return []
  return[wire.proposed('',result=0xb28)]if event.kind==0x3fb else[wire.answered(dict(uid=0,name=''),answer=4,result=0xb28)]
