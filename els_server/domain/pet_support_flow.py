"""Route native pet support requests before generic item-use families."""
import uuid
from els_server.protocol import pet_support_messages as wire
from els_server.protocol.career_messages import use_ack
from els_server.storage import pet_support as state

KINDS={0x219,0x661,0x2fb,0x8c7,0x8a1}
def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind not in KINDS or session.client_build!='dx11_260923' or not session.item_test:return None
    if event.kind==0x8a1 and (len(event.payload)<4 or event.payload[:4]!=b'\0\0\0\2'):return None
    kind=event.kind;path=session.account.store.path;owner=session.account.uid
    def failure():
        if kind==0x219:return [use_ack(result=-1)]
        if kind==0x8c7:return [wire.equipment_ack(result=-1)]
        if kind==0x8a1:return [state.bindings_ack(result=-1)]
        if kind==0x661:return [state.initialization(path,owner)]
        return [wire.pet_update(result=-1)]
    if session.role!='game' or session.phase not in (('town_ready',) if kind in (0x219,0x8c7) else ('town_ready','dungeon_active')):
        # Generic career/skill handlers retain their own invalid-phase reply.
        return None if kind==0x219 else failure()
    operation=session.shop_session_id+':pet:'+str(sequence if sequence is not None else uuid.uuid4())
    try:
        if kind==0x219:
            item_uid,_=wire.use_request(event.payload)
            item=next((i for i in session.account.get_inventory_snapshot()['items']if i['uid']==item_uid),None)
            from els_server.storage.pet_support_periods import PRODUCTS as timed_products
            historical=False
            if item is None:
                import json,sqlite3
                from contextlib import closing
                with closing(sqlite3.connect(path))as probe:
                    if probe.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='pet_support_receipts'").fetchone():
                        saved=probe.execute('SELECT context FROM pet_support_receipts WHERE owner=?AND operation=?',(owner,operation)).fetchone()
                        historical=bool(saved and json.loads(saved[0]).get('timed_support'))
            if(item and item['template']in timed_products)or historical:
                from els_server.domain.equipment_chip_flow import reset_context
                from els_server.domain.tenebros_capacity_flow import selected
                reset_context(session,event,sequence)
                selected_path,selected_owner,account_id,prepare=selected(session)
                return state.handle(selected_path,selected_owner,kind,event.payload,operation,account_id=account_id,prepare=prepare)
        return state.handle(path,owner,kind,event.payload,operation)
    except (ValueError,UnicodeError):return failure()
