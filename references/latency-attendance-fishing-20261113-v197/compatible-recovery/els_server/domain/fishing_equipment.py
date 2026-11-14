"""Finite original fishing items; no attempt timer, reward or life-budget policy."""
import functools
import hashlib
import struct

from els_server.domain.npc_exchange_rules import DIANA_TOWN

# The two Helen spas share the original Elrios fish and House40256 recipes.
ELRIOS_FISHING_TOWNS = frozenset((1500, 1501))
FISHING_TOWNS = ELRIOS_FISHING_TOWNS | {DIANA_TOWN}
SHOP_RODS = frozenset((135928, 135995))
# Nexon probability disclosure 234; current CN item records identify each rod.
ROD_SUCCESS = {135928: 50, 135995: 30, 136026: 50, 313129: 80, 321145: 60, 321146: 50, 321147: 60, 321148: 60, 321149: 70, 322850: 70, 570321: 70, 570341: 70, 570380: 70, 570420: 70, 570460: 70, 570499: 70, 570539: 70, 570637: 70, 570701: 70, 570744: 70, 580013: 70, 580054: 70, 580096: 70, 580182: 70, 580221: 70, 717878: 50, 720859: 80}
RODS = frozenset(ROD_SUCCESS)
# Readers/use only: this change does not open new DIY or event producers.
OWNED_RODS = RODS - SHOP_RODS

# Fixed options from the pinned item rows below and OptionItemData.lua:
# 110037/110041: success, 110007/110011: wait, 110101: endurance.
# Columns are percentage points of success, wait reduction, endurance reduction.
OPTIONS = {
    135929: (3, 0, 0),
    135930: (5, 0, 5),
    135931: (0, 3, 0),
    135932: (0, 5, 5),
}

