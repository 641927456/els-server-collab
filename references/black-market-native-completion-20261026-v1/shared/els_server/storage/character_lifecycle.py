"""Transactional CN character deletion, restoration and creation limits.

Current client StringTable 16102/16111/52334/55288: 72h creation
protection, 72h final-delete wait, 24h restore wait/cooldown, four creates/day.
Final deletion retains inaccessible tombstones and receipts; UIDs never recycle.
"""
import time,json
from contextlib import closing
import sqlite3
DAY=86400
def current_time():return int(time.time())
class LifecycleError(ValueError):
    def __init__(self,message,result=1,until=0):super().__init__(message);self.result=result;self.until=until
def exists(db):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_lifecycle'").fetchone() is not None
def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS character_lifecycle (uid INTEGER PRIMARY KEY REFERENCES characters(uid), account_id INTEGER NOT NULL, created_at INTEGER NOT NULL CHECK(created_at>=0), requested_at INTEGER NOT NULL DEFAULT 0, finalize_at INTEGER NOT NULL DEFAULT 0, restore_at INTEGER NOT NULL DEFAULT 0, cooldown_until INTEGER NOT NULL DEFAULT 0, finalized_at INTEGER NOT NULL DEFAULT 0)')
def states(db,uids=None):
    if not exists(db):return {}
    query='SELECT * FROM character_lifecycle'
    if uids is None:
        rows=db.execute(query)
    else:
        # Keep each statement below SQLite's legacy 999-variable limit.
        uids=tuple(dict.fromkeys(uids));rows=[]
        for start in range(0,len(uids),900):
            batch=uids[start:start+900]
            rows.extend(db.execute(query+' WHERE uid IN ('+','.join('?' for _ in batch)+')',batch))
    return {r[0]:dict(zip(('uid','account_id','created_at','requested_at','finalize_at','restore_at','cooldown_until','finalized_at'),r)) for r in rows}
def visible_ids(db,account_id):
    rows=db.execute('SELECT uid FROM character_owners WHERE account_id=? ORDER BY uid',(account_id,)).fetchall();saved=states(db)
    return tuple(r[0] for r in rows if not saved.get(r[0],{}).get('finalized_at'))
def check_creation(db,account_id,now):
    # UTC+8 calendar day is explicit; no machine clock or timezone changes.
    start=((now+8*3600)//DAY)*DAY-8*3600
    if exists(db) and db.execute('SELECT COUNT(*) FROM character_lifecycle WHERE account_id=? AND created_at>=? AND created_at<?',(account_id,start,start+DAY)).fetchone()[0]>=4:raise LifecycleError('Daily character creation limit')
    if len(visible_ids(db,account_id))>=16:raise LifecycleError('Character capacity')
def created(db,uid,account_id,now):
    initialize(db);db.execute('INSERT INTO character_lifecycle(uid,account_id,created_at) VALUES (?,?,?)',(uid,account_id,now))
def decorate(db,roles):
    roles=tuple(roles);saved=states(db,(c['uid'] for c in roles));out=[]
    for c in roles:
        s=saved.get(c['uid'],{})
        if s.get('finalized_at'):continue
        out.append(dict(c,pending_delete=bool(s.get('requested_at')),delete_at=s.get('finalize_at',0),delete_cooldown_until=s.get('restore_at',0) if s.get('requested_at') else s.get('cooldown_until',0)))
    return out
def _selection_changed(db,account_id,uid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_selection_preferences'").fetchone():return
    row=db.execute('SELECT deployed,character_order FROM character_selection_preferences WHERE account_id=?',(account_id,)).fetchone()
    if row:
        deployed=[0 if v==uid else v for v in json.loads(row[0])];order=[v for v in json.loads(row[1]) if v!=uid]
        db.execute('UPDATE character_selection_preferences SET deployed=?,character_order=?,revision=revision+1 WHERE account_id=?',(json.dumps(deployed),json.dumps(order),account_id))
def change(path,account_id,uid,operation):
    if operation not in ('schedule','restore','finalize'):raise ValueError('Lifecycle operation')
    if type(account_id) is not int or account_id<1 or type(uid) is not int or uid<1001:raise ValueError('Character identity')
    now=current_time()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise LifecycleError('Character ownership')
        if operation in ('schedule','finalize'):
            from els_server.domain.cartridge_registration_rules import require_role_unbound
            require_role_unbound(db,uid,account_id)
            from els_server.storage.black_market_state import require_deletion_unlocked
            require_deletion_unlocked(db,uid)
        s=states(db).get(uid,dict(created_at=0,requested_at=0,finalize_at=0,restore_at=0,cooldown_until=0,finalized_at=0))
        if s['finalized_at']:
            if operation=='finalize':return dict(uid=uid,operation=operation,until=s['finalized_at'])
            raise LifecycleError('Character already deleted')
        if operation=='restore' and not s['requested_at'] and s['cooldown_until']:
            return dict(uid=uid,operation=operation,until=s['cooldown_until'])
        from els_server.storage.character_selection import _state,_owned
        selection=_state(db,account_id,_owned(db,account_id))
        if uid in selection['deployed']:raise LifecycleError('Deployed character cannot be deleted')
        if operation=='schedule':
            if s['requested_at']:return dict(uid=uid,operation=operation,until=s['finalize_at'],restore_at=s['restore_at'])
            if s['created_at'] and now<s['created_at']+3*DAY:raise LifecycleError('New character deletion protection',0x9b6,s['created_at']+3*DAY)
            if now<s['cooldown_until']:raise LifecycleError('Restored character deletion cooldown',0x3d4,s['cooldown_until'])
        else:
            if not s['requested_at']:raise LifecycleError('Character is not pending deletion')
            until=s['restore_at'] if operation=='restore' else s['finalize_at']
            if now<until:raise LifecycleError('Character lifecycle waiting period',0x3d4,until)
        initialize(db)
        db.execute('INSERT OR IGNORE INTO character_lifecycle(uid,account_id,created_at) VALUES (?,?,0)',(uid,account_id))
        if operation=='schedule':
            db.execute('UPDATE character_lifecycle SET requested_at=?,finalize_at=?,restore_at=? WHERE uid=?',(now,now+3*DAY,now+DAY,uid))
            return dict(uid=uid,operation=operation,until=now+3*DAY,restore_at=now+DAY)
        if operation=='restore':
            db.execute('UPDATE character_lifecycle SET requested_at=0,finalize_at=0,restore_at=0,cooldown_until=? WHERE uid=?',(now+DAY,uid))
            return dict(uid=uid,operation=operation,until=now+DAY)
        # A tombstone prevents startup adoption and receipt replay from reviving
        # the character; per-role items/history remain owned by the old UID.
        db.execute('UPDATE character_lifecycle SET finalized_at=? WHERE uid=?',(now,uid))
        db.execute('UPDATE characters SET name_key=?,revision=revision+1 WHERE uid=?',(':deleted:'+str(uid),uid))
        _selection_changed(db,account_id,uid)
        return dict(uid=uid,operation=operation,until=now)
