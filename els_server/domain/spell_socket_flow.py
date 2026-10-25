"""Original single-slot mystic producer in the current real actor/scene lease."""
import struct
from pathlib import Path
from els_server.domain.equipment_chip_flow import reset_context
from els_server.protocol.spell_socket_messages import request,acknowledgement
BUSINESS_ENABLED=True

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x6e7 or not s.item_test or s.client_build!='dx11_260923':return None
    payload=event.payload
    if not isinstance(payload,bytes)or len(payload)<6:return None
    mode=struct.unpack_from('>i',payload,len(payload)-5)[0]
    if mode not in(2,4):return None
    uid=0;ed=0
    try:
        uid,group,slot,source,mode=request(payload);reset_context(s,event,sequence)
        account=s.account;store=account.store;root=account.root;app=getattr(s,'application',None);local=getattr(s,'_chip_reset_local_application',None)
        identity=getattr(s,'identity',None);owner=account.uid;account_id=account.account_id;session=s.shop_session_id;path=Path(store.path).resolve();scene=s.active_map
        if s.pending_map!=scene or s.dungeon_return_pending or account.get_location()['map']!=scene:raise ValueError('Mystic stable native town scene')
        ed=account.get_reward_balances()['ed']
        if not BUSINESS_ENABLED:raise ValueError('Mystic writes disabled by compatible recovery')
        def authorize(db):
            reset_context(s,event,sequence)
            if (s.account is not account or account.store is not store or account.root is not root
                or getattr(s,'application',None)is not app or getattr(s,'_chip_reset_local_application',None)is not local
                or getattr(s,'identity',None)is not identity or (account.uid,account.account_id,s.shop_session_id,s.active_map,s.pending_map)!=(owner,account_id,session,scene,scene)
                or s.dungeon_return_pending or Path(store.path).resolve()!=path
                or db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(scene,)):
                raise ValueError('Mystic original actor/scene generation changed')
        from els_server.storage.spell_socket import perform
        return perform(path,owner,payload,session+':mystic-native:'+str(owner)+':'+str(sequence),account_id=account_id,authorize=authorize)
    except ValueError:return [acknowledgement(uid,ed,mode=mode,result=2005)]
