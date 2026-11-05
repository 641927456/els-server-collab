"""Exact owned100black fragments to one selected singleton, atomic with receipt."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import time
from els_server.domain.cartridge_exchange_rules import request, plain_source, SOURCE, _SelectSource
from els_server.domain.manufacture_requirements import inventory_candidates
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.protocol.purifier_exchange_messages import acknowledgement
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances
from els_server.storage.seal_quests import load_character, completed_ids
from els_server.storage.character_lifecycle import states

WRITER_ENABLED = True


def _context(db, owner, account_id, authorize):
    if not callable(authorize) or authorize() is not True:
        raise ValueError('Cartridge exchange obsolete context')
    character = load_character(db, owner, account_id=account_id)
    state = states(db, (owner,)).get(owner)
    if state and (state['account_id'] != account_id or state['finalized_at']):
        raise ValueError('Cartridge exchange unavailable actor')
    if character['level'] != 99 or 27600 not in completed_ids(db, owner):
        raise ValueError('Cartridge exchange town qualification')
    location = db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',
                          (owner,)).fetchone()
    if location is None or location[0] != 1012:
        raise ValueError('Cartridge exchange saved town mismatch')
    from els_server.storage.local_state import validate_location, TOWN_SCENES
    if TOWN_SCENES.get(1012) != 1214:
        raise ValueError('Cartridge exchange town dependency is absent')
    validate_location(location[0], location[1], location[2], tuple(location[3:6]))


def exchange(path, owner, payload, operation, *, account_id, authorize, now=None):
    if not WRITER_ENABLED:
        raise ValueError('Cartridge exchange writer is closed')
    value = request(payload)
    if type(account_id) is not int or not 1 <= account_id < 2**63:
        raise ValueError('Cartridge exchange account identity')
    if now is None:
        now = int(time.time())
    if type(now) is not int or now < 0:
        raise ValueError('Cartridge exchange clock')
    owner, digest = _identity(owner, 0x223, struct.pack('>iQ', 1012, account_id) + payload, operation)
    uri = Path(path).resolve().as_uri() + '?mode=rw'
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        _context(db, owner, account_id, authorize)
        balance = validate_balances(db.execute(
            'SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (owner,)).fetchone())
        previous = _previous(db, operation, digest)
        before = load_items(db, owner)
        if previous is not None:
            changes = current_changes(db, operation, owner, 0x223, previous, before)
            response = [Event(0x201, kind=0x224,
                              payload=acknowledgement(balance['ed'], changes))]
            for event in response:
                encode_event(event)
            return response
        by_uid = {item['uid']: item for item in before}
        available = inventory_candidates(before, now=now).get(SOURCE, ())
        candidates = [(uid, count) for uid, count in available if plain_source(by_uid[uid])]
        if sum(count for _, count in candidates) < 100:
            raise ValueError('Insufficient current plain black fragments')
        source = _SelectSource(db, owner, account_id, payload, operation, authorize)
        remaining, positions, debits = 100, [], []
        for uid, count in sorted(candidates, key=lambda pair: (by_uid[pair[0]]['group'], by_uid[pair[0]]['slot'])):
            if not remaining:
                break
            item = by_uid[uid]
            take = min(count, remaining)
            debits.append((uid, take))
            remaining -= take
            positions.append((item['group'], item['slot']))
            if take == count:
                remove(db, owner, item)
            elif db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=? AND count=?',
                            (take, uid, owner, count)).rowcount != 1:
                raise ValueError('Cartridge exchange source changed')
        source.debit_complete(debits)
        try:
            granted = grant_items(db, [dict(template=value.destination, metadata=0,
                                           group=4, quantity=1)], owner, cartridge_select_source=source)
        finally:
            source.close()
        if (len(granted) != 1 or set(granted[0]) != {'uid','template','metadata','group','slot','count'}
                or (granted[0]['template'], granted[0]['metadata'], granted[0]['group'],
                    granted[0]['count']) != (value.destination, 0, 4, 1)
                or granted[0]['uid'] in by_uid):
            raise ValueError('Cartridge exchange singleton factory mismatch')
        positions = list(dict.fromkeys(positions + [(i['group'], i['slot']) for i in granted]))
        after = load_items(db, owner)
        current = {(item['group'], item['slot']): item for item in after}
        changes = [(position, current.get(position)) for position in positions]
        wire = acknowledgement(balance['ed'], changes, [(value.destination, 1)])
        response = [Event(0x201, kind=0x224, payload=wire)]
        for event in response:
            encode_event(event)
        _commit(db, operation, digest, owner, 0x223, positions, before, after)
        return response
