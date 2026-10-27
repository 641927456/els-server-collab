"""One owned SQL snapshot for authoritative native attribute production.

No data value is borrowed from session projection caches or a second database
connection. The read transaction ends before expensive arithmetic or encoding.
This is source acquisition; it does not assign a combat total or send packets.
"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sqlite3


def read_in_transaction(db, owner, account_id):
    from els_server.storage.character_schema import character_uid
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.seal_quests import load_character, current_slots
    from els_server.storage.inventory_state import load_items
    from els_server.domain.character_rules import validate_career_state
    owner=character_uid(owner)
    if type(account_id) is not int or not 0<account_id<2**63:
        raise ValueError('Native attribute account identity')
    if not db.in_transaction:
        raise ValueError('Native attribute source requires caller snapshot')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account_id,):
        raise ValueError('Native attribute source ownership changed')
    require_active_character(db,owner)
    character=load_character(db,owner,account_id)
    validate_career_state(character)
    items=tuple(load_items(db,owner))
    slots=tuple(current_slots(db,character))
    if character['uid']!=owner:
        raise ValueError('Native attribute source identity changed')
    # load_character's existing helpers include current title/qualification,
    # artifact, force ownership/presets, learned seals, collection, guild and
    # resonance. All attached item instances come from the very same db.
    value=dict(owner=owner,account_id=account_id,character=character,
               items=items,ordinary_slots=slots)
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
    return dict(deepcopy(value),source_sha256=hashlib.sha256(raw).hexdigest())


def capture(path, owner, account_id):
    path=Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,
                               isolation_level=None,timeout=10)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        try:
            return read_in_transaction(db,owner,account_id)
        finally:
            db.rollback()