ROWS = {
    136026: (1, 21, 22, 0, 39, '30d0b2bd83c5cebd00fc11baa11ef30f13565e0caaa51eea60affd33775abc7b'),
    313129: (1, 21, 22, 0, 39, '424c13ec463982e0fbd7be4696bdfcb1cfa4aa8fd4a3a3a98ca8f7b236e61878'),
    321145: (1, 21, 22, 0, 39, '8b8cbd5d0c24ac11a4406a426135557b0dfc37f22e5fcea7a045ea55413f3d41'),
    321146: (1, 21, 22, 0, 39, 'ec433c12fc173a42fff9a677047bcff3cfac7966c0fa58aad443992d1dda0b8f'),
    321147: (1, 21, 22, 0, 39, 'e17f1d7f3a25fd2e8cbd59841091f1bafbd5f0dfbe16f8e403f6fd87fe9a3184'),
    321148: (1, 21, 22, 0, 39, '7f972daae94b3d3e09c79672da8415ccee6d7665642c43ae588df1bef85fd130'),
    321149: (1, 21, 22, 0, 39, '823f7872d1cbb9231c3e08d9f190b29c180bcc33b96d3279c17cf8816eea68de'),
    322850: (1, 21, 22, 0, 39, 'b5a8ed05ac00c70e0c9ad4889d0bd0607a6ef2c434a5ed6429f250c8fa91e255'),
    570321: (1, 21, 22, 0, 39, '5787ed78e24b45f56f23a24f85faf56134f870bdd8803ca2f2c45c962641f6be'),
    570341: (1, 21, 22, 0, 39, '7187c946623116317056421bb7da7cf88c628d917c25a373ab4646e2a4e9c853'),
    570380: (1, 21, 22, 0, 39, '5858f953c556af74fc1b97cf683b8c0075083dd2353db58597ee088259256470'),
    570420: (1, 21, 22, 0, 39, '87f9dab575b291f442bb9eb518d239333a555284b39d3094d2ddebc4903e8097'),
    570460: (1, 21, 22, 0, 39, 'eb0df2b00ad06497b6b284fbde8b0ce5cf63e180b1453076c7464f48bd5de5c5'),
    570499: (1, 21, 22, 0, 39, '91c568d4d92cea090395628a721988e9fe72555d5703bdfac27ee13088b6099c'),
    570539: (1, 21, 22, 0, 39, '6c74cb9f862387ca5c4aedd0fd155b537e94e6169682bda5b5a984e11a98cf61'),
    570637: (1, 21, 22, 0, 39, '15f4b0fa2f30842d3bfe6c69c62323ab28324241bda618a23e4b538526de3c11'),
    570701: (1, 21, 22, 0, 39, '720a980737826a5b0fe52c0efc8ef64ff51d3395be7bb5cb3264837050bc3482'),
    570744: (1, 21, 22, 0, 39, '8eaa24e538667bc7c9aa1e1e56abfddbebfe8a30dd243812eadd9d6460ace153'),
    580013: (1, 21, 22, 0, 39, '57292e6d744c0289c46d7ff876bd0848e6f14e4b0567032b037b9c295104cbf7'),
    580054: (1, 21, 22, 0, 39, 'ab26581044f8cda2f01b07973f4ff0a4c09bc09a0a500a7b9697c393927ee51c'),
    580096: (1, 21, 22, 0, 39, '873bf386b53623d2a1b236ef023bf76acf4c0a4c47ea04e99935d0d25f31fc42'),
    580182: (1, 21, 22, 0, 39, '6df94f86942a7070bbe3104a4202b30b4028a7c38dc436e511be20955c934b2b'),
    580221: (1, 21, 22, 0, 39, 'b1aefa14269d133113b36b3399a2c98ebccc204fb73d9fdbfcd9b477707d36c7'),
    717878: (1, 21, 22, 0, 39, '1f4ce986768adad52c5c60957a60fae4dee06df0933d3ee92d884e2b6f3203e8'),
    720859: (1, 21, 22, 0, 39, '20e34df4ef939f72357670a9df2fd84aa0a5c6f5379d7fa02ac65360cf04efa6'),
    135995: (1, 21, 22, 0, 39, 'e955937c4dfb0e8ab7cafb65cb848929414c19980c5a3d7871f0f2218d44bdb6'),
    135932: (1, 21, 22, 2, 41, '80fb401d6bf4abe0935e616ae14221622dba0e62743571b9109fae83d61043e5'),
    135930: (1, 21, 22, 1, 40, 'c5986ec8a3c7bd6716971ef11b759bfedc00b88dd5881273069807f86cef7ac7'),
    135928: (1, 21, 22, 0, 39, 'afca1f5b9f1883e32fa56037110bbb7db8acffd9c3cf7d902184bf7814c1cb2a'),
    135929: (1, 21, 22, 1, 40, '46de956a17a7eba6715a710340bda6224a92f4c4fbc4dc0aaecf4a9ecea7103b'),
    135931: (1, 21, 22, 2, 41, 'bec59846b619d5683b074c752c5dba3a191e087450d04d72b7a54ea99a4ceec5'),
    99809: (2, 3, 23, 0, 42, 'f3dfcfc91db553a431f8411e81427adc35cfe5e33c9b52e57bae86e1fb806742'),
    99810: (2, 3, 23, 0, 42, 'e0cd58115a780a22d4fe97ed871fcfb299b065aadcc3043ea23d8e5a59aa94c6'),
    135983: (2, 3, 23, 0, 42, '185c7351cff5bad87ba7da7812e5c0e3aec83b0e87e4940fe618032fa2b62175'),
    717879: (2, 3, 23, 0, 42, '4fbcd5fa14b17b06dfde1b3e84a775ce54128d45725c537b95914cace7a19124'),
}
WRITER_ENABLED = True


@functools.lru_cache(maxsize=len(ROWS))
def definition(template):
    if template not in ROWS:
        raise ValueError('Outside finite fishing equipment scope')
    from els_server.game_data import client_data
    metadata, bag, equipped, slot, key, pin = ROWS[template]
    row = client_data().item(template)
    enum = client_data().resource('Enum.lua')
    if (hashlib.sha256(row['record']).hexdigest() != pin
            or row['metadata'] != metadata or row['equip_position'] != key
            or row['item_type'] != (6 if equipped == 23 else 15)):
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
