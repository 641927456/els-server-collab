"""Optional, account-owned profession snapshots for native login restoration.

This module does not choose a profession, assign starting XP or grant crafting
benefits. The caller must supply a complete validated state inside its business
transaction once those rules are recovered.
"""
import json
from dataclasses import asdict
from els_server.protocol.profession_messages import ProfessionState, state_wire
from els_server.storage.character_schema import character_uid


def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_professions'").fetchone())


def require_owner(db, uid, account_id):
    character_uid(uid)
    if type(account_id) is not int or not 1 <= account_id < 2**63:
        raise ValueError('Profession account identity')
    if db.execute('SELECT 1 FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',
                  (uid, account_id)).fetchone() is None:
        raise ValueError('Profession character ownership')


def snapshot(db, uid, account_id):
    """Read without creating a table or changing legacy characters."""
    require_owner(db, uid, account_id)
    row = db.execute('SELECT profession,level,experience,counters,progress,required,revision FROM character_professions WHERE uid=?',
                     (uid,)).fetchone() if exists(db) else None
    if row is None:
        return dict(state=asdict(ProfessionState()), revision=0)
    pairs = json.loads(row[3])
    if (not isinstance(pairs, list) or len(pairs) > 512 or
        any(not isinstance(p, list) or len(p) != 2 or type(p[0]) is not int for p in pairs)):
        raise ValueError('Stored profession counter format')
    counters = dict(pairs)
    if len(counters) != len(pairs):
        raise ValueError('Duplicate stored profession counter')
    state = ProfessionState(row[0], row[1], row[2], counters, row[4], row[5])
    state_wire(state)
    if type(row[6]) is not int or not 1 <= row[6] < 2**63:
        raise ValueError('Stored profession revision')
    return dict(state=asdict(state), revision=row[6])


def replace(db, uid, account_id, expected_revision, state):
    """Internal CAS; caller owns transaction, authorization and business rules.

    Revision is never reset when state becomes empty, preventing stale updates
    from becoming valid again. Encoding is checked before any persistence.
    """
    if not db.in_transaction:
        raise ValueError('Profession update requires explicit transaction')
    if type(expected_revision) is not int or not 0 <= expected_revision < 2**63-1:
        raise ValueError('Profession revision')
    state_wire(state)
    old = snapshot(db, uid, account_id)
    if old['revision'] != expected_revision:
        raise ValueError('Stale profession state')
    saved = asdict(state)
    if old['state'] == saved:
        return old
    db.execute('''CREATE TABLE IF NOT EXISTS character_professions (
        uid INTEGER PRIMARY KEY REFERENCES characters(uid),
        profession INTEGER NOT NULL CHECK(profession BETWEEN 0 AND 3),
        level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 255),
        experience INTEGER NOT NULL CHECK(experience BETWEEN 0 AND 2147483647),
        counters TEXT NOT NULL,
        progress INTEGER NOT NULL CHECK(progress BETWEEN 0 AND 2147483647),
        required INTEGER NOT NULL CHECK(required BETWEEN 0 AND 2147483647),
        revision INTEGER NOT NULL CHECK(revision>0))''')
    revision = expected_revision+1
    db.execute('''INSERT INTO character_professions VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET profession=excluded.profession,
        level=excluded.level,experience=excluded.experience,counters=excluded.counters,
        progress=excluded.progress,required=excluded.required,revision=excluded.revision''',
        (uid, state.profession, state.level, state.experience,
         json.dumps(sorted(state.counters.items()), separators=(',', ':')),
         state.progress, state.required, revision))
    db.execute('UPDATE characters SET revision=revision+1 WHERE uid=?', (uid,))
    return dict(state=saved, revision=revision)
