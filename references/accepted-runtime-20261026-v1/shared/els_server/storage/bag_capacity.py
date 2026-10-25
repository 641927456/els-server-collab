"""Per-character bag allowances, mutated inside the purchase transaction."""
from els_server.domain.bag_capacity import LOCAL_BASE,NATIVE_LIMIT,PRODUCT_GROUPS,STARTING_FASHION_CAPACITIES,capacities

def saved_capacities(db,uid):
    values={}
    for table in ('character_bag_capacities','character_extra_bag_capacities'):
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            values.update(db.execute('SELECT bag_group,capacity FROM '+table+' WHERE owner=?',(uid,)))
    capacities({'bag_capacities':values})
    return values

def allowances(db,uid):
    return capacities({'bag_capacities':saved_capacities(db,uid)})

def expand(db,uid,template,quantity):
    if type(quantity) is not int or not 1<=quantity<=36 or template not in PRODUCT_GROUPS:raise ValueError('Invalid bag expansion')
    if not db.execute('SELECT 1 FROM characters WHERE uid=?',(uid,)).fetchone():raise ValueError('Unknown bag owner')
    group=PRODUCT_GROUPS[template];old=allowances(db,uid)[group];new=old+8*quantity
    if new>NATIVE_LIMIT:raise ValueError('Bag capacity limit')
    if group==21:
        ensure_extra(db)
        db.execute('INSERT INTO character_extra_bag_capacities VALUES (?,?,?) ON CONFLICT(owner,bag_group) DO UPDATE SET capacity=excluded.capacity',(uid,group,new))
        return new
    db.execute('CREATE TABLE IF NOT EXISTS character_bag_capacities (owner INTEGER NOT NULL REFERENCES characters(uid), bag_group INTEGER NOT NULL CHECK(bag_group BETWEEN 1 AND 6), capacity INTEGER NOT NULL CHECK(capacity BETWEEN 36 AND 392 AND (capacity-36)%8=0), PRIMARY KEY(owner,bag_group))')
    db.execute('INSERT INTO character_bag_capacities VALUES (?,?,?) ON CONFLICT(owner,bag_group) DO UPDATE SET capacity=excluded.capacity',(uid,group,new))
    return new


def ensure_extra(db):
    # Separate table preserves the original six-group schema and every row.
    db.execute('CREATE TABLE IF NOT EXISTS character_extra_bag_capacities (owner INTEGER NOT NULL REFERENCES characters(uid), bag_group INTEGER NOT NULL, capacity INTEGER NOT NULL, CHECK((bag_group=21 AND capacity BETWEEN 36 AND 392 AND (capacity-36)%8=0) OR (bag_group=7 AND capacity=840) OR (bag_group=27 AND capacity=1120)), PRIMARY KEY(owner,bag_group))')


def grant_starting_fashion(db,uid):
    # Called only by the new-identity branch inside the creation transaction.
    ensure_extra(db)
    db.executemany('INSERT INTO character_extra_bag_capacities VALUES (?,?,?)',[(uid,g,n) for g,n in STARTING_FASHION_CAPACITIES.items()])
    return dict(STARTING_FASHION_CAPACITIES)
