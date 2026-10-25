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


def _normal_solo_stage_ready(session,application):
    """Use the committed original solo actor; never manufacture a shared room."""
    from pathlib import Path
    import math,uuid
    from els_server.application import Application,FriendsSession
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.domain.dungeon_clock import DungeonClock
    from els_server.domain.dungeon_routes import DungeonRun,route_catalog
    from els_server.domain.event_dungeons import is_reviewed
    from els_server.domain.raid_party import raid_definition
    try:
        a=session.account;world=application.world
        if (type(application) is not Application or type(session) is not FriendsSession
            or application.config.mode!='friends' or session.role!='game'
            or session.client_build!='dx11_260923' or not session.item_test
            or not current_lease(session) or not application.registry.enabled(a.account_id)
            or Path(a.store.path).resolve()!=Path(application.config.state_file).resolve()
            or session.social_overflow or session.coop_error or session in world.party_of or session in world.members
            or world.dungeons.transport_room(session) is not None
            or not session.enter_dungeon or not session.population_test
            or session.phase!='dungeon_active' or not session.dungeon_substage_synced
            or session.gate_stage_loading or session.dungeon_return_pending
            or session.clear_notified or session.dungeon_failed or session.part_end_notified
            or session.reward_receipt is not None or session.dungeon_end_payload is not None
            or getattr(session,'active_challenge',None) is not None
            or getattr(session,'challenge_deadline',None) is not None
            or getattr(session,'solo_challenge_party',None) is not None
            or session.dungeon_requested or session.requested_dungeon_id is not None or session.requested_dungeon_mode is not None
            or session.dungeon_participants!=frozenset((a.uid,))):return False
        clock=session.dungeon_clock
        if type(clock) is not DungeonClock or type(clock.started) not in (int,float) or not math.isfinite(clock.started) or clock.started<0:return False
        identity=session.dungeon_id;catalog=route_catalog()
        if type(identity) is not int or str(identity) not in catalog._data['routes']:return False
        from els_server.game_data import client_data
        d=client_data().dungeon(identity)
        original=client_data().dungeon(d['OriginalModeDungeonID']) if d.get('OriginalModeDungeonID') else {}
        if (is_reviewed(identity) or raid_definition(identity) is not None or d.get('m_eDungeonType') not in (None,1)
            or original.get('m_eDungeonType') in (2,3,4,5,6,7) or d.get('m_bRelativeMonsterLevel') or d.get('m_bArcadeMode') or d.get('IS_HELL_MODE')
            or str(d.get('m_PieceName','')).upper().startswith(('SPECIAL_','CHALLENGE_','SECRET_','PVP_','GUILD_','HENIR_'))
            or max(d.get('m_MinPlayerCount',1),d.get('MinAdequateMemberCount',1))>1):return False
        run=session.dungeon_run
        if run is None:
            # Legacy30000 has no DungeonRun. Its admission UUID is retained
            # only with the original reward-enabled profile; unknown stays shut.
            if identity!=30000 or not session.reward_test or type(session.gate_stage) is not int or session.gate_stage not in range(3):return False
            epoch=session.reward_run_id
        else:
            if (type(run) is not DungeonRun or run.identity!=identity or run.stage!=session.gate_stage
                or run.catalog is not catalog or run.encounter is not None
                or run.graph['source_sha256']!=catalog.graph(identity)['source_sha256']
                or type(run.part) is not int or run.part not in run.parts
                or type(run.started_at) not in (int,float) or not math.isfinite(run.started_at) or run.started_at<0
                or session.reward_test and session.reward_run_id!=run.run_id):return False
            epoch=run.run_id
        parsed=uuid.UUID(epoch)
        return parsed.version==4 and str(parsed)==epoch
    except (AttributeError,KeyError,TypeError,ValueError):return False


def native_stage_ready(session):
    if session.phase != 'dungeon_active' or not session.dungeon_substage_synced:
        return False
    application = getattr(session, 'application', None)
    if application is None:
        return True
    dispatcher = application.world.dungeons
    room = dispatcher.room(session)
    if room is None:
        return _normal_solo_stage_ready(session,application)
    return (room is not None and room.phase == 'active'
            and all(not p.released and dispatcher.room(p) is room
                    and p.phase == 'dungeon_active' and p.dungeon_substage_synced
                    for p in room.members))


def relay_committed_use(session, replies):
    """Peers consume the same native effect once; never their inventory ACK."""
    from els_server.domain.consumable_extensions import quick_templates
    notices = [e for e in replies if e.event_id == 0x201 and e.kind == 0x115
               and len(e.payload) == 22
               and struct.unpack_from('>Qi', e.payload) in
               {(session.account.uid, t) for t in ({710313,710314,710315,77110,130467,710193,723674}|quick_templates())}]
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
