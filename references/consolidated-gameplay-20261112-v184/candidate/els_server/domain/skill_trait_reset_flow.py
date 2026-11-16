"""Return the native trait reset reply for manual and recommended skills."""
from els_server.domain.skill_trait_reset import reset_acknowledgement
from els_server.domain.equipment_engrave_flow import current_lease

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x55f or not s.item_test or s.client_build!='dx11_260923':return None
    try:
        actor=s.account;store=actor.store;identity=(actor.uid,actor.account_id,s.shop_session_id,getattr(store,'path',None))
        def guard():
            from els_server.domain.equipment_chip_flow import reset_authority
            reset_authority(s)
            if (s.account is not actor or actor.store is not store or store is None or store.uid!=actor.uid
                or (actor.uid,actor.account_id,s.shop_session_id,store.path)!=identity or actor.characters is None
                or s.role!='game' or s.phase!='town_ready' or not current_lease(s)
                or type(sequence)is not int or not 0<sequence<2**32 or event.performers not in((),(0,))
                or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Trait reset current actor')
        guard()
        from els_server.storage.skill_trait_reset import reset
        operation = f'trait-reset:{s.shop_session_id}:{actor.uid}:{sequence}'
        ack = reset(store.path, actor.uid, actor.account_id, event.payload,
                    operation, prepare=lambda db: guard())
        # BC32D0 removes the trait, refreshes the display and continues Apply.
        # Career refresh emits a 123 for Master characters, which advances
        # the same queue again while the original trait chain is in flight.
        return [ack]
    except ValueError:return[reset_acknowledgement(result=-1)]
