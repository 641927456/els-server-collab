"""Native storage dispatch using the current capacity actor/NPC authority."""
from pathlib import Path
from els_server.protocol import tenebros_storage_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.domain.tenebros_capacity_flow import selected, selection_snapshot


def handle(s, event, sequence):
    kinds = (0x9f4, 0x9f6, 0x9f8, 0x855)
    if event.event_id != 0x202 or event.kind not in kinds or s.client_build != 'dx11_260923':
        return None
    try:
        if (type(sequence) is not int or not 1 <= sequence < 2**32 or event.performers not in ((), (0,))
                or event.uid != 0xffffffffffffffff or event.target_uid != 0xffffffffffffffff or event.payload_mode != 0):
            raise ValueError('Tenebros storage envelope')
        path, owner, account_id, prepare = selected(s, npc=event.kind != 0x855)
        from els_server.storage.tenebros_storage import perform
        operation = s.shop_session_id+':tenebros-storage:'+str(account_id)+':'+str(owner)+':'+str(sequence)
        replies = perform(path, owner, account_id, event.kind, event.payload, operation,
                          s.shop_session_id, prepare=prepare)
        if event.kind == 0x9f6 and replies and int.from_bytes(replies[0].payload[:4], 'big', signed=True) == 0:
            s.tenebros_storage_selected = (s.account, s.account.store, s.account.root,
                path, owner, account_id, s.shop_session_id)
        # Retain the server capture until departure. A replayed old confirm or
        # cancel must not erase cleanup ownership of a newer paid pending.
        return replies
    except ValueError:
        if event.kind == 0x855:
            return []  # No dedicated native cancellation ACK is evidenced.
        ack = {0x9f4: wire.save_ack, 0x9f6: wire.load_ack, 0x9f8: wire.confirm_ack}[event.kind]
        return [ack(result=2005)]


def initialize_login(s, messages):
    """9F1 is consumed by CX2StateServerSelect, before the 29 login ACK."""
    if not (s.client_build == 'dx11_260923' and s.item_test and s.account.characters is not None):
        return messages
    from els_server.storage.tenebros_storage import snapshot
    path, owner, account_id, prepare = selection_snapshot(s)
    current = snapshot(path, owner, account_id, prepare=prepare)
    notice = wire.state(current['extras'], current['options'])
    encode_event(notice)
    # 2A has installed the active character. 29 advances its login state.
    index = next(i for i, event in enumerate(messages) if event.event_id == 0x201 and event.kind == 0x29)
    return [*messages[:index], notice, *messages[index:]]


def abandon(s):
    """Invoke before clearing the accepted actor on disconnect/character/phase exit."""
    captured = getattr(s, 'tenebros_storage_selected', None)
    if captured is None:
        return
    account, store, root, path, owner, account_id, session_key = captured
    if (s.account is not account or account.store is not store or account.root is not root
            or (account.uid, account.account_id, s.shop_session_id) != (owner, account_id, session_key)
            or Path(store.path).resolve() != path):
        raise ValueError('Tenebros cleanup actor changed before release')
    from els_server.storage.tenebros_storage import abandon as discard
    discard(path, owner, account_id, session_key)
    s.tenebros_storage_selected = None
