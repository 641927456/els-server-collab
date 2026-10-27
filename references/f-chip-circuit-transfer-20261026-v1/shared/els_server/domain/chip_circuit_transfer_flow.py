"""Original T-tree D2E; no replacement UI, item source or client adaptation."""
from els_server.protocol import chip_circuit_transfer_messages as wire


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0xd2e or s.client_build!='dx11_260923':
        return None
    try:
        source,target=wire.request(event.payload)
    except ValueError:
        return []
    try:
        from els_server.domain.option_conversion_existing_flow import _session,_selected_authorizer
        selection=_session(s);path,owner,account_id=selection
        authorize=_selected_authorizer(s,selection)
        if (type(sequence)is not int or not 1<=sequence<2**32
            or event.performers not in((),(0,)) or event.uid!=event.target_uid
            or event.uid!=2**64-1 or event.payload_mode!=0
            or s.active_map!=1012 or s.dungeon_return_pending
            or getattr(s,'town_warp_transition',None)is not None):
            raise ValueError('F transfer original loaded actor/envelope')
        from els_server.domain.assembly_flow import _actor,_guard
        guard=_guard(s,_actor(s),town=True)
        def prepare(db,now):
            if not authorize()or s.active_map!=1012 or s.dungeon_return_pending or getattr(s,'town_warp_transition',None)is not None:
                raise ValueError('F transfer selected actor changed')
            guard(db,now)
            return True
        from els_server.storage.chip_circuit_transfer import perform
        operation=s.shop_session_id+':chip-circuit-transfer:'+str(owner)+':'+str(sequence)
        return perform(path,owner,event.payload,operation,account_id=account_id,prepare=prepare)
    except ValueError:
        return [wire.acknowledgement(source,target,result=2005)]
