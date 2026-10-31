"""Route native synergy tickets before generic219 item families."""
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.protocol.career_messages import use_request,use_ack
from els_server.domain.el_search_collection_tickets import catalog,CollectionTicketError


def handle(s,event,sequence):
    if event.event_id==0x202 and event.kind in (0x960,0x962) and s.client_build=='dx11_260923':
        from els_server.domain.quest_flow import account_source_actor,collection_source_guard
        if not account_source_actor(s):return []
        if (event.performers not in ((),(0,))or event.uid!=event.target_uid or event.uid!=2**64-1
            or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):return []
        # The verified shared mutation source is the stable town. Other scene
        # contexts and additional preset pages remain outside this release.
        from els_server.storage.collection_synergy import perform,reply
        operation=s.shop_session_id+':synergy:'+str(s.account.uid)+':'+str(sequence)
        try:
            guard=collection_source_guard(s)
            return perform(s.account.store.path,s.account.uid,s.account.account_id,event.kind,event.payload,operation,guard)
        except ValueError:
            if not account_source_actor(s):return []
            return [reply(event.kind,dict(expansion=0,presets={}),0,result=-1)]

    if (event.event_id!=0x202 or event.kind!=0x219 or s.client_build!='dx11_260923'
        or not s.item_test or s.account.store is None):return None
    try:source=use_request(event.payload)
    except ValueError:return None
    operation=s.shop_session_id+':collection-ticket:'+str(s.account.uid)+':'+str(sequence)
    with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
        row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(s.account.uid,source)).fetchone()
        replay=db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone()else None
    if (row is None or row[0]not in catalog())and not replay:return None
    from els_server.domain.quest_flow import collection_source_guard,account_source_actor
    if not account_source_actor(s):return []
    try:
        if (type(sequence)is not int or not 1<=sequence<2**32 or event.performers!=(0,)
            or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0):
            raise ValueError('Collection ticket native envelope')
        guard=collection_source_guard(s)
        from els_server.storage.el_search_collection_tickets import use
        return use(s.account.store.path,s.account.uid,s.account.account_id,event.payload,operation,guard)
    except CollectionTicketError as error:return [use_ack(result=error.result)]if account_source_actor(s)else[]
    except ValueError:return [use_ack(result=2005)]if account_source_actor(s)else[]
