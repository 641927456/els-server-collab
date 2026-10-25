"""Native9B3 transaction adapter and readonly original21B synchronization."""
from contextlib import closing
import sqlite3
from els_server.domain.manufacture_flow import _actor,_binding,_same_binding,_saved_paths
from els_server.domain.equipment_chip_flow import current_lease
from els_server.protocol.protocol_codec import encode_event
from els_server.protocol.anvil_messages import acknowledgement,notification
def handle(session,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x9b3:return None
 try:
  def context():
   return bool(_actor(session)and type(sequence)is int and 1<=sequence<2**32
    and event.performers in((),(0,))and event.uid==event.target_uid==2**64-1 and event.payload_mode==0)
  if not context():raise ValueError('Anvil session envelope')
  binding=_binding(session)
  def authorize():return bool(context()and _same_binding(session,binding))
  def prepare_replay(events):return [*events,session.saved_user_sync()]
  from els_server.storage.anvil import use
  return use(binding[6],binding[4],binding[5],event.payload,f'{binding[7]}:{binding[4]}:anvil:{sequence}',authorize=authorize,prepare_replay=prepare_replay)
 except(ValueError,sqlite3.Error):
  # Failed9B4 does not run the native success-state copy/ED/XP path.
  return [acknowledgement(result=-1)]
def synchronize(session,reply):
 if any(event.kind==0x9b2 for event in reply):return reply
 triggers=any(event.kind in(0x2a,0x600,0x4c4)or(event.kind==0x4c3 and event.payload[:4]==bytes(4))for event in reply)
 if not triggers:return reply
 try:
  account=getattr(session,'account',None);app=getattr(session,'application',None)
  if not(account is not None and session.item_test and session.client_build=='dx11_260923'
   and session.role=='game'and account.store is not None and account.characters is not None
   and account.store.uid==account.uid and _saved_paths(account)and current_lease(session)
   and(app is None or app.registry.enabled(account.account_id))):return reply
  binding=_binding(session)
  from els_server.storage.profession_state import snapshot as profession_snapshot
  from els_server.storage.anvil import snapshot
  with closing(sqlite3.connect(binding[6].as_uri()+'?mode=ro',uri=True))as db:
   db.execute('BEGIN');db.execute('PRAGMA query_only=ON')
   profession=profession_snapshot(db,binding[4],binding[5])
   if profession['state']['profession']!=2:return reply
   state=snapshot(db,binding[4],binding[5]);message=notification(state['hammers'],state['ready_at']);encode_event(message)
  if not _same_binding(session,binding)or not current_lease(session):return reply
  return [*reply,message]
 except(ValueError,sqlite3.Error):return reply
