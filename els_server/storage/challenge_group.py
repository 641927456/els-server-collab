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


def begin(path, uids, leader, challenge, phase, *, now=None):
    uids=tuple(uids);now=int(time.time()) if now is None else now
    if any(type(uid) is not int or not 1001<=uid<2**63 for uid in uids):raise ValueError('Challenge character identity')
    uids=tuple(sorted(uids))
    if not 2<=len(uids)<=6 or len(set(uids))!=len(uids) or leader not in uids:raise ValueError('Challenge roster')
    definition=phase_definition(challenge,phase)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        old=[read(db,uid) for uid in uids]
        active=[row for row in old if row and not row['complete'] and row['deadline']>now]
        if active:
            first=active[0]
            roster=db.execute('SELECT leader,roster_json FROM challenge_rosters WHERE attempt=?',(first['attempt'],)).fetchone()
            if (len(active)!=len(uids) or any(row!=first for row in active) or
                (first['challenge'],first['phase'])!=(challenge,phase) or roster!=(leader,json.dumps(uids))):
                raise ValueError('An active attempt belongs to a different party or phase')
            return first
        attempt=str(uuid.uuid4())
        db.execute('INSERT INTO challenge_rosters VALUES (?,?,?)',(attempt,leader,json.dumps(uids)))
        for uid in uids:
            db.execute('INSERT INTO challenge_attempts VALUES (?,?,?,?,?,0,0) ON CONFLICT(uid) DO UPDATE SET attempt=excluded.attempt,challenge=excluded.challenge,phase=excluded.phase,deadline=excluded.deadline,progress=0,complete=0',(uid,attempt,challenge,phase,now+definition['seconds']))
        db.execute('DELETE FROM challenge_rosters WHERE attempt NOT IN (SELECT attempt FROM challenge_attempts)')
        return read(db,leader)


def abandon(path, attempt):
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        db.execute('DELETE FROM challenge_attempts WHERE attempt=?',(attempt,))
        db.execute('DELETE FROM challenge_rosters WHERE attempt=?',(attempt,))
