"""The native camp buff survives reconnect until its original1800second end."""
import time
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner

BUFF=1433;FACTOR=1538;WAIT=360;PERIOD=1800
TOWNS=frozenset((1009,1010,20013,1011))

def active(db,owner,now=None):
    now=int(time.time()) if now is None else now
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='town_rest_buffs'").fetchone():return ()
    row=db.execute('SELECT town,starts_at,ends_at,operation_id FROM town_rest_buffs WHERE owner=?',(owner,)).fetchone()
    if row is None:return ()
    town,start,end,operation=row
    if town not in TOWNS or not 1<=start<end<2**31 or end-start!=PERIOD or not operation:raise ValueError('Saved native camp buff')
    return (dict(owner=owner,template=BUFF,factor=FACTOR,start=start,end=end),) if start<=now<end else ()

def grant(db,owner,account,town,operation,now):
    require_owner(db,owner,account);require_active_character(db,owner)
    if not db.in_transaction or town not in TOWNS or db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(town,):raise ValueError('Camp buff current town')
    if active(db,owner,now):return False
    db.execute('CREATE TABLE IF NOT EXISTS town_rest_buffs(owner INTEGER PRIMARY KEY REFERENCES characters(uid),town INTEGER NOT NULL,starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL)')
    db.execute('INSERT INTO town_rest_buffs VALUES(?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET town=excluded.town,starts_at=excluded.starts_at,ends_at=excluded.ends_at,operation_id=excluded.operation_id',(owner,town,now,now+PERIOD,operation))
    from els_server.storage.growth_guide import record
    record(db,owner,77,town=town)
    return True
