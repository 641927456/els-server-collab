"""Reconcile source-proven level titles with committed character state atomically."""
from contextlib import closing
import sqlite3,time
from els_server.storage import titles
from els_server.domain.title_level_rules import achieved
from els_server.protocol import title_messages as wire

def _events(value):
    events=[wire.initialization(value),wire.equipment(value['title'])]
    if any(not isinstance(e.payload,bytes) or not 1<=len(e.payload)<=65536 for e in events):raise ValueError('Level title response bounds')
    return events


def _unchanged(db,uid,now):
    if not all(titles.exists(db,t) for t in ('title_ownership','title_equipment','title_item_receipts')):return None
    character=titles.character(db,uid)
    present={r[0] for r in db.execute("SELECT title FROM title_ownership WHERE scope='character' AND subject=?",(uid,))}
    if any(identity not in present for identity in achieved(character)):return None
    value=titles.snapshot(db,uid,now)
    selected=db.execute('SELECT title FROM title_equipment WHERE owner=?',(uid,)).fetchone()
    if selected and selected[0] and not value['title']:return None
    return value


def synchronize(path,uid,*,now=None):
    now=int(time.time()) if now is None else now
    if type(now) is not int or not 0<=now<2**40:raise ValueError('Level title clock')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        # Repeated notification snapshots require no writer when ownership and
        # equipped title already match the committed character. Never upgrade
        # a read snapshot: release it and recompute under the writer instead.
        db.execute('BEGIN')
        value=_unchanged(db,uid,now)
        if value is not None:return value,_events(value)
        db.rollback()
        db.execute('BEGIN IMMEDIATE');character=titles.character(db,uid)
        qualified=achieved(character);titles.schema(db)
        for identity in qualified:
            # Preserve an existing ownership row, its attribution and acquisition time.
            db.execute('INSERT OR IGNORE INTO title_ownership VALUES (?,?,?,?,?,?)',('character',uid,identity,character['name'],now,0))
        value=titles.snapshot(db,uid,now)
        if not value['title']:db.execute('UPDATE title_equipment SET title=0 WHERE owner=? AND title<>0',(uid,))
        # Reuse the verified ownership DTO. Encoding failure must roll back all inserts.
        return value,_events(value)
