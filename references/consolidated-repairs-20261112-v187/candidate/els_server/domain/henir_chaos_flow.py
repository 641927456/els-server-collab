"""Solo Chaos admission, checkpointed stages, and the original reward picker."""
import copy
import json
import sqlite3

from els_server.protocol import henir_chaos_messages as wire
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.storage import henir_chaos as store


DUNGEON = 35870
POLICY = 'henir-chaos-weekly-cn-20261112'
GRAPH_SHA = '44b861d871931c20d4a8e3e8c6bc13c28cbdeb16daf9673cdd2a59d0e39d5bbc'
BOX_POS = (3.96143, 2000, 0)  # Henir_Space_Chaos_Linemap.lua, NPC start point 2.
SELECT_POWER = (0, 1_100_000, 1_400_000, 2_200_000)


def rewards(grade):
    return 62217 + grade, tuple(62222 + grade + 5 * i for i in range(4))


def _lease(session, run):
    from els_server.domain.equipment_chip_flow import current_lease
    uid = session.account.uid
    return (session.role == 'game' and current_lease(session) and session.dungeon_run is run
            and session.phase == 'dungeon_active' and session.dungeon_substage_synced
            and not session.dungeon_failed and not session.dungeon_return_pending
            and session.reward_run_id == run.run_id and session.dungeon_participants == frozenset((uid,))
            and run.chaos.owner == uid)


def admit(session, run):
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.domain.raid_native_power import basis

    account = session.account
    report = getattr(session, '_raid_native_power', None)
    if (not current_lease(session) or report is None or report[0] != basis(session)
            or account.character_identity()['level'] != 99 or report[1] < 270_000):
        raise ValueError('Chaos admission combat power or actor')

    def prepare(progress):
        if not current_lease(session):
            raise ValueError('Chaos admission actor changed')
        run.configure_chaos(progress)
        event = wire.progress(progress)
        encode_event(event)
        encode_event(run.population_event())
        return [event]

    return store.admit(account.store.path, account.uid, account.account_id, prepare)


def transition(session, run):
    if not _lease(session, run) or not session.part_end_notified or session.clear_notified or not run.poll_ready():
        raise ValueError('Chaos checkpoint requires the original completed stage')
    account = session.account
    prepared = copy.copy(run)
    prepared.completed_stages = set(run.completed_stages)
    prepared.stage_wires = dict(run.stage_wires)
    source_part = run.part

    def prepare(progress, delta):
        prepared.advance()
        if prepared.stage != progress.stages[progress.cursor]:
            raise ValueError('Chaos prepared stage does not match checkpoint')
        prepared.chaos = progress
        prepared.completed_transition = dict(target=(prepared.stage, prepared.part, prepared.visits),
                                             parts=(bytes((source_part,)),))
        messages = [wire.grade(progress.grade, delta), wire.progress(progress), prepared.population_event()]
        for message in messages:
            encode_event(message)
        if not _lease(session, run):
            raise ValueError('Chaos checkpoint actor changed')
        return messages

    _, messages = store.advance(account.store.path, account.uid, account.account_id, run.chaos, prepare)
    run.__dict__.update(prepared.__dict__)
    session.previous_dungeon_part = source_part
    session.gate_stage = run.stage
    session.part_end_notified = False
    session.defeated_npcs = run.defeated
    session.dungeon_substage_synced = False
    session.gate_stage_loading = True
    return messages


