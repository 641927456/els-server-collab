"""Owner-only ground marks in the final room of a settled raid encounter."""

from contextlib import closing
import hashlib
import sqlite3
import struct
import uuid

from els_server.domain.dungeon_drops import ground_drop_notice, ground_pickup_notice, pickup_inventory_notice
from els_server.domain.dungeon_lifecycle import death_report
from els_server.domain.raid_reward_items import _issue_source
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.storage.inventory_state import InventoryFull, load_items


POLICY = 'raid-final-room-mark-v1'
MARKS = frozenset((135914, 136056, 136116, 119317, 136151, 136152))


def issue(db, shadow, plan, guard):
    """Build the personal CF and its claim source on the original clear writer."""
    marks = [row for row in plan if row['template'] in MARKS]
    if not marks:
        return plan, []

    run = shadow.dungeon_run
    # Some final gates retire script controllers as well. Use an accepted
    # enemy death in the loaded room for the ground position.
    actors = {npc['key']: npc for npc in run.current['npcs'] if not npc.get('dynamic')
              and not npc.get('ally') and npc.get('team', 1) != 0}
    deaths = [(key, raw) for key, raw in reversed(tuple(run.defeated.items())) if key in actors]
    anchor = None
    for key, raw in sorted(deaths, key=lambda death: not actors[death[0]]['boss']):
        report = death_report(raw)
        if report['flag'] in (0, 1) and all(abs(axis) <= 1_000_000 for axis in report['xyz'][3:]):
            anchor = key, raw, report['xyz'][3:]
            break
    if anchor is None:
        # A scripted clear without an enemy position retains the settled
        # inventory delivery. There is no original room position for a CF.
        return plan, []

    key, raw, xyz = anchor
    owner = shadow.account.uid
    notices = []
    shadow.world_drops = dict(shadow.world_drops)
    for mark in marks:
        drop_id = shadow.world_drop_sequence
        shadow.world_drop_sequence += 1
        notice = ground_drop_notice(drop_id, xyz, uid=owner, template=mark['template'])
        operation = str(uuid.uuid5(uuid.UUID(shadow.reward_run_id), f'raid-ground:{drop_id}'))
        source = dict(reward_source=POLICY, owner=owner, run=shadow.reward_run_id,
                      source_run=run.run_id, dungeon=run.identity, stage=run.stage,
                      part=run.part, visits=run.visits, graph_sha256=run.graph['source_sha256'],
                      drop_id=drop_id, npc_key=key, death_sha256=hashlib.sha256(raw).hexdigest(),
                      payload_sha256=hashlib.sha256(notice.payload).hexdigest())
        _issue_source(db, owner, operation, 'phase', source, [mark], guard)
        drop = dict(source=POLICY, run_id=shadow.reward_run_id, stage=run.stage,
                    drop_id=drop_id, owner=owner, template=mark['template'], xyz=xyz,
                    operation=operation, authority=source, plan=mark, pickup_committed=False)
        shadow.world_drops[drop_id] = drop
        shadow.world_drop_issued = drop
        notices.append(notice)
    return [row for row in plan if row['template'] not in MARKS], notices


def claim(session, drop):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    from els_server.storage.profession_state import require_owner

    run = session.dungeon_run
    source = drop['authority']
    owner = session.account.uid

    def guard(db):
        if (not db.in_transaction or not current_lease(session) or not session.clear_notified
                or session.dungeon_failed or session.dungeon_run is not run
                or session.reward_run_id != source['run'] or session.world_drops.get(drop['drop_id']) is not drop
                or (run.identity, run.run_id, run.stage, run.part, run.visits, run.graph['source_sha256']) != (
                    source['dungeon'], source['source_run'], source['stage'], source['part'],
                    source['visits'], source['graph_sha256'])):
            raise ValueError('Raid mark pickup left its settled room')
        require_owner(db, owner, session.account.account_id)
        return True

    try:
        with closing(sqlite3.connect(session.account.reward_store.path, timeout=10)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            guard(db)
            if db.execute('SELECT 1 FROM raid_reward_sources WHERE operation_id=? AND owner=?',
                          (drop['operation'], owner)).fetchone() is None:
                raise ValueError('Raid mark pickup has no committed source')
            plan = [drop['plan']]
            capability = _issue_source(db, owner, drop['operation'], 'phase', source, plan, guard)
            proof = b'raid-ground-mark-v1\0' + uuid.UUID(drop['operation']).bytes + bytes.fromhex(source['payload_sha256'])
            receipt = session.account.reward_store.grant(
                drop['operation'], proof, 0, 0, item_plan=plan, transaction=db,
                raid_reward_source=capability, dungeon_drop=True,
                inventory_response_builder=lambda _, items: pickup_inventory_notice(items).payload)
            replies = [Event(0x201, kind=0xd1, payload=bytes(4))]
            if receipt['replayed']:
                awarded = {item['uid'] for item in receipt['items']}
                replies.append(pickup_inventory_notice([item for item in load_items(db, owner)
                                                        if item['uid'] in awarded]))
            else:
                replies.extend((ground_pickup_notice(drop['drop_id'], owner, template=drop['template']),
                                Event(0x201, kind=0xd3, payload=receipt['response'])))
            for reply in replies:
                encode_event(reply)
    except InventoryFull:
        return [Event(0x201, kind=0xd1, payload=struct.pack('>i', -1))]
    except (ValueError, sqlite3.Error):
        return []

    drop['pickup_committed'] = True
    session.pickup_receipt = dict(receipt, run_id=drop['operation'], dungeon_run_id=drop['run_id'],
                                  drop_id=drop['drop_id'])
    return replies
