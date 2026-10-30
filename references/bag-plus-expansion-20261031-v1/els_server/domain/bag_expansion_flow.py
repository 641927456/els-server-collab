"""Connect the native inventory expansion popup to existing bag allowances."""
from contextlib import closing
import sqlite3
from els_server.protocol import bag_expansion_messages as wire
from els_server.domain.equipment_chip_flow import current_lease


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x47b,0x479) or s.client_build!='dx11_260923':return None
    quote=event.kind==0x47b
    failure=wire.quote_ack if quote else wire.expansion_ack
    account=s.account;store=account.store;uid=account.uid;account_id=account.account_id;session=s.shop_session_id
    def prepare(db):
        if (not s.item_test or s.role!='game' or s.phase!='town_ready' or not current_lease(s)
            or getattr(s,'released',False) or s.account is not account or account.store is not store
            or store is None or store.uid!=uid or (account.uid,account.account_id,s.shop_session_id)!=(uid,account_id,session)
            or type(sequence) is not int or not 1<=sequence<2**32
            or event.performers not in ((),(0,)) or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
            raise ValueError('Bag expansion selected actor/context')
    try:
        prepare(None);group=wire.request(event.payload)
        key=(uid,group)
        if not hasattr(s,'bag_expansion_quotes'):s.bag_expansion_quotes={}
        from els_server.storage.bag_capacity import expansion_quote,direct_expansion
        if quote:
            from els_server.storage.profession_state import require_owner
            from els_server.storage.item_actor import require_active_character
            with closing(sqlite3.connect(store.path,timeout=10)) as db:
                db.execute('BEGIN');require_owner(db,uid,account_id);require_active_character(db,uid)
                offer=expansion_quote(db,uid,group)
            s.bag_expansion_quotes[key]=offer
            return [wire.quote_ack(offer[2])]
        operation=session+':bag-expand:'+str(uid)+':'+str(sequence)
        event=direct_expansion(store.path,uid,account_id,event.payload,operation,
            expected=s.bag_expansion_quotes.get(key),prepare=prepare)
        s.bag_expansion_quotes.pop(key,None)
        return [event]
    except ValueError:return [failure(result=-1)]
