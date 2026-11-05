"""Native feed requests and absolute growth sync after clear receipts."""
import sqlite3
from pathlib import Path
from els_server.domain.equipment_chip_flow import current_lease
from contextlib import closing
from els_server.protocol import pet_progression_messages as wire
from els_server.storage import pet_progression as state

def handle(session,request,sequence):
    from els_server.domain.pet_nutrition_flow import handle as nutrition
    reply=nutrition(session,request,sequence)
    if reply is not None:return reply
    if request.event_id!=0x202 or request.kind!=0x2f5 or session.client_build!='dx11_260923' or not session.item_test:return None
    def failure():return [wire.feed(result=-1)]
    account=session.account;store=account.store
    owner,account_id=account.uid,account.account_id
    path=Path(store.path).resolve() if store is not None else None
    captured=(session.shop_session_id,session.phase)
    def same():
        return (session.account is account and account.store is store and store is not None
            and account.uid==owner and store.uid==owner and account.account_id==account_id
            and Path(store.path).resolve()==path and current_lease(session)
            and not session.released and session.application.registry.enabled(account_id)
            and (session.shop_session_id,session.phase)==captured)
    def prepare(db):
        if not same():raise ValueError('Pet feeding selected actor changed')
    if (session.role!='game' or session.phase not in ('town_ready','dungeon_active')
        or not same() or 0x28 not in session.completed
        or type(sequence)is not int or not 1<=sequence<2**32
        or request.performers not in((),(0,))or request.uid!=2**64-1
        or request.target_uid!=2**64-1 or request.payload_mode!=0):return failure()
    operation=session.shop_session_id+':pet-growth:'+str(owner)+':'+str(sequence)
    try:
        return state.handle(path,owner,request.kind,request.payload,operation,
                            account_id=account_id,prepare=prepare)
    except (ValueError,UnicodeError,sqlite3.Error):return failure() if same() else []

def observe(session,reply):
    if session.client_build!='dx11_260923' or not session.item_test or not getattr(session,'reward_receipt',None) or not any(e.kind==0xc1 for e in reply):return []
    with closing(sqlite3.connect(session.account.store.path)) as db:
        try:pet=state.active(db,session.account.uid)
        except ValueError:return []
    return [wire.progress(session.account.uid,pet)]
