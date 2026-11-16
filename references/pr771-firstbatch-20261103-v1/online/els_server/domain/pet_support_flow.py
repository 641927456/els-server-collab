"""Route native pet support requests before generic item-use families."""
import json,sqlite3
from contextlib import closing
from pathlib import Path
from els_server.protocol import pet_support_messages as wire
from els_server.protocol.career_messages import use_ack
from els_server.storage import pet_support as state

KINDS={0x219,0x661,0x2fb,0x8c7,0x8a1}
def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind not in KINDS or session.client_build!='dx11_260923' or not session.item_test:return None
    if event.kind==0x8a1 and (len(event.payload)<4 or event.payload[:4]!=b'\0\0\0\2'):return None
    kind=event.kind
    def failure(restore=False):
        current=None
        if restore and kind in (0x219,0x661,0x8a1):
            try:
                prepare(None)
                with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:
                    from els_server.storage.item_actor import require_active_character
                    from els_server.storage.profession_state import require_owner
                    db.execute('BEGIN');require_active_character(db,owner);require_owner(db,owner,account_id)
                    current=state.automatic(db,owner)
                    prepare(None)
            except ValueError:return failure()
        if kind==0x219:return [use_ack(result=-1)]+([wire.settings(current,0xb3b)]if current is not None else [])
        if kind==0x8c7:return [wire.equipment_ack(result=-1)]
        if kind==0x8a1:return [state.bindings_ack(current,result=-1)]
        if kind==0x661:return [wire.settings(current or state.DEFAULT)]
        return [wire.pet_update(result=-1)]
    if session.role!='game' or session.phase not in (('town_ready',) if kind in (0x219,0x8c7) else ('town_ready','dungeon_active')):
        # Generic career/skill handlers retain their own invalid-phase reply.
        return None if kind==0x219 else failure()
    from els_server.domain.equipment_chip_flow import current_lease
    account=session.account;store=account.store
    if (store is None or store.uid!=account.uid or not current_lease(session)
        or getattr(session,'released',False) or type(sequence)is not int or not 1<=sequence<2**32
        or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1
        or event.payload_mode!=0):return failure()
    path=Path(store.path).resolve();owner=account.uid;account_id=account.account_id
    captured=(session.shop_session_id,session.phase)
    def prepare(db):
        if (session.account is not account or account.store is not store or store.uid!=owner
            or account.uid!=owner or account.account_id!=account_id or Path(store.path).resolve()!=path
            or (session.shop_session_id,session.phase)!=captured or not current_lease(session)
            or getattr(session,'released',False)):
            raise ValueError('Pet support selected actor changed')
    operation=session.shop_session_id+':pet:'+str(sequence)
    try:
        if kind==0x219:
            item_uid,_=wire.use_request(event.payload)
            from els_server.storage.inventory_state import owned_template
            from els_server.storage.pet_support_periods import PRODUCTS as timed_products
            with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as probe:
                template=owned_template(probe,owner,item_uid)
                saved=probe.execute('SELECT context FROM pet_support_receipts WHERE owner=?AND operation=?',(owner,operation)).fetchone()if probe.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='pet_support_receipts'").fetchone()else None
            if template not in state.PRODUCTS and saved is None:return None
            historical=bool(saved and json.loads(saved[0]).get('timed_support'))
            if template in timed_products or historical:
                from els_server.domain.equipment_chip_flow import reset_context
                from els_server.domain.tenebros_capacity_flow import selected
                reset_context(session,event,sequence)
                selected_path,selected_owner,account_id,prepare=selected(session)
                return state.handle(selected_path,selected_owner,kind,event.payload,operation,account_id=account_id,prepare=prepare)
        return state.handle(path,owner,kind,event.payload,operation,account_id=account_id,prepare=prepare)
    except (ValueError,UnicodeError) as error:
        session._pet_support_rejection=str(error)
        return failure(restore=True)
