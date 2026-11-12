"""Current original NPC exchanges, preserving the preceding specialized writers."""
from contextlib import closing
from functools import partial
from pathlib import Path
import sqlite3,struct
from els_server.domain import npc_exchange_rules as rules
from els_server.protocol.fish_exchange_messages import acknowledgement
from els_server.protocol.protocol_codec import Event,encode_event

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x223 or type(event.payload)is not bytes or len(event.payload)<4:return None
    house=struct.unpack_from('>i',event.payload)[0]
    if str(house)not in rules.catalog()['house_towns']:return None
    try:
        from els_server.domain.housing_access_flow import capture
        same,guard=capture(s)
        if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1
           or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('NPC exchange envelope')
        r=rules.request(event.payload)
        if rules.specialized(r):return None
        rows=rules.selection(r,s.active_map)
        from els_server.domain.hidden_fashion import VOUCHER
        if r.source == VOUCHER:
            from els_server.domain.modern_ice import output_for
            character = s.account.character()
            if character is None:
                raise ValueError('Missing hidden fashion exchange character')
            role = character['unit_type']
            minor = character.get('luciel_active_unit', 0) if role == 10 else 0
            output_for(r.destination, role, minor)
        from els_server.storage.material_exchange import exchange
        from els_server.storage.npc_exchange_source import create
        def factory(db,owner,operation,plan,validate):return create(db,owner,operation,rows,plan,validate)
        return exchange(s.account.store.path,s.account.uid,s.active_map,event.payload,
            s.shop_session_id+':native-npc-exchange:'+str(s.account.uid)+':'+str(sequence),r,
            account_id=s.account.account_id,source_quantity=r.source_quantity,
            acknowledgement=partial(acknowledgement,exchange_type=r.exchange_type),guard=guard,
            draw=partial(rules.awards,rows),npc_source_factory=factory,period_days=rows[0]['period_days'])
    except(ValueError,sqlite3.Error,OverflowError):
        if'same'not in locals()or not same():return[]
        with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            row=db.execute('SELECT b.ed FROM reward_balances b JOIN character_owners o ON o.uid=b.uid WHERE b.uid=?AND o.account_id=?',(s.account.uid,s.account.account_id)).fetchone()
        if row is None:return[]
        kind=struct.unpack_from('>i',event.payload,24)[0]if len(event.payload)>=28 else 3
        answer=Event(0x201,kind=0x224,payload=acknowledgement(row[0],result=-1,exchange_type=kind if kind in(1,2,3,4)else 3))
        encode_event(answer);return[answer]if same()else[]