def select(session, event, run):
    from els_server.domain.dungeon_drops import ground_drop_notice

    refused = [wire.selected(2)]
    try:
        if (not _lease(session, run) or run.stage != store.REWARD_STAGE or session.clear_notified
                or event.performers not in ((), (0,)) or event.uid != event.target_uid
                or event.uid != 2**64-1 or event.payload_mode != 0):
            return refused
        account = session.account
        template, reported_power = wire.request(event.payload, account.uid)
        state = run.chaos
        if state.selected:
            return [wire.selected(0)] if state.selected == template else refused
        fixed, options = rewards(state.grade)
        if template not in options:
            return refused
        if reported_power is not None:
            if run.chaos_reward_power is not None and run.chaos_reward_power != reported_power:
                return refused
            run.chaos_reward_power = reported_power
        required = SELECT_POWER[options.index(template)]
        if required and (reported_power is None or reported_power < required):
            return refused

        def prepare(db,saved,now):
            messages = [wire.selected(0)]
            drops = []
            for index, reward in enumerate((fixed, saved.selected)):
                key = session.world_drop_sequence + index
                if key in session.world_drops:
                    raise ValueError('Chaos duplicate ground identity')
                messages.append(ground_drop_notice(key, BOX_POS, uid=account.uid, template=reward))
                drops.append(dict(drop_id=key, template=reward, run_id=run.run_id, owner=account.uid,
                                  stage=run.stage, xyz=BOX_POS, quantity=1, source=POLICY,
                                  pickup_committed=False))
            from els_server.storage.ariel_daily_special import notification
            messages.append(notification(db,account.account_id,account.uid,now))
            for message in messages:
                encode_event(message)
            if not _lease(session, run):
                raise ValueError('Chaos selection actor changed')
            return messages, drops

        saved, messages, drops = store.select(account.store.path, account.uid, account.account_id, state, template, prepare)
        run.chaos = saved
        session.world_drops.update((drop['drop_id'], drop) for drop in drops)
        session.world_drop_sequence += len(drops)
        return messages
    except (ValueError, sqlite3.Error):
        return refused


def reset_ticket(session,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219 or session.phase!='town_ready' or len(event.payload)<8:
        return None
    account=session.account
    if account.store is None or not session.item_test or session.client_build!='dx11_260923':
        return None
    from contextlib import closing
    import struct
    item_uid,=struct.unpack_from('>Q',event.payload)
    if not 0<item_uid<2**63:return None
    operation=f'henir-chaos-reset:{session.shop_session_id}:{account.uid}:{sequence}'
    path=account.store.path
    with closing(sqlite3.connect(path,timeout=10)) as db:
        row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(account.uid,item_uid)).fetchone()
        recognized=row is not None and row[0] in store.RESET_TICKETS
        if not recognized and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():
            recognized=db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=?',
                                  (operation,account.uid,0x219)).fetchone() is not None
    if not recognized:return None

    from els_server.domain.equipment_chip_flow import reset_authority
    from els_server.domain.raid_reward_flow import town
    from els_server.domain.region_quests import account_dungeon_allowed
    from els_server.protocol.career_messages import use_ack
    try:
        if (type(sequence)is not int or event.performers not in ((),(0,)) or event.uid!=event.target_uid
                or event.uid!=2**64-1 or event.payload_mode!=0):
            raise ValueError('Chaos reset original owned envelope')
        bound=town(session,sequence)
        if not account_dungeon_allowed(account,DUNGEON):
            raise ValueError('Chaos reset requires unlocked dungeon')

        def guard():
            reset_authority(session)
            if town(session,sequence)!=bound or not {0x28,0x225,0x227}<=session.completed:
                raise ValueError('Chaos reset current town authority')
        return store.reset(path,account.uid,account.account_id,event.payload,operation,guard)
    except (ValueError,sqlite3.Error):
        return [use_ack(result=500)]


def pickup(session, drop):
    from els_server.domain.dungeon_drops import ground_pickup_notice, pickup_inventory_notice
    from els_server.storage.inventory_state import InventoryFull

    run = session.dungeon_run
    account = session.account

    def guard():
        return (_lease(session, run) and run.stage == store.REWARD_STAGE
                and session.world_drops.get(drop['drop_id']) is drop)

    def prepare(grants):
        events = [Event(0x201, kind=0xd1, payload=bytes(4))]
        if grants:
            events += [ground_pickup_notice(drop['drop_id'], account.uid, template=drop['template']),
                       pickup_inventory_notice(grants)]
        for event in events:
            encode_event(event)
        return events

    try:
        events = store.pickup(account.store.path, account.uid, account.account_id, run.chaos, drop, guard, prepare)
    except InventoryFull:
        return [Event(0x201, kind=0xd1, payload=b'\xff'*4)]
    except (ValueError, sqlite3.Error):
        return []
    drop['pickup_committed'] = True
    return events


def authorize_output(template, source):
    if source is None or not 62218 <= template <= 62242:
        return False
    from els_server.domain.raid_reward_items import validate_source
    source = validate_source(source)
    identity = json.loads(source._source)
    if identity.get('policy') != POLICY or identity.get('template') != template or source.kind != 'ordinary':
        return False
    source.validate_template(template)
    return True
