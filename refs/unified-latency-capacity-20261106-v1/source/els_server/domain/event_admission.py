"""Ticket-only compatibility entry for three source-timed single-player maps."""
import json
import sqlite3
import struct
from contextlib import closing
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.domain.dungeon_clock import DungeonClock
from els_server.domain.inventory_items import inventory_payload, item_body, fixture
from els_server.storage.event_tickets import selected, admit


def eligible(account, identity):
    if account.store is None or account.character() is None:
        return False
    try:
        with closing(sqlite3.connect(account.store.path)) as db:
            selected(db, account.account_id, account.uid, identity)
        return True
    except (ValueError, sqlite3.Error):
        return False


def ticket_delta(before, after):
    if after is not None:
        vector = inventory_payload([after])
    else:
        body = bytearray(item_body(before))
        for field in fixture()['fields']:
            if int(field['offset'], 0) in (0, 5):
                struct.pack_into('>i', body, field['wire_offset'], 0)
        vector = struct.pack('>IQBh', 1, 0, before['group'], before['slot']) + body + bytes(9)
    return Event(0x201, kind=0xad8, payload=vector)


def start(session, identity, run_id, run, request, ack):
    s = session
    # Allocate every piece of run state before the commit. The only operation
    # after a successful transaction is installing this prepared state.
    state = dict(active_challenge=None, challenge_clear_effect=None, challenge_deadline=None,
        phase='dungeon_loading', dungeon_requested=False, dungeon_id=identity, dungeon_run=run,
        requested_dungeon_id=None, requested_dungeon_mode=None, requested_challenge=None,
        previous_dungeon_part=None, dungeon_clock=DungeonClock(), summon_next_key=16,
        summon_requests={}, summon_keys=set(), summon_deaths={}, dungeon_substage_synced=False,
        dungeon_end_payload=None, defeated_npcs={}, part_end_notified=False, gate_stage=0,
        gate_stage_loading=False, clear_notified=False, dungeon_failed=False,
        reward_run_id=run_id if s.reward_test else None, reward_receipt=None, clear_items_synced=False,
        world_drops={}, world_drop_issued=None, world_drop_sequence=910001, pickup_receipt=None)
    prepared = []
    try:
        from els_server.protocol.dungeon_messages import dungeon_start
        start_packet = dungeon_start(s.account.get_skills(), s.account.character(),
            s.account.get_inventory_snapshot()['items'] if s.item_test else None,
            dungeon_id=identity, account_id=s.account.account_id)
        success = ack(0)

        def encode(before, after):
            prepared[:] = [ticket_delta(before, after), success, start_packet]
            # Validate actual event serialization while a failure can roll back.
            for packet in prepared:
                encode_event(packet)
            return json.dumps([[p.kind, p.payload.hex()] for p in prepared], separators=(',', ':')).encode()

        response = admit(s.account.store.path, s.account.account_id, s.account.uid,
                         identity, run_id, request, encode)
        if not prepared:
            # This path only replays an existing receipt; it cannot debit again.
            prepared = [Event(0x201, kind=k, payload=bytes.fromhex(v)) for k, v in json.loads(response)]
    except (ValueError, sqlite3.Error):
        return [ack(-1)]
    s.__dict__.update(state)
    return prepared
