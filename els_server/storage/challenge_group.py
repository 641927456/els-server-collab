"""Atomic roster-bound challenge attempts in the existing game database."""
import json
import sqlite3
import time
import uuid
from contextlib import closing
from els_server.storage.challenge_state import ensure, read, phase_definition


def schema(db):
    ensure(db)
    db.execute('CREATE TABLE IF NOT EXISTS challenge_rosters (attempt TEXT PRIMARY KEY, leader INTEGER NOT NULL, roster_json TEXT NOT NULL)')


def _guard(db, uids, owners, prepare, *, active=True):
    if prepare is not None:prepare()
    if owners is not None:
        if set(owners)!=set(uids):raise ValueError('Challenge owner roster changed')
        from els_server.storage.profession_state import require_owner
        from els_server.storage.item_actor import require_active_character
        for uid in uids:
            require_owner(db,uid,owners[uid])
            if active:require_active_character(db,uid)


def _roster(db, attempt, uids, leader):
    row=db.execute('SELECT leader,roster_json FROM challenge_rosters WHERE attempt=?',(attempt,)).fetchone()
    actual=tuple(r[0] for r in db.execute('SELECT uid FROM challenge_attempts WHERE attempt=? ORDER BY uid',(attempt,)))
    if row!=(leader,json.dumps(uids)) or actual!=uids:raise ValueError('Challenge saved roster changed')


def begin(path, uids, leader, challenge, phase, *, now=None, owners=None, prepare=None, precommit=None):
    uids=tuple(uids)
    if any(type(uid) is not int or not 1001<=uid<2**63 for uid in uids):raise ValueError('Challenge character identity')
    uids=tuple(sorted(uids))
    if not 2<=len(uids)<=6 or len(set(uids))!=len(uids) or leader not in uids:raise ValueError('Challenge roster')
    definition=phase_definition(challenge,phase)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');_guard(db,uids,owners,prepare);schema(db)
        now=int(time.time()) if now is None else now
        old=[read(db,uid) for uid in uids]
        active=[row for row in old if row and not row['complete'] and row['deadline']>now]
        if active:
            first=active[0]
            roster=db.execute('SELECT leader,roster_json FROM challenge_rosters WHERE attempt=?',(first['attempt'],)).fetchone()
            if (len(active)!=len(uids) or any(row!=first for row in active) or
                (first['challenge'],first['phase'])!=(challenge,phase) or roster!=(leader,json.dumps(uids))):
                raise ValueError('An active attempt belongs to a different party or phase')
            if precommit is not None:precommit(first)
            _guard(db,uids,owners,prepare)
            return first
        attempt=str(uuid.uuid4())
        db.execute('INSERT INTO challenge_rosters VALUES (?,?,?)',(attempt,leader,json.dumps(uids)))
        for uid in uids:
            db.execute('INSERT INTO challenge_attempts VALUES (?,?,?,?,?,0,0) ON CONFLICT(uid) DO UPDATE SET attempt=excluded.attempt,challenge=excluded.challenge,phase=excluded.phase,deadline=excluded.deadline,progress=0,complete=0',(uid,attempt,challenge,phase,now+definition['seconds']))
        db.execute('DELETE FROM challenge_rosters WHERE attempt NOT IN (SELECT attempt FROM challenge_attempts)')
        state=read(db,leader)
        if precommit is not None:precommit(state)
        _guard(db,uids,owners,prepare)
        return state


def abandon(path, attempt, *, uids=None, leader=None, owners=None, prepare=None, precommit=None, active=True):
    if type(active)is not bool:raise ValueError('Challenge cleanup actor mode')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        current=tuple(sorted(uids)) if uids is not None else ()
        if owners is not None and uids is None:raise ValueError('Challenge cancellation roster missing')
        _guard(db,current,owners,prepare,active=active);schema(db)
        if uids is not None:_roster(db,attempt,current,leader)
        db.execute('DELETE FROM challenge_attempts WHERE attempt=?',(attempt,))
        db.execute('DELETE FROM challenge_rosters WHERE attempt=?',(attempt,))
        if precommit is not None:precommit(None)
        _guard(db,current,owners,prepare,active=active)
