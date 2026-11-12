"""Four-template native104 moves using the unchanged wear_move_receipts schema."""
import hashlib
import json
import sqlite3
import struct
import uuid
from contextlib import closing
from els_server.domain.fishing_equipment import positions, definition
from els_server.domain.fashion_state import move_ack
from els_server.domain.inventory_items import validate_item
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.character_schema import character_uid


def move(path, payload, uid, *, account_id, session_id, sequence, expected_town,
         validate=lambda: None):
    uid = character_uid(uid)
    source, destination = positions(payload)
    if type(account_id) is not int or account_id <= 0 or type(session_id) is not str:
        raise ValueError('Fishing wear account/session')
    connection = uuid.UUID(session_id)
    if (connection.version != 4 or str(connection) != session_id
            or type(sequence) is not int or not 1 <= sequence < 2**32
            or type(expected_town) is not int):
        raise ValueError('Fishing wear operation')
    operation = session_id + ':life104:' + str(uid) + ':' + str(sequence)
    digest = hashlib.sha256(struct.pack('>Q', uid) + payload).hexdigest()
    position_json = json.dumps((source, destination), separators=(',', ':'))
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        require_active_character(db, uid)
        validate()
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?', (uid,)).fetchone() != (account_id,):
            raise ValueError('Fishing wear owner mismatch')
        character = db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?', (uid,)).fetchone()
        location = db.execute('SELECT town FROM location WHERE uid=?', (uid,)).fetchone()
        from els_server.game_data import client_data
        from els_server.storage.local_state import TOWN_SCENES
        if (character is None or client_data().unit(character[1])['unitType'] != character[0]
                or location != (expected_town,) or expected_town not in set(TOWN_SCENES) | {1500}):
            raise ValueError('Fishing wear saved actor/location')
        before = load_items(db, uid)
        by = {(i['group'], i['slot']): i for i in before}
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wear_move_receipts'").fetchone()
        old = db.execute('SELECT owner,account_id,request_hash,positions_json FROM wear_move_receipts WHERE operation_id=?',
                         (operation,)).fetchone() if exists else None
        if old is not None:
            if old != (uid, account_id, digest, position_json):
                raise ValueError('Fishing wear receipt conflict')
            response = move_ack([(source, by.get(source)), (destination, by.get(destination))])
            validate()
            return response
        from els_server.domain import fishing_equipment as rules
        if not rules.WRITER_ENABLED:
            raise ValueError('Fishing gear new writer held')
        if destination[0] in (22, 23) and (expected_town != 1500 or character[2] < 99):
            raise ValueError('Fishing wear finite1500/99 admission')
        from els_server.storage.bag_capacity import allowances
        limits = allowances(db, uid)
        if any(group in (3, 21) and slot >= limits[group] for group, slot in (source, destination)):
            raise ValueError('Fishing wear bag ownership')
        first, second = by.get(source), by.get(destination)
        if first is None:
            raise ValueError('Fishing wear source empty')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        for item in (first, second):
            if item is None:
                continue
            require_current(item)
            require_unlocked(item)
            rule = definition(item['template'])
            if (item.get('sealed', False)
                    or any(group not in (rule['bag'], rule['equipped']) for group, _ in (source, destination))):
                raise ValueError('Fishing wear item classification')
        moved = validate_item({**first, 'group': destination[0], 'slot': destination[1]})
        swapped = validate_item({**second, 'group': source[0], 'slot': source[1]}) if second else None
        response = move_ack([(source, swapped), (destination, moved)])
        validate()
        if not rules.WRITER_ENABLED:
            raise ValueError('Fishing gear writer held after response encoding')
        for item in (first, second):
            if item and db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',
                                   (-item['uid'], item['uid'], uid)).rowcount != 1:
                raise ValueError('Fishing wear retained owner')
        for item in (moved, swapped):
            if item and db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=? AND owner=?',
                                   (item['group'], item['slot'], item['uid'], uid)).rowcount != 1:
                raise ValueError('Fishing wear saved position')
        after = load_items(db, uid)
        expected = {i['uid']: i for i in before}
        expected.update({i['uid']: i for i in (moved, swapped) if i})
        if expected != {i['uid']: i for i in after}:
            raise ValueError('Fishing wear changed instance state')
        db.execute("CREATE TABLE IF NOT EXISTS wear_move_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL CHECK(length(request_hash)=64),positions_json TEXT NOT NULL)")
        db.execute('INSERT INTO wear_move_receipts VALUES (?,?,?,?,?)',
                   (operation, uid, account_id, digest, position_json))
        validate()
        if not rules.WRITER_ENABLED:
            raise ValueError('Fishing gear writer held before final commit')
        return response
