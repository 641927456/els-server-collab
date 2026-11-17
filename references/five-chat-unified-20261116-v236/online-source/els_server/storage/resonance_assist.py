"""Account entitlement and purchase receipt in the existing shop SQL writer."""
from els_server.domain.resonance_assist import DURATION,PRICE,level_multiplier

TABLE='resonance_assist_periods'
OPS='resonance_assist_purchases'

def period(db,account):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone():return None
    row=db.execute('SELECT starts_at,expires_at,operation FROM resonance_assist_periods WHERE account=?',(account,)).fetchone()
    if row is not None and (any(type(x)is not int for x in row[:2])or row[0]<=0 or row[1]-row[0]!=DURATION):raise ValueError('Saved assist period')
    return row

def multiplier(db,owner,account,dungeon,now):
    from els_server.storage import resonance_state as er
    account=er.owner(db,owner,account)
    saved=period(db,account)
    if saved is None or not saved[0]<=now<saved[1]:return 1
    # Current original exclusions: secret dungeons and Gate of Darkness.
    if dungeon is not None:
        from els_server.domain.title_economy import dungeon_type
        if dungeon==38300 or dungeon_type(dungeon)==3:return 1
    if er.route(db,owner,account)!='resonance':return 1
    return level_multiplier(er.snapshot(db,owner,account)['level'])

def purchase(db,owner,account,operation,digest,now):
    from els_server.storage.normal_fatigue import _actor
    from els_server.storage.npc_trade import balances,charge
    if not db.in_transaction or type(now)is not int or not 0<now<2**31-DURATION:raise ValueError('Assist purchase writer/clock')
    _actor(db,owner,account)
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(OPS,)).fetchone()
    old=db.execute('SELECT owner,account,request_sha FROM resonance_assist_purchases WHERE operation=?',(operation,)).fetchone()if exists else None
    wallet=balances(db,owner)
    if old is not None:
        if old!=(owner,account,digest):raise ValueError('Conflicting assist purchase retry')
        return wallet['ed']
    saved=period(db,account)
    if saved is not None and now<saved[1]:raise ValueError('Resonance assist is already active')
    ed=charge(db,owner,wallet,PRICE)
    db.execute('CREATE TABLE IF NOT EXISTS resonance_assist_periods(account INTEGER PRIMARY KEY,starts_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,operation TEXT NOT NULL UNIQUE)')
    db.execute('CREATE TABLE IF NOT EXISTS resonance_assist_purchases(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,account INTEGER NOT NULL,request_sha TEXT NOT NULL,starts_at INTEGER NOT NULL,expires_at INTEGER NOT NULL)')
    db.execute('INSERT INTO resonance_assist_periods VALUES(?,?,?,?) ON CONFLICT(account) DO UPDATE SET starts_at=excluded.starts_at,expires_at=excluded.expires_at,operation=excluded.operation',(account,now,now+DURATION,operation))
    db.execute('INSERT INTO resonance_assist_purchases VALUES(?,?,?,?,?,?)',(operation,owner,account,digest,now,now+DURATION))
    return ed
