"""Native911 spa ED debit and its immutable operation identity."""
from els_server.storage.npc_trade import balances

def debit(db,owner,operation,town,division):
    db.execute('''CREATE TABLE IF NOT EXISTS environment_spa_purchases(
        operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL,town INTEGER NOT NULL,
        division INTEGER NOT NULL,cost INTEGER NOT NULL)''')
    cost=250000 if division==97 else 350000 if division==96 else 500000
    prior=db.execute('SELECT owner,town,division,cost FROM environment_spa_purchases WHERE operation_id=?',(operation,)).fetchone()
    if prior is not None:
        if prior!=(owner,town,division,cost):raise ValueError('Conflicting spa purchase replay')
        return False
    raise ValueError('Recovery only: fresh spa purchase is disabled')
    value=balances(db,owner)
    if value['ed']<cost:raise ValueError('Insufficient spa ED')
    db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?',(cost,owner))
    db.execute('INSERT INTO environment_spa_purchases VALUES(?,?,?,?,?)',(operation,owner,town,division,cost))
    return True
