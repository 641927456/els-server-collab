"""Preset keyboard UI persistence; native Apply calls the original page routes."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol import character_preset_messages as wire


def handle_coupon(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219 or s.client_build!='dx11_260923' or not s.item_test:return None
    from els_server.protocol.career_messages import use_request,use_ack
    from els_server.domain.character_preset_coupons import SOURCES
    from els_server.storage.read_scope import snapshot_connection
    account=s.account;store=account.store
    if store is None or account.characters is None:return None
    try:source=use_request(event.payload)
    except ValueError:return None
    operation=s.shop_session_id+':preset-expand:'+str(account.uid)+':'+str(sequence)
    with snapshot_connection(store.path)as db:
        item=db.execute('SELECT template FROM inventory_items WHERE owner=?AND uid=?',(account.uid,source)).fetchone()
        prior=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='inventory_action_receipts'").fetchone()
            and db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=?AND owner=?AND kind=?',(operation,account.uid,0x219)).fetchone())
    if not(item and item[0]in SOURCES)and not prior:return None
    try:
        if (type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Preset expansion envelope')
        from els_server.domain.quest_flow import collection_source_guard
        from els_server.storage.character_presets import expand
        result=expand(store.path,account.uid,account.account_id,event.payload,operation,collection_source_guard(s))
        if result is None:raise ValueError('Preset coupon no longer owned')
        return result
    except ValueError as error:
        s._character_preset_rejection=str(error)
        return [use_ack(result=1)]


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x959,0x784,0xb29):return None
    try:
        if (s.client_build!='dx11_260923' or type(sequence)is not int or not 1<=sequence<2**32
            or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1
            or event.payload_mode!=0):raise ValueError('Preset save envelope')
        from els_server.domain.quest_flow import collection_source_guard
        guard=collection_source_guard(s)
        if event.kind==0xb29:
            # 12163A0 -> C656B0; BEC540 consumes result + selected i32.
            # The existing collection store only owns its original page 1.
            if event.payload!=struct.pack('>i',1):raise ValueError('Unowned synergy page')
            from els_server.storage.read_scope import snapshot_connection
            with snapshot_connection(s.account.store.path)as db:
                db.execute('BEGIN')
                guard(db)
                from els_server.storage.profession_state import require_owner
                require_owner(db,s.account.uid,s.account.account_id)
                return [Event(0x201,kind=0xb2a,payload=struct.pack('>ii',0,1))]
        if event.kind==0x784:
            # The existing worn inventory is equipment page 1. Do not grant
            # additional equipment pages through a saved preset reference.
            result=0 if event.payload==struct.pack('>H',1)else 1
            from els_server.storage.avatar_sets import owner_side,snapshot
            from els_server.protocol.avatar_set_messages import restoration,empty_restoration
            from els_server.storage.read_scope import snapshot_connection
            with snapshot_connection(s.account.store.path)as db:
                db.execute('BEGIN')
                guard(db)
                owner_side(db,s.account.uid,s.account.account_id)
                _,rows=snapshot(db,s.account.uid)
                current=restoration(rows,page=1,total=1)if rows else empty_restoration(page=1,total=1)
                answer=wire.equipment_selection(current,result=result)
                guard(db)
                return [answer]
        from els_server.storage.character_presets import save
        return save(s.account.store.path,s.account.uid,s.account.account_id,event.payload,
            s.shop_session_id+':preset:'+str(sequence),guard)
    except (ValueError,UnicodeError)as error:
        s._character_preset_rejection=str(error)
        if event.kind==0x959:return [wire.acknowledgement(1)]
        if event.kind==0xb29:return [Event(0x201,kind=0xb2a,payload=struct.pack('>ii',1,1))]
        from els_server.protocol.avatar_set_messages import empty_restoration
        return [wire.equipment_selection(empty_restoration(page=1,total=1),result=1)]
