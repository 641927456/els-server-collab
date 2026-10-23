"""EP reads and credits participate in the caller's character transaction."""
from els_server.domain.ep_points import validate
from els_server.storage.character_schema import character_uid

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS character_ep (uid INTEGER PRIMARY KEY REFERENCES characters(uid), ep INTEGER NOT NULL CHECK(ep BETWEEN 0 AND 10000), revision INTEGER NOT NULL CHECK(revision>=0))')

def balance(db,uid):
    uid=character_uid(uid)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_ep'").fetchone():return 0
    row=db.execute('SELECT ep FROM character_ep WHERE uid=?',(uid,)).fetchone()
    return validate(row[0]) if row else 0

def credit(db,uid,amount):
    uid=character_uid(uid);validate(amount)
    if not db.execute('SELECT 1 FROM characters WHERE uid=?',(uid,)).fetchone():raise ValueError('Unknown EP owner')
    current=balance(db,uid);after=validate(current+amount)
    if amount:
        if not db.in_transaction:raise ValueError('EP credit requires caller transaction')
        ensure(db)
        row=db.execute('SELECT revision FROM character_ep WHERE uid=?',(uid,)).fetchone()
        if row is not None and (type(row[0]) is not int or not 0<=row[0]<2**63-1):
            raise ValueError('EP revision limit')
        db.execute('INSERT INTO character_ep VALUES (?,?,1) ON CONFLICT(uid) DO UPDATE SET ep=excluded.ep,revision=character_ep.revision+1',(uid,after))
    return after


def debit(db,uid,amount):
    """Spend in the existing caller transaction, using its saved EP/revision."""
    uid=character_uid(uid);validate(amount)
    if not db.in_transaction:raise ValueError('EP debit requires caller transaction')
    if not db.execute('SELECT 1 FROM characters WHERE uid=?',(uid,)).fetchone():
        raise ValueError('Unknown EP owner')
    current=balance(db,uid)
    if amount>current:raise ValueError('Insufficient Epic Points')
    if amount:
        row=db.execute('SELECT revision FROM character_ep WHERE uid=?',(uid,)).fetchone()
        if row is None or type(row[0])is not int or not 0<=row[0]<2**63-1:
            raise ValueError('EP revision limit')
        changed=db.execute('UPDATE character_ep SET ep=?,revision=revision+1 WHERE uid=? AND ep=? AND revision=?',
                           (current-amount,uid,current,row[0])).rowcount
        if changed!=1:raise ValueError('EP balance changed during debit')
    return current-amount
