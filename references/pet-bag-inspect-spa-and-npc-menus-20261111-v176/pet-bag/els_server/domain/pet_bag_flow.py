"""Pet selection supplies the target for native group-13 position moves."""
import struct

from els_server.protocol import pet_bag_messages as wire
from els_server.protocol.companion_messages import uid_request


def handle(session, request, sequence):
    if request.event_id != 0x202 or session.client_build != 'dx11_260923' or not session.item_test:
        return None
    selecting = request.kind == 0xb39
    setting = request.kind == 0x2f8
    if not selecting and not setting and not (request.kind == 0x104 and len(request.payload) == 11
                                               and wire.GROUP in (request.payload[0], request.payload[5])):
        return None

    from els_server.domain.housing_access_flow import capture
    from els_server.storage import pet_bag as storage

    same = None
    try:
        same, guard = capture(session)
        if (request.performers not in ((), (0,)) or request.uid != 2**64 - 1
            or request.target_uid != 2**64 - 1 or request.payload_mode != 0
            or type(sequence) is not int or not 1 <= sequence < 2**32):
            raise ValueError('Invalid pet bag request envelope')
        account = session.account
        owner = account.uid
        if selecting:
            pet = uid_request(request.payload)
            answer = storage.select(account.store.path, owner, account.account_id, pet, guard)
            session.pet_bag_selection = (account.store, owner, pet)
        else:
            selected = getattr(session, 'pet_bag_selection', None)
            if selected is None or selected[0] is not account.store or selected[1] != owner:
                raise ValueError('Select an owned pet bag before moving items')
            if setting:
                if len(request.payload) != 9:
                    raise ValueError('Invalid auto-feed setting request size')
                enabled, pet_uid = struct.unpack('>BQ', request.payload)
                if enabled not in (0, 1) or pet_uid != selected[2]:
                    raise ValueError('Auto-feed setting requires the selected pet')
                answer = storage.set_auto_feed(account.store.path, owner, account.account_id,
                                               pet_uid, bool(enabled), guard)
            else:
                operation = f'{session.shop_session_id}:pet-bag:{owner}:{sequence}'
                answer = storage.move(account.store.path, owner, account.account_id, selected[2],
                                      request.payload, operation, guard)
        return [answer]
    except ValueError:
        if same is not None and not same():
            return []
        if setting:
            return [wire.auto_feed_setting(result=-1)]
        return [wire.selected(result=-1) if selecting else wire.moved(result=-1)]
