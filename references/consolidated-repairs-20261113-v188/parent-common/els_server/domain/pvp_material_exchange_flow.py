"""Authenticated Camilla manual-choice exchange; original223/224 UI retained."""
import sqlite3,struct
from contextlib import closing
from els_server.protocol.purifier_exchange_messages import ExchangeRequest
from els_server.protocol.fish_exchange_messages import acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.domain.pvp_material_exchange import recipe

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x223 or len(event.payload)<16:return None
    if struct.unpack_from('>i',event.payload)[0]!=40016 or struct.unpack_from('>i',event.payload,12)[0]!=72920:return None
    try:
        from els_server.domain.housing_access_flow import capture
        same,guard=capture(s)
        if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32 or len(event.payload)!=37):raise ValueError('PvP material original envelope')
        r=ExchangeRequest(*struct.unpack('>iQiiiiiBi',event.payload));town=s.active_map;recipe(r,town)
        from els_server.storage.material_exchange import exchange
        return exchange(s.account.store.path,s.account.uid,town,event.payload,s.shop_session_id+':pvp-material:'+str(s.account.uid)+':'+str(sequence),r,
                        account_id=s.account.account_id,source_quantity=1,destination=r.destination,output_quantity=1,
                        acknowledgement=acknowledgement,guard=guard)
    except(ValueError,sqlite3.Error,OverflowError,AttributeError):
        if'same'not in locals()or not same():return[]
        with closing(sqlite3.connect(s.account.store.path))as db:
            row=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(s.account.uid,)).fetchone()
        return[]if row is None else[Event(0x201,kind=0x224,payload=acknowledgement(row[0],result=-1))]
