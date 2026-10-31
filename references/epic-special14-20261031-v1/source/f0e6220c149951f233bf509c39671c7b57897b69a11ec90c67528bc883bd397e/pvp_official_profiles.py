"""Finite real-player official registration profiles and immutable receipts.

Read paths never create schema or adopt unknown historic profiles. Lazy schema
and the approved fresh profile are created only by the normal authenticated
342 writer, with its live admission guard and complete precommit response.
This leaf does not manufacture a match, death, reward, or quest completion.
"""
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import sqlite3
from els_server.domain.pvp_official_1v1_policy import Profile, POLICY
from els_server.protocol.pvp_match_messages import registration
from els_server.protocol.protocol_codec import encode_event, decode_event
from els_server.storage.item_actor import require_active_character

WRITER_ENABLED = True
TABLES = ('official_pvp_profiles', 'official_pvp_registrations')
OWNED_TABLES = TABLES + ('official_pvp_results',)


def _exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                      (name,)).fetchone() is not None


def _owner(db, uid, account_id):
    if any(type(n) is not int or not 1 <= n < 2**63 for n in (uid, account_id)):
        raise ValueError('PvP saved identity')
    require_active_character(db, uid)
    row = db.execute('SELECT c.level FROM characters c JOIN character_owners o ON '
        'o.uid=c.uid WHERE c.uid=? AND o.account_id=?', (uid, account_id)).fetchone()
    if row is None:
        raise ValueError('PvP saved character owner')
    return row[0]


def snapshot(db, uid, account_id):
    _owner(db, uid, account_id)
    present = tuple(_exists(db, name) for name in TABLES)
    if not any(present):
        return None
    if not all(present):
        raise ValueError('Partial PvP schema requires explicit compatibility review')
    row = db.execute('SELECT account_id,policy,profile_json,revision,source_operation '
        'FROM official_pvp_profiles WHERE uid=?', (uid,)).fetchone()
    if row is None:
        return None
    if row[0] != account_id or row[1] != POLICY or type(row[3]) is not int or row[3] < 0:
        raise ValueError('Unknown PvP profile owner/version')
    profile = Profile(**json.loads(row[2])).checked()
    receipt = db.execute('SELECT uid,account_id FROM official_pvp_registrations '
                        'WHERE operation=?', (row[4],)).fetchone()
    if receipt != (uid, account_id):
        raise ValueError('PvP profile lacks its actual registration receipt')
    return profile, row[3]


def cold(path, uid, account_id):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',
                                uri=True, timeout=10)) as db:
        db.execute('BEGIN')
        return snapshot(db, uid, account_id)


def _schema(db):
    # No migration of foreign PvP histories into the approved fresh policy.
    unknown = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
               if 'pvp' in r[0].lower() and r[0] not in OWNED_TABLES]
    if unknown:
        raise ValueError('Unknown historic PvP tables are read-only')
    columns = [r[1].lower() for r in db.execute('PRAGMA table_info(characters)')]
    if any('pvp' in name or name in ('rating', 'arena_points', 'rank_points') for name in columns):
        raise ValueError('Unknown character PvP history is read-only')
    present = tuple(_exists(db, name) for name in TABLES)
    if any(present) and not all(present):
        raise ValueError('Partial PvP schema')
    db.execute('CREATE TABLE IF NOT EXISTS official_pvp_profiles ('
        'uid INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,'
        'policy TEXT NOT NULL,profile_json TEXT NOT NULL,revision INTEGER NOT NULL,'
        'source_operation TEXT NOT NULL UNIQUE)')
    db.execute('CREATE TABLE IF NOT EXISTS official_pvp_registrations ('
        'operation TEXT PRIMARY KEY,uid INTEGER NOT NULL,account_id INTEGER NOT NULL,'
        'request_hash TEXT NOT NULL,response_json TEXT NOT NULL)')


def register(path, uid, account_id, payload, operation, *, guard, encode):
    """One actual 342 registration, no entry cost or implicit match outcome.

    encode(profile, repeat) returns the normal 343/344 events after checking
    the original queue generation. This runs inside BEGIN IMMEDIATE. The
    caller publishes its prepared queue/mailbox changes only after return.
    Same-operation receipt reads have zero SQL writes, including recovery.
    """
    if not callable(guard) or not callable(encode):
        raise ValueError('PvP live guard and native response required')
    if type(operation) is not str or not 1 <= len(operation) <= 180:
        raise ValueError('PvP registration operation')
    modes, hint, related = registration(payload)
    if modes != ((0, 1, False),) or related:
        raise ValueError('PvP only ordinary solo 1v1 registration')
    digest = hashlib.sha256(str(uid).encode()+b':'+str(account_id).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            guard()
            if _owner(db, uid, account_id) < 10:
                raise ValueError('PvP minimum level')
            old = None if not _exists(db, TABLES[1]) else db.execute(
                'SELECT uid,account_id,request_hash,response_json FROM official_pvp_registrations '
                'WHERE operation=?', (operation,)).fetchone()
            if old is not None:
                if old[:3] != (uid, account_id, digest):
                    raise ValueError('Conflicting PvP registration receipt')
                saved = snapshot(db, uid, account_id)
                if saved is None:
                    raise ValueError('Missing registered PvP profile')
                events = tuple(decode_event(bytes.fromhex(raw)) for raw in json.loads(old[3]))
                for event in events:
                    encode_event(event)
                guard()
                db.rollback()
                return saved[0], events, True
            if not WRITER_ENABLED:
                raise ValueError('PvP new registration held in recovery')
            _schema(db)
            saved = snapshot(db, uid, account_id)
            profile = Profile().checked() if saved is None else saved[0]
            guard()
            events = tuple(encode(profile, False))
            if not events or events[0].kind != 0x343 or events[0].payload[:4] != bytes(4):
                raise ValueError('PvP native successful registration response required')
            responses = json.dumps([encode_event(e).hex() for e in events], separators=(',', ':'))
            guard()
            if _owner(db, uid, account_id) < 10:
                raise ValueError('PvP late saved eligibility change')
            db.execute('INSERT INTO official_pvp_registrations VALUES(?,?,?,?,?)',
                       (operation, uid, account_id, digest, responses))
            if saved is None:
                db.execute('INSERT INTO official_pvp_profiles VALUES(?,?,?,?,0,?)',
                    (uid, account_id, POLICY, json.dumps(asdict(profile), sort_keys=True,
                     separators=(',', ':')), operation))
            if snapshot(db, uid, account_id) != (profile, 0 if saved is None else saved[1]):
                raise ValueError('PvP registration readback')
            guard()
            db.commit()
            return profile, events, False
        except BaseException:
            db.rollback()
            raise
