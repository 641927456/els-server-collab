"""One owned town adapter for the source-qualified four-product EP ledger."""
import sqlite3
from els_server.domain.dungeon_equipment_loot_flow import current_lease
from els_server.protocol.ep_shop_messages import purchase_ack,count_snapshot
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.ep_shop import purchase,snapshot


def context(session,event,sequence):
    account=getattr(session,'account',None);store=getattr(account,'store',None)
    uid=getattr(account,'uid',None)
    valid=(session.role=='game' and session.phase=='town_ready' and store is not None
        and getattr(account,'characters',None) is not None and type(uid) is int
        and getattr(store,'uid',None)==uid and type(sequence) is int and 1<=sequence<2**32
        and event.performers==(0,) and event.uid==event.target_uid==0xffffffffffffffff
        and event.payload_mode==0 and current_lease(session))
    return (store.path,account.account_id,uid) if valid else None


def _success(ep,counts,items):
    events=(purchase_ack(0,ep,counts,items),count_snapshot(counts))
    # Both native replies must encode inside the storage transaction. A5E is
    # required even on a committed old-operation refresh, not a delta cache map.
    for event in events:encode_event(event)
    return events


def handle(session,event,sequence):
    if not (session.item_test and session.client_build=='dx11_260923'
            and event.event_id==0x202 and event.kind==0xa5f):return None
    owned=context(session,event,sequence)
    if owned is None:return [purchase_ack(-1,0,{},[])]
    path,account_id,uid=owned
    try:
        operation=session.shop_session_id+':'+str(uid)+':ep-purchase:'+str(sequence)
        return list(purchase(path,event.payload,operation,account_id=account_id,uid=uid,encode=_success))
    except (ValueError,sqlite3.Error):
        # Actor/owner revalidation occurs in this fresh read. Invalid context
        # never reaches it; a failed purchase never discloses a sibling wallet.
        try:ep=snapshot(path,account_id=account_id,uid=uid)['ep']
        except (ValueError,sqlite3.Error):ep=0
        return [purchase_ack(-1,ep,{},[])]
