"""Shared account life4800, inferred current units; CN10:00 fresh-login reset.

20 is original fishing cost. The1440/30% derivation is frozen outside runtime.
No item-use endpoint, automatic online refill, or level-up reset is introduced.
"""
from datetime import datetime,timedelta,timezone
MAXIMUM=4800


def day(now):
    if type(now)not in(int,float)or now<0:raise ValueError('Life clock')
    local=datetime.fromtimestamp(now,timezone(timedelta(hours=8)))
    return (local-timedelta(hours=10)).date().toordinal()


def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_life_stamina'").fetchone())


def owner(db,uid,account):
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    require_active_character(db,uid);require_owner(db,uid,account)


def snapshot(db,uid,account):
    from els_server.storage.profession_state import require_owner
    require_owner(db,uid,account)
    row=db.execute('SELECT current,maximum FROM account_life_stamina WHERE account=?',(account,)).fetchone()if exists(db)else None
    current,maximum=row if row is not None else(MAXIMUM,MAXIMUM)
    if type(current)is not int or maximum!=MAXIMUM or not 0<=current<=maximum:raise ValueError('Life saved state')
    return dict(current=current,maximum=maximum)


def initialize(db,uid,account,connection,now):
    import uuid
    owner(db,uid,account)
    if not db.in_transaction or str(uuid.UUID(connection))!=connection or uuid.UUID(connection).version!=4:raise ValueError('Life original login')
    db.execute('''CREATE TABLE IF NOT EXISTS account_life_stamina (
      account INTEGER PRIMARY KEY CHECK(account>0),current INTEGER NOT NULL CHECK(current BETWEEN0 AND4800),
      maximum INTEGER NOT NULL CHECK(maximum=4800),reset_day INTEGER NOT NULL,last_connection TEXT NOT NULL)'''.replace('BETWEEN0 AND4800','BETWEEN 0 AND 4800'))
    today=day(now);row=db.execute('SELECT current,maximum,reset_day,last_connection FROM account_life_stamina WHERE account=?',(account,)).fetchone()
    if row is None:
        db.execute('INSERT INTO account_life_stamina VALUES(?,?,?,?,?)',(account,MAXIMUM,MAXIMUM,today,connection))
    else:
        snapshot(db,uid,account)
        if row[2]>today:raise ValueError('Future life reset period')
        # One continuously connected account never refreshes at10:00. A new
        # original connection observes the next daily entitlement once.
        current=MAXIMUM if row[2]<today and row[3]!=connection else row[0]
        reset=today if current==MAXIMUM and row[2]<today and row[3]!=connection else row[2]
        db.execute('UPDATE account_life_stamina SET current=?,reset_day=?,last_connection=? WHERE account=?',(current,reset,connection,account))
    return snapshot(db,uid,account)


def debit(db,uid,account,amount,*,premium_at=None):
    owner(db,uid,account)
    if not db.in_transaction or type(amount)is not int or amount not in(10,20):raise ValueError('Finite original life cost')
    if amount==10:
        from els_server.storage.fishing_vip import active
        if premium_at is None or not active(db,uid,account,premium_at):raise ValueError('FishingVIP saved authority required for half life cost')
    row=snapshot(db,uid,account)
    if not exists(db)or row['current']<amount:raise ValueError('Insufficient saved life')
    if db.execute('UPDATE account_life_stamina SET current=current-? WHERE account=? AND current=?',(amount,account,row['current'])).rowcount!=1:raise ValueError('Life compare-and-set')
    return snapshot(db,uid,account)
