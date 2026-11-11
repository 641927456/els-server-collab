"""Original 382 ordinary-dungeon admission response with an owned ticket debit."""
import json
import sqlite3
import struct
from contextlib import closing
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.domain.inventory_items import inventory_payload, item_body, fixture
from els_server.storage.native_dungeon_tickets import admit, selected


def eligible(account, dungeon_id):
    if account.store is None:
        return False
    try:
        with closing(sqlite3.connect(account.store.path)) as db:
            selected(db, account.account_id, account.uid, dungeon_id)
        return True
    except (ValueError, sqlite3.Error):
        return False


def _delta(before, after):
    if after is not None:
        payload = inventory_payload([after])
    else:
        body = bytearray(item_body(before))
        for field in fixture()['fields']:
            if int(field['offset'], 0) in (0, 5):
                struct.pack_into('>i', body, field['wire_offset'], 0)
        payload = struct.pack('>IQBh', 1, 0, before['group'], before['slot']) + body + bytes(9)
    return Event(0x201, kind=0xad8, payload=payload)


def start(session, dungeon_id, run_id, request, ack, inventory_before, room_id):
    s = session
    bound = (s.account, s.account.store, s.account.account_id, s.account.uid,
             s.shop_session_id, s.requested_dungeon_id, s.requested_dungeon_mode,
             s.phase, s.dungeon_requested, getattr(s, 'application', None))

    def guard():
        if ((s.account, s.account.store, s.account.account_id, s.account.uid,
             s.shop_session_id, s.requested_dungeon_id, s.requested_dungeon_mode,
             s.phase, s.dungeon_requested, getattr(s, 'application', None)) != bound
                or s.phase != 'town_ready' or not s.dungeon_requested
                or s.requested_dungeon_id != dungeon_id or s.requested_dungeon_mode != 1):
            raise ValueError('Permanent ticket original entry actor changed')

    prepared = []
    success = ack(0)

    def encode(before, after):
        from els_server.protocol.dungeon_messages import dungeon_start
        if inventory_before is None:
            raise ValueError('Permanent ticket admission requires native inventory sync')
        items = [dict(item) for item in inventory_before]
        indexes = [index for index, item in enumerate(items) if item['uid'] == before['uid']]
        if (len(indexes) != 1 or items[indexes[0]]['template'] != before['template']
                or items[indexes[0]]['count'] != before['count']):
            raise ValueError('Permanent ticket inventory changed before debit')
        index = indexes[0]
        if after is None:
            del items[index]
        else:
            items[index]['count'] = after['count']
        start_packet = dungeon_start(s.account.get_skills(), s.account.character(), items,
            dungeon_id=dungeon_id, room_id=room_id, account_id=s.account.account_id,
            bootstrap_port=s.port_probe_port, member_capture=s._capture_luciel_dungeon_hp)
        prepared[:] = [_delta(before, after), success, start_packet]
        for packet in prepared:
            encode_event(packet)
        return json.dumps([[p.kind, p.payload.hex()] for p in prepared], separators=(',', ':')).encode()

    try:
        response = admit(s.account.store.path, s.account.account_id, s.account.uid,
                         dungeon_id, run_id, request, encode, guard)
        if not prepared:
            prepared = [Event(0x201, kind=k, payload=bytes.fromhex(v)) for k, v in json.loads(response)]
        return prepared
    except (ValueError, sqlite3.Error):
        return None
