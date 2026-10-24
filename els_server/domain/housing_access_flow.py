"""Native first-use7day contract plus lifetime cold reader, exact current actor."""
from contextlib import closing
from pathlib import Path
import sqlite3
from els_server.domain.town_travel_flow import _ordinary_actor
from els_server.protocol.career_messages import use_ack,use_request
from els_server.protocol.protocol_codec import Event
from els_server.protocol.housing_access_messages import patch_initialization
from els_server.storage import housing_access as storage

def capture(s):
    def current():
        if(not _ordinary_actor(s)or s.account.characters is None or s.role!='game'
           or s.phase!='town_ready'or not s.enter_town or not s.item_test
           or s.client_build!='dx11_260923'or s.dungeon_return_pending
           or not{0x28,0x225,0x227}.issubset(s.completed)
           or s.pending_map!=s.active_map or s.account.get_location()['map']!=s.active_map):raise ValueError('Housing stable native town required')
        a=s.account
        return(a,a.store,a.characters,getattr(a,'root',None),getattr(s,'application',None)),(a.uid,a.account_id,s.shop_session_id,s.active_map,s.pending_map)
    refs,values=current()
    def same():
        try:r,v=current()
        except(ValueError,AttributeError):return False
        return v==values and all(a is b for a,b in zip(r,refs))
    def guard(db):
        if not same():raise ValueError('Housing actor generation changed')
        if db.execute('SELECT town FROM location WHERE uid=?',(values[0],)).fetchone()!=(values[3],):raise ValueError('Housing saved source scene changed')
    return same,guard

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219:return None
    if not _ordinary_actor(s):return None
    try:source=use_request(event.payload)
    except ValueError:return None
    operation=s.shop_session_id+':housing136034:'+str(s.account.uid)+':'+str(sequence)
    with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
        row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(s.account.uid,source)).fetchone()
        replay=db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()if db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone()else None
    if row!=(storage.TEMPLATE,)and not replay:return None
    try:
        same,guard=capture(s)
        if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
           or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Housing native envelope')
        return storage.use(s.account.store.path,s.account.uid,s.account.account_id,event.payload,operation,guard)
    except(ValueError,sqlite3.Error,OverflowError):
        return[use_ack(result=-1)]if'same'in locals()and same()else[]

def synchronize(s,replies):
    if not any(e.event_id==0x201 and e.kind==0x30 for e in replies):return replies
    if not _ordinary_actor(s):raise ValueError('Housing cold actor unavailable')
    state=storage.read(s.account.store.path,s.account.uid,s.account.account_id)
    if state is None:return replies
    return[Event(e.event_id,kind=e.kind,payload=patch_initialization(e.payload,state['expires_at']))if e.event_id==0x201 and e.kind==0x30 else e for e in replies]
