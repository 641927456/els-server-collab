"""Original right-click quantity confirmation, without client adaptation."""
from els_server.protocol.protocol_codec import Event
from els_server.protocol.el_shard_messages import acknowledgement

def handle(session,event,sequence):
    if not(session.item_test and session.client_build=='dx11_260923' and event.event_id==0x202 and event.kind==0x45e):return None
    from els_server.domain.equipment_engrave_flow import current_lease
    from els_server.storage.el_shard_extraction import extract
    actor=session.account;store=actor.store
    identity=(actor.uid,actor.account_id,session.shop_session_id,store.path if store else None)
    def prepare():
        if(not current_lease(session) or session.role!='game' or session.phase!='town_ready'
                or session.account.characters is None or session.account.store is None
                or session.account.store.uid!=session.account.uid
                or session.account is not actor or actor.store is not store
                or(actor.uid,actor.account_id,session.shop_session_id,store.path if store else None)!=identity
                or type(sequence) is not int or not 1<=sequence<2**32
                or event.performers not in((),(0,)) or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            raise ValueError('El Shard selected actor admission')
    try:
        prepare()
        operation=session.shop_session_id+':'+str(actor.uid)+':el-shard:'+str(sequence)
        return extract(store.path,actor.uid,event.payload,operation,
                       account_id=actor.account_id,prepare=prepare)
    except ValueError:
        return [Event(0x201,kind=0x45f,payload=acknowledgement(result=-1))]
