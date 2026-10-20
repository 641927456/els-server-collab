"""Three original, non-persistent apple effects consumed by native 115.

The server admits the immutable inputs and charges the owned stack. The
client's AC effects and A8 BuffFactors own recovery, awakening and timers.
Elixirs have persistent/world Buffs and are deliberately outside this scope.
"""
import functools
import hashlib
import json
import struct

from els_server.game_data import CLIENT_SHA, client_data
from els_server.paths import PROJECT_ROOT


@functools.lru_cache(maxsize=1)
def catalog():
    path = PROJECT_ROOT / 'els_server/data/apple_consumables.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '003dc80a49299909b4aced47a19ef28e5480d61891715bc9957a418e2e1ae3e8':
        raise ValueError('Apple source identity')
    source = json.loads(raw)
    if (source['client_sha256'] != CLIENT_SHA
            or source['catalog_sha256'] != client_data().manifest['catalog_sha256']):
        raise ValueError('Apple client version')
    definitions = {r['template']: r for r in source['definitions']}
    native = {r['template']: r for r in source['native_rows']}
    effects = source['item_effects']
    if set(definitions) != {710313, 710314, 710315} or set(native) != set(definitions):
        raise ValueError('Apple finite admission')
    expected = {
        710313: (58065274, ()),
        710314: (0, ((19, 0, 50, 0, 0, 0), (13, 0, 50, 0, 0, 0), (24, 0, 20, 0, 0, 0))),
        710315: (58065356, ((3, 0, 0, 0, 0, 0), (5, 0, 0, 0, 0, 0),
                            (6, 0, 0, 0, 0, 0), (23, 0, 10, 45, 0, 0))),
    }
    for template, row in definitions.items():
        item = client_data().item(template)
        proof = native[template]
        meta = effects[str(template)]
        record = item['record']
        if (row['record_sha256'] != hashlib.sha256(record).hexdigest()
                or proof['record_sha256'] != row['record_sha256']
                or item['name'] != row['name'] or item['metadata'] != row['metadata']
                or item['item_type'] != 5 or row['metadata'] != 2
                or row['group'] != 6 or proof['native_group'] != 6 or row['max_stack'] != 99
                or bytes.fromhex(meta['record_hex']) != record
                or record[0xd1] != (40 if template == 710313 else 50)
                or struct.unpack_from('<I', record, 0xa8)[0] != expected[template][0]
                or (meta['cooldown_group'], meta['cooldown_seconds']) != (10, 30)
                or meta['effects'] != [struct.pack('<6I', *r).hex() for r in expected[template][1]]
                or [(c['count'], c['ok'], c['consumed'], c['template'], c['metadata'])
                    for c in proof['cases']] != [(n, 1, 304, template, 2) for n in (1, 99)]):
            raise ValueError('Apple original inventory/effect definition')
    return source


def inventory_definitions():
    return catalog()['definitions']


def usable(template):
    if type(template) is not int or template not in (710313, 710314, 710315):
        raise ValueError('Unsupported apple')
    from els_server.domain.consumables import catalog as consumable_catalog
    source = catalog()['item_effects'][str(template)]
    current = consumable_catalog()[template]
    if current != source:
        raise ValueError('Apple consumable metadata changed')
    return current


def native_stage_ready(session):
    if session.phase != 'dungeon_active' or not session.dungeon_substage_synced:
        return False
    application = getattr(session, 'application', None)
    if application is None:
        return True
    dispatcher = application.world.dungeons
    room = dispatcher.room(session)
    return (room is not None and room.phase == 'active'
            and all(not p.released and dispatcher.room(p) is room
                    and p.phase == 'dungeon_active' and p.dungeon_substage_synced
                    for p in room.members))


def relay_committed_use(session, replies):
    """Peers consume the same native effect once; never their inventory ACK."""
    notices = [e for e in replies if e.event_id == 0x201 and e.kind == 0x115
               and len(e.payload) == 22
               and struct.unpack_from('>Qi', e.payload) in
               {(session.account.uid, t) for t in (710313, 710314, 710315)}]
    if not notices or session.phase != 'dungeon_active':
        return
    dispatcher = session.application.world.dungeons
    room = dispatcher.room(session)
    if room is None or room.phase != 'active':
        return
    for peer in room.members:
        if (peer is not session and not peer.released
                and dispatcher.room(peer) is room and peer.phase == 'dungeon_active'
                and peer.dungeon_substage_synced):
            dispatcher.send(peer, notices)
