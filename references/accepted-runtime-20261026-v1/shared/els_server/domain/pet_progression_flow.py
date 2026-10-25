"""Native feed requests and absolute growth sync after clear receipts."""
import sqlite3,uuid
from contextlib import closing
from els_server.protocol import pet_progression_messages as wire
from els_server.storage import pet_progression as state

def handle(session,request,sequence):
    if request.event_id!=0x202 or request.kind!=0x2f5 or session.client_build!='dx11_260923' or not session.item_test:return None
    def failure():return [wire.feed(result=-1)]
    if session.role!='game' or session.phase not in ('town_ready','dungeon_active'):return failure()
    operation=session.shop_session_id+':pet-growth:'+str(sequence if sequence is not None else uuid.uuid4())
    try:return state.handle(session.account.store.path,session.account.uid,request.kind,request.payload,operation)
    except (ValueError,UnicodeError):return failure()

def observe(session,reply):
    if session.client_build!='dx11_260923' or not session.item_test or not getattr(session,'reward_receipt',None) or not any(e.kind==0xc1 for e in reply):return []
    with closing(sqlite3.connect(session.account.store.path)) as db:
        try:pet=state.active(db,session.account.uid)
        except ValueError:return []
    return [wire.progress(session.account.uid,pet)]
