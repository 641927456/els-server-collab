"""Native up/down requests and exhaustion notices; no invented attack packets."""
import sqlite3,uuid
from els_server.protocol import mount_messages as wire
from els_server.storage import mount_state as state

def admitted(session):
 return session.item_test and session.client_build=='dx11_260923' and session.role=='game' and session.phase in ('town_ready','dungeon_active')

def handle(session,event,sequence):
 if event.event_id!=0x202 or session.client_build!='dx11_260923' or not session.item_test:return None
 if event.kind==0x542:return _recall(session,event)
 if event.kind not in (0x42c,0x42f):return None
 def failure(reason):
  session._mount_rejection=reason
  return wire.summoned(-1) if event.kind==0x42c else wire.dismounted(-1,0)
 if not admitted(session):return [failure('phase=%s'%session.phase)]
 operation=session.shop_session_id+':mount:'+str(sequence if sequence is not None else uuid.uuid4())
 try:answer=state.handle(session.account.store.path,session.account.uid,event.kind,event.payload,operation)
 except (ValueError,UnicodeError) as error:return [failure(str(error) or 'rejected')]
 session._mount_rejection=None
 session.mount_touched=True;session.mount_owner=session.account.uid
 return [answer]

def _recall(session,event):
 """Consume the native scene-change release (542) and mirror it in storage."""
 if not admitted(session):return []
 try:mount=state.recall(session.account.store.path,session.account.uid)
 except (ValueError,UnicodeError,sqlite3.Error):return []
 if mount is not None:
  session._mount_rejection=None
  session.mount_touched=True;session.mount_owner=session.account.uid
 return []

def periodic(session):
 if not getattr(session,'mount_touched',False) or not admitted(session):return []
 if session.account.uid!=session.mount_owner:
  close(session);return []
 return state.tick(session.account.store.path,session.mount_owner)

def close(session):
 if getattr(session,'mount_touched',False):
  state.tick(session.account.store.path,session.mount_owner,disconnect=True)
  session.mount_touched=False

def observe(session):
 if session.phase in ('closing','channels_ready') or (getattr(session,'mount_touched',False) and session.account.uid!=session.mount_owner):close(session)
 return []
