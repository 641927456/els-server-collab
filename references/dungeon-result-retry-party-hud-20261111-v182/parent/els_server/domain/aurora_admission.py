"""Preencoded original 382 solo admission, with free or owned-ticket plan."""
import json
import sqlite3
from contextlib import closing

from els_server.protocol.protocol_codec import Event, encode_event
from els_server.domain.native_ticket_admission import _delta
from els_server.storage.aurora_admissions import admit, eligible as storage_eligible


def eligible(account, dungeon):
    if account.store is None:
        return False
    try:
        return storage_eligible(account.store.path, account.account_id, account.uid, dungeon)
    except (ValueError, sqlite3.Error):
        return False


def start(s, dungeon, run_id, request, ack, inventory_before, room_id):
    from els_server.domain.equipment_chip_flow import current_lease
    bound = (s.account, s.account.store, s.account.account_id, s.account.uid,
             s.shop_session_id, s.requested_dungeon_id, s.requested_dungeon_mode,
             s.phase, s.dungeon_requested, getattr(s, 'application', None))

    def guard():
        if ((s.account, s.account.store, s.account.account_id, s.account.uid,
             s.shop_session_id, s.requested_dungeon_id, s.requested_dungeon_mode,
             s.phase, s.dungeon_requested, getattr(s, 'application', None)) != bound
                or s.phase != 'town_ready' or not s.dungeon_requested
                or s.requested_dungeon_id != dungeon or s.requested_dungeon_mode != 1
                or s.account.store is None or s.account.store.uid != s.account.uid
                or not current_lease(s)):
            raise ValueError('Aurora original solo actor or lease changed')

    prepared = []
    success = ack(0)

    def encode(plans):
        from els_server.protocol.dungeon_messages import dungeon_start
        item, after = plans[0]
        items = [dict(value) for value in inventory_before] if inventory_before is not None else None
        if item is not None:
            if items is None:
                raise ValueError('Aurora paid entry needs original inventory snapshot')
            positions = [i for i, value in enumerate(items) if value['uid'] == item['uid']]
            if (len(positions) != 1 or items[positions[0]]['template'] != item['template']
                    or items[positions[0]]['count'] != item['count']):
                raise ValueError('Aurora owned ticket inventory changed')
            if after is None:
                del items[positions[0]]
            else:
                items[positions[0]]['count'] = after['count']
        packet = dungeon_start(s.account.get_skills(), s.account.character(), items,
            dungeon_id=dungeon, room_id=room_id, account_id=s.account.account_id,
            bootstrap_port=s.port_probe_port, member_capture=s._capture_luciel_dungeon_hp)
        prepared[:] = ([_delta(item, after)] if item is not None else []) + [success, packet]
        for event in prepared:
            encode_event(event)
        return json.dumps([[event.kind, event.payload.hex()] for event in prepared],
                          separators=(',', ':')).encode()

    try:
        response = admit(s.account.store.path, ((s.account.account_id, s.account.uid),),
                         dungeon, run_id, request, encode, guard)
        if not prepared:
            prepared[:] = [Event(0x201, kind=kind, payload=bytes.fromhex(payload))
                           for kind, payload in json.loads(response)]
        return prepared
    except (ValueError, sqlite3.Error):
        return None
