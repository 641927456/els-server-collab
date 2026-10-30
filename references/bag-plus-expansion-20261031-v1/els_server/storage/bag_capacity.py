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


def expansion_quote(db,uid,group):
    # Reuse this server's listed eight-slot product and price for the same tab.
    from els_server.storage.shop_state import catalog
    from els_server.storage.character_schema import stored_character_type
    template=next((t for t,g in PRODUCT_GROUPS.items() if g==group),None)
    offer=next((p for p in catalog(stored_character_type(db,uid)) if p['template']==template),None)
    if offer is None or offer['quantity']!=1:raise ValueError('Bag expansion product unavailable')
    current=allowances(db,uid)[group]
    if current+8>NATIVE_LIMIT:raise ValueError('Bag capacity limit')
    return template,current,offer['price']


def direct_expansion(path,uid,account_id,payload,operation,*,expected=None,prepare):
    from contextlib import closing
    import sqlite3
    from els_server.protocol import bag_expansion_messages as wire
    from els_server.protocol.protocol_codec import encode_event
    from els_server.storage.inventory_actions import _identity,_previous,_commit
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    from els_server.storage.npc_trade import balances,charge
    group=wire.request(payload)
    uid,digest=_identity(uid,0x479,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prepare(db);require_owner(db,uid,account_id);require_active_character(db,uid)
        old=_previous(db,operation,digest);balance=balances(db,uid)
        if old is not None:
            event=wire.expansion_ack(ed=balance['ed'])
        else:
            template,current,cost=expansion_quote(db,uid,group)
            if expected!=(template,current,cost):raise ValueError('Bag expansion quote missing or changed')
            ed=charge(db,uid,balance,cost)
            new=expand(db,uid,template,1)
            event=wire.expansion_ack(group,ed,new-current)
            _commit(db,operation,digest,uid,0x479,[],[dict(group=group,capacity=current)],[dict(group=group,capacity=new)])
        encode_event(event)
        prepare(db)
        return event
