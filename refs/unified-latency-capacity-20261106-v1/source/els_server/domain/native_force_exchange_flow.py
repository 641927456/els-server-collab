"""Finite Force NPC recipes through the original manual exchange protocol."""
import sqlite3,struct
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.domain.native_force_catalog import catalog
from els_server.storage.native_force_exchange import exchange,request

def handle(s,e,sequence):
    if not(s.item_test and s.client_build=='dx11_260923'and e.event_id==0x202 and e.kind==0x223):return None
    if not isinstance(e.payload,bytes)or len(e.payload)<4:return None
    house=struct.unpack_from('>i',e.payload)[0]
    if str(house)not in catalog()['npc_towns']:return None
    # Other goods of the same NPC keep their existing dispatcher.
    if len(e.payload)==37:
        source,cost,dest,kind=struct.unpack_from('>iiii',e.payload,12)
        if not any(r['house']==house and r['source']==source and r['source_quantity']==cost and r['type']==kind and (r['destination']==dest if kind==3 else dest==0)for r in catalog()['exchanges']):return None
    from els_server.protocol.fish_exchange_messages import acknowledgement
    from els_server.protocol.protocol_codec import Event
    def context():
        return bool(current_lease(s)and s.role=='game'and 0x28 in s.completed and s.phase=='town_ready'and s.active_map in catalog()['npc_towns'][str(house)]and s.account.store is not None and s.account.characters is not None and s.account.store.uid==s.account.uid)
    if s.account.store is None or 0x28 not in s.completed:raise ValueError('Force exchange before character selection')
    try:
        if not context()or type(sequence)is not int or not 1<=sequence<2**32 or e.performers!=(0,)or e.uid!=e.target_uid or e.uid!=0xffffffffffffffff or e.payload_mode!=0:raise ValueError('Force exchange context')
        request(e.payload)
        return exchange(s.account.store.path,s.account.uid,s.active_map,e.payload,s.shop_session_id+':force-exchange:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id,authorize=context)
    except(ValueError,sqlite3.Error):
        from contextlib import closing
        from pathlib import Path
        from els_server.storage.reward_state import validate_balances
        with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            row=db.execute('SELECT b.ed,b.experience,b.revision FROM reward_balances b JOIN character_owners o ON o.uid=b.uid WHERE b.uid=? AND o.account_id=?',(s.account.uid,s.account.account_id)).fetchone()
        return [Event(0x201,kind=0x224,payload=acknowledgement(validate_balances(row)['ed'],result=-1))]
