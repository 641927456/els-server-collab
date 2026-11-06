"""Four original fishing items; no attempt timer, reward or life-budget policy."""
import functools
import hashlib
import struct

ROWS = {
    135928: (1, 21, 22, 0, 39, 'afca1f5b9f1883e32fa56037110bbb7db8acffd9c3cf7d902184bf7814c1cb2a'),
    135929: (1, 21, 22, 1, 40, '46de956a17a7eba6715a710340bda6224a92f4c4fbc4dc0aaecf4a9ecea7103b'),
    135931: (1, 21, 22, 2, 41, 'bec59846b619d5683b074c752c5dba3a191e087450d04d72b7a54ea99a4ceec5'),
    99809: (2, 3, 23, 0, 42, 'f3dfcfc91db553a431f8411e81427adc35cfe5e33c9b52e57bae86e1fb806742'),
}
WRITER_ENABLED = True


@functools.lru_cache(maxsize=4)
def definition(template):
    if template not in ROWS:
        raise ValueError('Outside finite fishing equipment scope')
    from els_server.game_data import client_data
    metadata, bag, equipped, slot, key, pin = ROWS[template]
    row = client_data().item(template)
    enum = client_data().resource('Enum.lua')
    if (hashlib.sha256(row['record']).hexdigest() != pin
            or row['metadata'] != metadata or row['equip_position'] != key
            or row['item_type'] != (6 if template == 99809 else 15)):
        raise ValueError('Fishing equipment source identity')
    if {k: enum['SORT_TYPE'][k] for k in ('ST_LIFE', 'ST_E_FISHING', 'ST_E_FISHING_BAIT')} != {
            'ST_LIFE': 21, 'ST_E_FISHING': 22, 'ST_E_FISHING_BAIT': 23}:
        raise ValueError('Fishing original groups')
    return dict(metadata=metadata, bag=bag, equipped=equipped, slot=slot, key=key)


def accepts_equipped(item):
    if item.get('template') not in ROWS:
        return False
    row = definition(item['template'])
    return (item['metadata'] == row['metadata'] and item['group'] == row['equipped']
            and item['slot'] == row['slot'])


def equipment_entries(items):
    from els_server.domain.inventory_items import validate_item
    return [(definition(i['template'])['key'], validate_item(i))
            for i in items if i.get('group') in (22, 23)]


def positions(payload):
    if type(payload) is not bytes or len(payload) != 11:
        raise ValueError('Fishing wear request length')
    sg, ss, dg, ds, flag = struct.unpack('>BiBiB', payload)
    from els_server.domain.bag_capacity import wire_limit
    if flag or {sg, dg} not in ({21, 22}, {3, 23}):
        raise ValueError('Fishing wear original groups')
    for group, slot in ((sg, ss), (dg, ds)):
        valid = (0 <= slot < wire_limit(group) if group in (3, 21)
                 else 0 <= slot < 3 if group == 22 else slot == 0)
        if not valid:
            raise ValueError('Fishing wear position')
    return (sg, ss), (dg, ds)


def capture(session):
    from els_server.domain.tutorial_accessory import wear_context
    facts = wear_context(session)
    if session.account.store.uid != session.account.uid:
        raise ValueError('Fishing wear selected owner')
    pending = getattr(session, 'pending_map', None)
    location = getattr(session.account, 'location', None)
    return facts, (session.phase, session.active_map, id(pending), repr(pending),
                   getattr(session, 'map_synchronizing', None), id(location), repr(location))


def validate_context(session, captured):
    from els_server.domain.tutorial_accessory import validate_wear_context
    validate_wear_context(session, captured[0])
    if capture(session)[1] != captured[1]:
        raise ValueError('Fishing wear source changed before commit')


def _reply_binding(s):
    # Capture the original graph independently from eligibility so an ordinary
    # malformed request can still clear its own wait, never a replacement's.
    a=s.account;app=getattr(s,'application',None)
    world=getattr(app,'world',None);room=world.room(s) if world is not None else None
    entry=room.get(s) if room is not None else None
    location=getattr(a,'location',None);pending=getattr(s,'pending_map',None)
    objects=(a,a.store,a.characters,getattr(a,'root',None),app,getattr(s,'identity',None),world,room,entry)
    facts=(a.uid,a.account_id,a.store.uid,s.shop_session_id,s.role,s.phase,s.active_map,
           id(pending),repr(pending),getattr(s,'map_synchronizing',None),id(location),repr(location),
           repr(a.get_location()),repr(getattr(s,'completed',None)),
           getattr(s,'item_test',None),getattr(s,'client_build',None),
           world.members.get(s) if world is not None else None,
           repr(entry[0]) if entry is not None else None)
    return objects,facts


def handle(session, event, sequence):
    from els_server.protocol.protocol_codec import Event
    from els_server.domain.fashion_state import move_ack
    from els_server.domain.town_travel_flow import _ordinary_actor
    if not _ordinary_actor(session) or session.account.characters is None:return []
    bound=_reply_binding(session)
    def current():
        try:
            now=_reply_binding(session)
            return bool(_ordinary_actor(session) and all(a is b for a,b in zip(now[0],bound[0])) and now[1]==bound[1])
        except (ValueError,AttributeError,KeyError,TypeError):return False
    try:
        if (event.event_id != 0x202 or event.kind != 0x104 or event.performers != (0,)
                or event.uid != 0xffffffffffffffff or event.target_uid != 0xffffffffffffffff
                or event.payload_mode != 0):
            raise ValueError('Fishing wear envelope')
        captured = capture(session)
        from els_server.storage.fishing_equipment import move
        def validate():
            if not current():raise ValueError('Fishing wear original reply actor graph changed')
            validate_context(session, captured)
        answer = move(session.account.store.path, event.payload, session.account.uid,
                      account_id=session.account.account_id, session_id=session.shop_session_id,
                      sequence=sequence, expected_town=session.active_map,
                      validate=validate)
    except ValueError:
        if not current():return []
        answer = move_ack(result=-1)
        if not current():return []
    return [Event(0x201, kind=0x105, payload=answer)]
