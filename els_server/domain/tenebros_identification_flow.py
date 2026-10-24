"""Native initial identification only; existing shadow effects cannot reroll."""
from els_server.protocol import tenebros_identification_messages as wire


def handle(s, event, sequence):
    if event.event_id != 0x202 or event.kind != 0x9ef or s.client_build != 'dx11_260923':
        return None
    try:
        wire.request(event.payload)
        if (type(sequence) is not int or not 1 <= sequence < 2**32
                or event.performers not in ((), (0,))
                or event.uid != 0xffffffffffffffff or event.target_uid != 0xffffffffffffffff
                or event.payload_mode != 0):
            raise ValueError('Tenebros identification envelope')
        from els_server.domain.tenebros_capacity_flow import selected
        path, owner, account_id, prepare = selected(s)
        from els_server.storage.tenebros_identification import perform
        operation = (s.shop_session_id + ':tenebros-identify-v1:' + str(account_id)
                     + ':' + str(owner) + ':' + str(sequence))
        return perform(path, owner, account_id, event.payload, operation, prepare=prepare)
    except ValueError:
        return [wire.acknowledgement(result=2005)]
