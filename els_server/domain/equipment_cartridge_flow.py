"""Complete native failure acknowledgements for unqualified cartridge operations.

The client owns the UI and its waiting state. Registration, equip, removal and
growth remain unavailable until material/share/authority rules are qualified.
No collection initialization, SQL mutation, charge or success is manufactured.
"""
from els_server.protocol.equipment_cartridge_messages import acknowledge, request

REQUEST_KINDS = frozenset((0xd4e, 0xd50, 0xd52, 0xd54))


def handle(s, event, sequence):
    if (event.event_id != 0x202 or event.kind not in REQUEST_KINDS
            or s.client_build != 'dx11_260923'):
        return None
    identity = 0
    ed = 0
    try:
        fields = request(event.kind, event.payload)
        if (s.role != 'game' or s.phase != 'town_ready'
                or not s.item_test or s.account.characters is None
                or s.account.store is None
                or type(sequence) is not int or not 1 <= sequence < 2**32
                or event.performers not in ((), (0,))
                or event.uid != 0xffffffffffffffff
                or event.target_uid != 0xffffffffffffffff
                or event.payload_mode != 0):
            raise ValueError('Cartridge session envelope')
        if event.kind == 0xd50:
            identity = fields[1]
        elif event.kind == 0xd54:
            identity = fields[0]
        # The initialized selected actor already owns this balance. On the
        # native nonzero-result branch neither ED nor the empty map is applied.
        if event.kind == 0xd54:
            ed = s.account.get_reward_balances()['ed']
    except ValueError:
        identity = 0
    kind = event.kind + 1
    extras = {'points': 0} if kind in (0xd4f, 0xd55) else {}
    if kind == 0xd55:
        extras['ed'] = ed
    return [acknowledge(kind, result=2005, identity=identity, rows={}, **extras)]
