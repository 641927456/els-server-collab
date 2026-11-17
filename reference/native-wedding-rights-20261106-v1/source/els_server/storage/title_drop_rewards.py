"""Freeze the approved newlywed title's drop effect in the original draw writer."""
import hashlib
import json
import time
from els_server.storage import titles

TABLE = 'title_drop_reward_facts'
POLICY = 'human-newlywed-drop20-20261106-v1'


def present(db, operation):
    return bool(titles.exists(db, TABLE) and db.execute(
        'SELECT 1 FROM title_drop_reward_facts WHERE operation=?', (operation,)).fetchone())


def bonus(db, owner, dungeon, operation, context, *, already_issued=False, now=None):
    if not db.in_transaction:
        raise ValueError('Title drop requires the original reward writer')
    digest = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    old = db.execute('''SELECT owner,dungeon,context_hash,title,basis_points,
        created_at,expires_at,policy FROM title_drop_reward_facts WHERE operation=?''',
        (operation,)).fetchone() if titles.exists(db, TABLE) else None
    if old is not None:
        if old[:3] != (owner, dungeon, digest) or old[3] not in (0, 12360) or old[7] != POLICY:
            raise ValueError('Conflicting title drop receipt')
        if old[4] != (2000 if old[3] else 0) or old[3] and old[6] and old[5] >= old[6]:
            raise ValueError('Title drop source amount or lifetime')
        return old[4]
    from els_server.domain.el_search_effects import eligible
    if already_issued or not eligible(dungeon):
        return 0
    when = int(time.time()) if now is None else now
    character = titles.character(db, owner)
    active = titles.equipped(db, owner, when)
    selected = active if active == 12360 else 0
    end = next((row['expires_at'] for row in titles.owned(db, character, when)
                if row['title'] == selected), 0)
    amount = 2000 if selected else 0
    # A zero fact also freezes absence: equipping a title later cannot alter
    # a draw whose other effect sources happened to contribute zero.
    db.execute('''CREATE TABLE IF NOT EXISTS title_drop_reward_facts(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),
        dungeon INTEGER NOT NULL,context_hash TEXT NOT NULL,title INTEGER NOT NULL,
        basis_points INTEGER NOT NULL,created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,policy TEXT NOT NULL)''')
    db.execute('INSERT INTO title_drop_reward_facts VALUES(?,?,?,?,?,?,?,?,?)',
               (operation, owner, dungeon, digest, selected, amount, when, end, POLICY))
    return amount
