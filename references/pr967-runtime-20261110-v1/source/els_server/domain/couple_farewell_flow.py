"""Native41A/41C free couple1 farewell, real quote and recipient generation.
Quote is an in-memory capability, not a fee clock or durable mutation. Closure
receipts live separately in SQL; no notification is fabricated to refresh900.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
from els_server.protocol import relationship_messages as wire
from els_server.storage import couple_closures as storage
from els_server.domain.party_commands import _prepared_boxes

def _peer_capture(s,expected):
 app=getattr(s,'application',None)
 if app is None:
  from els_server.domain.housing_room_flow import local_application
  witness=local_application(s)
  def same():return local_application(s)is witness
  return None,same
 account_id=expected['peer_account'];peer=app.playing.get(account_id)
 if peer is None:
  def same():return app.playing.get(account_id)is None
  return None,same
 from els_server.domain.equipment_chip_flow import current_lease
 if not current_lease(peer)or peer.application is not app or Path(peer.account.store.path).resolve()!=Path(s.account.store.path).resolve():raise ValueError('Farewell peer current actual lease')
 def facts():
  box=peer.mailbox
  return(peer.account,peer.account.root,peer.identity,box),(peer.account.uid,peer.account.account_id,peer.shop_session_id,peer.phase,peer.enter_town,peer.released,tuple(box.messages),tuple(box.moves.items()),box.bytes)
 refs,values=facts()
 def same():
  r,v=facts()
  return app.playing.get(account_id)is peer and current_lease(peer)and app.registry.enabled(account_id)and all(a is b for a,b in zip(r,refs))and v==values
 # No UID exists in41E: character-selection/frontend/closing instances cannot
 # consume it. Their durable cold reader observes the closed pair instead.
 notify=(peer.account.uid==expected['peer_uid']and peer.phase not in('new','authenticated','channels_ready','session_ready','closing'))
 return peer if notify else None,same

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in(0x41a,0x41c):return None
 try:
  from els_server.domain.relationship_flow import capture
  same,sender_guard=capture(s)
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Farewell native envelope')
  wire.farewell_request(event.payload)
  owner,account=s.account.uid,s.account.account_id
  if event.kind==0x41a:
   with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True,timeout=5))as db:
    db.execute('BEGIN');sender_guard(db);state=storage.quote(db,owner,account);answer=[wire.farewell_quote(state)]
    from els_server.protocol.protocol_codec import encode_event
    for reply in answer:encode_event(reply)
    sender_guard(db)
   s.couple_close_quote=(s.shop_session_id,owner,account,tuple(sorted(state.items())))
   return answer
  quote=getattr(s,'couple_close_quote',None);expected=None
  if type(quote)is tuple and len(quote)==4 and quote[:3]==(s.shop_session_id,owner,account):expected=dict(quote[3])
  peer,peer_same=(None,lambda:True)if expected is None else _peer_capture(s,expected)
  def guard(db):
   sender_guard(db)
   if expected is not None and(getattr(s,'couple_close_quote',None)is not quote or not peer_same()):raise ValueError('Farewell quoted actor or peer instance changed')
  boxes={}
  def encode(repeat):
   nonlocal boxes
   answer=[wire.farewell_ack()]
   if not repeat and getattr(s,'application',None)is None:answer.append(wire.farewell_notice())
   deliveries=[]if repeat or getattr(s,'application',None)is None else[(s,[wire.farewell_notice()])]+([]if peer is None else[(peer,[wire.farewell_notice()])])
   boxes=_prepared_boxes(deliveries,answer)
   return answer
  operation=s.shop_session_id+':couple-farewell:'+str(owner)+':'+str(sequence)
  with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
   answer=storage.perform(db,owner,account,event.payload,operation,expected,guard=guard,encode=encode);guard(db)
  # Original business worker, no await between COMMIT and bounded publication.
  for recipient,box in boxes.items():recipient.mailbox=box
  s.couple_close_quote=None
  return answer
 except(ValueError,sqlite3.Error,OverflowError,AttributeError,KeyError,TypeError):
  if 'same'not in locals()or not same():return[]
  return[wire.farewell_quote(result=0xb28)]if event.kind==0x41a else[wire.farewell_ack(result=0xb28)]
