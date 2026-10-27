"""Original ready-room 382: prepare every Aurora member before one DB commit."""
import json
import sqlite3
import time
import uuid
from pathlib import Path

from els_server.protocol.protocol_codec import Event, encode_event
from els_server.protocol.local_messages import wstring
from els_server.protocol.dungeon_messages import party_dungeon_start
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.native_ticket_admission import _delta
from els_server.storage.aurora_admissions import admit
from els_server.domain.equipment_chip_flow import current_lease


def start(dispatcher, party, leader, dungeon, event):
    from els_server.domain.friends_dungeon import Room
    from els_server.domain.local_session import LocalSession
    members = tuple(party['members'])
    if (party['leader'] is not leader or not 2 <= len(members) <= 4
            or len(set(members)) != len(members)
            or any(not s.item_test or s.account.store is None for s in members)):
        return False
    paths = {Path(s.account.store.path).resolve() for s in members}
    if len(paths) != 1:
        return False
    path = paths.pop()
    actors = tuple((s.account.account_id, s.account.uid) for s in members)
    selection = (tuple(members), frozenset(party['ready']), party.get('dungeon'), party.get('run'))
    seed = str(uuid.uuid4())
    snapshots = {s: dict(s.__dict__) for s in members}
    runs = {s: DungeonRun(dungeon, seed, internal=False) for s in members}
    participants = frozenset(s.account.uid for s in members)
    room = Room(party, members, leader, dungeon, seed, deadline=time.monotonic() + 90)
    prepared = {}

    def guard():
        if (selection != (tuple(party['members']), frozenset(party['ready']),
                          party.get('dungeon'), party.get('run'))
                or any(not current_lease(s) or s.account.store is None
                       or s.account.store.uid != s.account.uid
                       or Path(s.account.store.path).resolve() != path for s in members)):
            raise ValueError('Aurora party roster, lease or DB changed')
        if not prepared:
            if not dispatcher.admissible(party, leader, dungeon):
                raise ValueError('Aurora original ready party changed')
        elif any(s.phase != 'dungeon_loading' or s.dungeon_run is None
                 or s.dungeon_run.run_id != seed for s in members):
            raise ValueError('Aurora prepared party memory changed')

    def encode(plans):
        inventories = {}
        deltas = {}
        for s, (item, after) in zip(members, plans):
            inventory = [dict(value) for value in s.account.get_inventory_snapshot()['items']]
            if item is not None:
                positions = [i for i, value in enumerate(inventory) if value['uid'] == item['uid']]
                if (len(positions) != 1 or inventory[positions[0]]['template'] != item['template']
                        or inventory[positions[0]]['count'] != item['count']):
                    raise ValueError('Aurora party owned ticket inventory changed')
                if after is None:
                    del inventory[positions[0]]
                else:
                    inventory[positions[0]]['count'] = after['count']
                deltas[s] = _delta(item, after)
            inventories[s] = inventory
        captured = {}
        packet = party_dungeon_start(members, leader, dungeon, party['id'],
            bootstrap_port=leader.port_probe_port, member_captures=captured,
            inventories=inventories)
        ack = Event(0x201, kind=0x383, payload=bytes(4) + wstring('') * 2)
        for wire in [packet, ack, *deltas.values()]:
            encode_event(wire)
        for s in members:
            s._native_group_ticket_prepare = True
            s.dungeon_requested = True
            s.requested_dungeon_id = dungeon
            s.requested_dungeon_mode = 1
            result = LocalSession.handle(s, event)
            if not any(reply.kind == 0x14a for reply in result):
                raise ValueError('Aurora party member admission changed')
            s._capture_luciel_dungeon_hp(*captured[s])
            s.dungeon_run = runs[s]
            s.reward_run_id = str(uuid.uuid5(uuid.UUID(seed), 'reward:' + str(s.account.uid))) if s.reward_test else None
            s.dungeon_participants = participants
            from els_server.domain.pve_economy_flow import bind_story
            bind_story(s)
            from els_server.domain.normal_fatigue_flow import bind as bind_normal_fatigue
            bind_normal_fatigue(s, epoch=seed)
            del s._native_group_ticket_prepare
        prepared.update(packet=packet, deltas=deltas)
        return json.dumps(dict(packet=packet.payload.hex(),
            deltas={str(s.account.uid):deltas[s].payload.hex() for s in deltas}),
            separators=(',', ':')).encode()

    try:
        admit(path, actors, dungeon, seed, event.payload, encode, guard)
    except Exception:
        for s, snapshot in snapshots.items():
            s.__dict__.clear()
            s.__dict__.update(snapshot)
        return False
    for s in members:
        dispatcher.rooms[s] = room
        dispatcher.world.synchronize(s)
        if s in prepared['deltas']:
            dispatcher.send(s, [prepared['deltas'][s], prepared['packet']])
        else:
            dispatcher.send(s, [prepared['packet']])
    from els_server.domain.friends_spawns import capture_static_origin
    capture_static_origin(room)
    party.pop('admission', None)
    party['run'] = room
    party['dungeon'] = dungeon
    return True
