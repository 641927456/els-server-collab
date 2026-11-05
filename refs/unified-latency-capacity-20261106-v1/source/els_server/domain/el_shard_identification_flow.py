"""Existing right-click mystery shard206 selected-character dispatch."""
from els_server.protocol.protocol_codec import Event
from els_server.protocol.el_shard_identification_messages import acknowledgement
def handle(session,event,sequence):
    if not(session.item_test and session.client_build=='dx11_260923' and event.event_id==0x202 and event.kind==0x206):return None
    from els_server.domain.equipment_engrave_flow import current_lease
    from els_server.storage.el_shard_identification import identify
    actor=session.account;store=actor.store
    identity=(actor.uid,actor.account_id,session.shop_session_id,store.path if store else None)
    def prepare():
        if(not current_lease(session)or session.role!='game'or session.phase!='town_ready'
                or actor.characters is None or store is None or store.uid!=actor.uid
                or session.account is not actor or actor.store is not store
                or(actor.uid,actor.account_id,session.shop_session_id,store.path if store else None)!=identity
                or type(sequence)is not int or not 1<=sequence<2**32
                or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Shard identification current actor')
    ed=0
    try:
        prepare();ed=actor.get_reward_balances()['ed']
        operation=session.shop_session_id+':'+str(actor.uid)+':shard-identify:'+str(sequence)
        return identify(store.path,actor.uid,event.payload,operation,account_id=actor.account_id,prepare=prepare)
    except ValueError:return[Event(0x201,kind=0x207,payload=acknowledgement(ed,result=-1))]
