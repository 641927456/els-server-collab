"""Original results-screen admission using the completed run as its source."""
import uuid

from els_server.protocol.dungeon_errors import ENTRY_REQUIREMENTS_NOT_MET
from els_server.protocol.local_messages import i32, wstring
from els_server.protocol.protocol_codec import Event, encode_event

DCC_NOT_RETRY_DUNGEON = 14


def ack(result):
    # The native 652 reader consumes result, u64, and two wide strings.
    return Event(0x201, kind=0x652, payload=i32(result) + bytes(8) + wstring('') * 2)


def original_request(s, event):
    from els_server.domain.equipment_chip_flow import current_lease

    return (s.client_build == 'dx11_260923' and s.role == 'game' and s.enter_dungeon
            and event.performers in ((), (0,)) and event.uid == event.target_uid == 2**64 - 1
            and event.payload_mode == 0 and not event.payload and current_lease(s))


def cleared(s):
    return (s.phase == 'dungeon_active' and s.clear_notified and not s.dungeon_failed
            and not s.dungeon_return_pending and getattr(s, 'active_challenge', None) is None)


def route_allows_retry(identity):
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.henir_chaos_flow import DUNGEON as CHAOS_DUNGEON
    from els_server.game_data import client_data

    # CX2STXGameMatching skips enabling the retry action on this native flag.
    return (identity != CHAOS_DUNGEON and route_catalog().supports(identity)
            and DCC_NOT_RETRY_DUNGEON not in client_data().dungeon(identity).get('DUNGEON_CHECK_CONDITION', {}).values())


def request_identity(epoch):
    # Ticket receipts hash the real request kind and the result that authorized it.
    return b'\x06\x51' + uuid.UUID(epoch).bytes


def solo_entry_allowed(s, identity, challenge, *, retry=False):
    from els_server.domain.raid_native_power import allowed as native_power_allowed
    from els_server.domain.raid_party import entry_size
    from els_server.domain.region_quests import account_dungeon_allowed

    return (account_dungeon_allowed(s.account, identity)
            and (challenge is not None or entry_size(s, identity))
            and native_power_allowed(s, identity, retry=retry))


def solo(s, event, *, previous=None):
    failure = [ack(ENTRY_REQUIREMENTS_NOT_MET)]
    if not original_request(s, event) or not cleared(s):
        return failure
    app = getattr(s, 'application', None)
    world = app.world if app is not None else None
    party = world.party_of.get(s) if world is not None else getattr(s, 'solo_challenge_party', None)
    if party and not party.get('solo_challenge'):
        return failure
    if previous is None:
        if (world is not None and world.dungeons.room(s) is not None
            or s.dungeon_participants != frozenset((s.account.uid,))):
            return failure

    from els_server.domain.dungeon_hp_c1 import prepare_retry
    from els_server.domain.dungeon_routes import DungeonRun
    from els_server.domain.normal_fatigue_flow import admission_result
    from els_server.domain.daily_ticket_rules import MAPS as daily_ticket_maps
    from els_server.protocol.dungeon_messages import SUPPORTED_DUNGEON, dungeon_start

    identity = s.dungeon_id
    if not route_allows_retry(identity) or not solo_entry_allowed(s, identity, None, retry=True):
        return failure
    result = admission_result(s, identity, retry=True)
    if result:
        return [ack(result)]

    old_run, old_epoch = s.dungeon_run, s.reward_run_id
    actor = s.account, s.account.store, s.shop_session_id

    def guard():
        from els_server.domain.equipment_chip_flow import current_lease

        if (not cleared(s) or not current_lease(s) or actor != (s.account, s.account.store, s.shop_session_id)
            or s.dungeon_run is not old_run or s.dungeon_id != identity or s.reward_run_id != old_epoch
            or (world is not None and (world.party_of.get(s) is not party or world.dungeons.room(s) is not previous))):
            raise ValueError('The original retry result changed')

    run_id = str(uuid.uuid4())
    hp_context = prepare_retry(s, run_id)
    henir_mode=getattr(old_run,'henir_mode',1)
    run = DungeonRun(identity, run_id, hp_context=hp_context,henir_mode=henir_mode) if identity != SUPPORTED_DUNGEON else None
    from els_server.domain.silver_mirror_flow import admit as mirror_admit

    items = s.account.get_inventory_snapshot()['items'] if s.item_test else None
    room_id = party['id'] if party else 10001
    try:
        if identity in (35100, 35360) or identity in daily_ticket_maps:
            if identity in daily_ticket_maps:
                from els_server.domain.aurora_admission import start
            else:
                from els_server.domain.native_ticket_admission import start
            if hp_context is not None:
                hp_context.check(run)
            reply = start(s, identity, run_id, request_identity(old_run.run_id), ack, items, room_id, retry_guard=guard)
            if reply is None:
                return failure
        else:
            packet = dungeon_start(s.account.get_skills(), s.account.character(), items, dungeon_id=identity,
                room_id=room_id, account_id=s.account.account_id, bootstrap_port=s.port_probe_port,
                member_capture=s._capture_luciel_dungeon_hp, retry=True,henir_mode=henir_mode)
            encode_event(packet)
            reply = [ack(0), packet, *mirror_admit(s, run, retry_guard=guard)]
    except ValueError:
        return failure
    origin = getattr(s, 'village1012_return_origin', None)
    if origin is not None and (origin['dungeon'], origin['run_id']) == (identity, s.reward_run_id):
        origin = dict(origin, prior_run=s.reward_run_id)
    else:
        origin = None
    s._adopt_dungeon_start(identity, run, run_id, None, hp_context)
    if previous is not None:
        world.dungeons.finish_solo_retry(s, previous)
    if origin is not None:
        from els_server.domain.town_travel_flow import finish_village1012_origin
        finish_village1012_origin(s, origin)
    return reply
