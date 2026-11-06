"""Original6E7 modes12/11 from the existing Camilla specialization UI."""
import sqlite3,struct
from contextlib import closing
from els_server.domain.pvp_specialization import request
from els_server.protocol.spell_socket_messages import acknowledgement

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x6e7 or len(event.payload)<6:return None
    mode=struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]
    if mode not in(11,12):return None
    uid=0
    try:
        from els_server.domain.housing_access_flow import capture
        same,guard=capture(s)
        from els_server.domain.pvp_material_exchange import catalog
        if(s.active_map not in map(int,catalog()['towns'])or event.performers not in((),(0,))or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('PvP specialization original actor/envelope')
        uid,*_=request(event.payload)
        from els_server.storage.pvp_specialization import perform
        return perform(s.account.store.path,s.account.uid,s.account.account_id,event.payload,s.shop_session_id+':pvp-specialization:'+str(s.account.uid)+':'+str(sequence),guard)
    except(ValueError,sqlite3.Error,OverflowError,AttributeError):
        if'same'not in locals()or not same():return[]
        from els_server.storage.pvp_official_profiles import snapshot
        from els_server.storage.npc_trade import balances
        with closing(sqlite3.connect(s.account.store.path))as db:
            db.execute('BEGIN')
            profile=snapshot(db,s.account.uid,s.account.account_id);ed=balances(db,s.account.uid)['ed']
        return[acknowledgement(uid,ed,mode=mode,ap=profile[0].ap if profile else 0,result=2005)]
