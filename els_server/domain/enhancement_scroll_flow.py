"""+13 enhancement scroll use; only scroll-sourced 0x219 packets are claimed."""
from els_server.domain.equipment_chip_flow import current_lease
from els_server.protocol.career_messages import use_ack
from els_server.storage import enhancement_scroll as store


def enabled(s):
    return (s.item_test and s.client_build == 'dx11_260923'
            and s.account.characters is not None and s.account.store is not None
            and s.account.store.uid == s.account.uid and s.role == 'game'
            and s.phase == 'town_ready' and current_lease(s))


def handle(s, event, sequence):
    if event.event_id != 0x202 or event.kind != 0x219:
        return None
    if (not s.item_test or s.client_build != 'dx11_260923'
            or s.account.characters is None or s.account.store is None):
        return None
    if type(sequence) is not int or not 1 <= sequence < 2**32:
        return None
    operation = s.shop_session_id+':enhancement-scroll-v1:'+str(s.account.uid)+':'+str(sequence)
    if not store.candidate(s.account.store.path, s.account.uid, event.payload, operation):
        return None
    if not enabled(s):
        return [use_ack(result=-1)]
    try:
        return store.use(s.account.store.path, s.account.uid, s.account.account_id,
                         event.payload, operation)
    except ValueError:
        return [use_ack(result=-1)]
