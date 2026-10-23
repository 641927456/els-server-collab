"""EP inventory transaction under the explicit source-owned local policy.

Trusted offers explicitly provide grant units,
class eligibility and period/scope; no opaque native field is guessed here.
"""
import hashlib,json,sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.ep_shop import Offer,catalog
from els_server.storage.character_schema import character_uid
from els_server.storage.ep_points import balance,debit
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_state import ensure_inventory,grant_items,load_items,InventoryFull,validate_plan
from els_server.protocol.ep_shop_messages import purchase_request,purchase_ack
from els_server.protocol.protocol_codec import encode_event


def _exists(db,table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None


def _schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS ep_purchase_receipts (owner INTEGER NOT NULL REFERENCES characters(uid), operation_id TEXT NOT NULL, account_id INTEGER NOT NULL CHECK(account_id>0), request_sha256 TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>0), items_json TEXT NOT NULL, PRIMARY KEY(owner,operation_id))')
    db.execute("CREATE TABLE IF NOT EXISTS ep_purchase_counters (scope TEXT NOT NULL CHECK(scope IN ('account','character')), subject INTEGER NOT NULL CHECK(subject>0), template INTEGER NOT NULL CHECK(template>0), period TEXT NOT NULL CHECK(length(period) BETWEEN 1 AND 64), count INTEGER NOT NULL CHECK(count BETWEEN 0 AND 2147483647), PRIMARY KEY(scope,subject,template,period))")


def _offers():
    rows=catalog()
    if type(rows) is not tuple or any(type(o) is not Offer for o in rows):
        raise ValueError('Untrusted EP catalog provider')
    result={o.template:o for o in rows}
    if len(result)!=len(rows):raise ValueError('Duplicate admitted EP product')
    return result


def _counter_key(offer,account_id,uid):
    limit=offer.limit
    return (limit.scope,account_id if limit.scope=='account' else uid,offer.template,limit.period)


def _count(db,offer,account_id,uid):
    if not _exists(db,'ep_purchase_counters'):return 0
    row=db.execute('SELECT count FROM ep_purchase_counters WHERE scope=? AND subject=? AND template=? AND period=?',
                   _counter_key(offer,account_id,uid)).fetchone()
    value=row[0] if row else 0
    if type(value) is not int or not 0<=value<=offer.limit.maximum:raise ValueError('Invalid saved EP counter')
    return value


def _counts(db,offers,account_id,uid):
    return {template:_count(db,offer,account_id,uid) for template,offer in offers.items() if offer.limit is not None}


def _events(ep,counts,items,encode):
    events=(purchase_ack(0,ep,counts,items),)if encode is None else tuple(encode(ep,counts,items))
    if not events or any(not isinstance(getattr(e,'payload',None),bytes)or len(e.payload)>65536 for e in events):
        raise ValueError('EP response bound')
    for event in events:encode_event(event)
    return events


def _retry(db,uid,account_id,offers,saved,encode):
    # Refresh original and current affected slots from owned SQL, never replay
    # historical item counts, positions, wallet values or slot occupants.
    from els_server.storage.inventory_management import _updates
    current=load_items(db,uid);by_uid={i['uid']:i for i in current};by_position={(i['group'],i['slot']):i for i in current}
    positions={(i['group'],i['slot']) for i in saved}
    positions.update((by_uid[i['uid']]['group'],by_uid[i['uid']]['slot']) for i in saved if i['uid'] in by_uid)
    events=_events(balance(db,uid),_counts(db,offers,account_id,uid),[],encode)
    updates=tuple(_updates([(p,by_position.get(p)) for p in sorted(positions)]))
    for event in updates:encode_event(event)
    return (*events,*updates)


def _grant(db,uid,offer,quantity):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,LOCAL_MAX_STACK
    from els_server.storage.bag_capacity import allowances
    template=offer.template
    if template not in VERIFIED_TEMPLATES:raise ValueError('EP grant template not admitted to inventory')
    group=TEMPLATE_BAG_GROUPS[template];metadata=VERIFIED_TEMPLATES[template]
    total=offer.unit_quantity*quantity
    # The existing inventory allocator is authoritative for actual limits.
    # An explicit preflight avoids iterating an impossible huge bundle.
    limits=allowances(db,uid);items=load_items(db,uid);maximum=TEMPLATE_MAX_STACKS[template]
    if group not in limits:raise ValueError('EP product is not an inventory bag item')
    capacity=sum(maximum-i['count'] for i in items if i['group']==group and i['template']==template and i.get('expires_at') is None)
    capacity+=max(0,limits[group]-sum(i['group']==group for i in items))*maximum
    if total>capacity:raise InventoryFull('EP delivery exceeds current owned capacity')
    changed={};batch=[]
    while total:
        amount=min(total,LOCAL_MAX_STACK);total-=amount
        batch.append(dict(template=template,metadata=metadata,group=group,quantity=amount))
        if len(batch)==36 or not total:
            for item in grant_items(db,batch,uid):changed[item['uid']]=item
            batch=[]
    return list(changed.values())


def purchase(path,payload,operation_id,*,account_id,uid,encode=None):
    template,quantity=purchase_request(payload);uid=character_uid(uid)
    if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('Invalid EP account')
    if type(operation_id) is not str or not 1<=len(operation_id)<=100:raise ValueError('Invalid EP operation identity')
    digest=hashlib.sha256(payload).hexdigest()
    # mode=rw refuses to create a mistaken path; only the caller's owned save
    # may already exist. Account and character ownership are checked in SQL.
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db:
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            owned=_owner(db,account_id,uid)
            offers={t:o for t,o in _offers().items()if owned in o.eligible_classes}
            old=db.execute('SELECT account_id,request_sha256,items_json FROM ep_purchase_receipts WHERE owner=? AND operation_id=?',(uid,operation_id)).fetchone() if _exists(db,'ep_purchase_receipts') else None
            if old is not None:
                if old[0]!=account_id or old[1]!=digest:raise ValueError('Conflicting EP purchase retry')
                events=_retry(db,uid,account_id,offers,json.loads(old[2]),encode);db.commit();return events
            offer=offers.get(template)
            if offer is None:raise ValueError('EP product not admitted')
            if owned not in offer.eligible_classes:raise ValueError('EP product class mismatch')
            if offer.limit is not None and _count(db,offer,account_id,uid)+quantity>offer.limit.maximum:
                raise ValueError('EP purchase limit reached')
            # Validate the underlying source-backed inventory type before
            # creating receipt/counter tables or spending a character balance.
            from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
            if template not in VERIFIED_TEMPLATES:raise ValueError('Unadmitted EP inventory template')
            validate_plan([dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=1)])
            cost=offer.unit_price*quantity
            if cost>balance(db,uid):raise ValueError('Insufficient Epic Points')
            ensure_inventory(db);_schema(db)
            after=debit(db,uid,cost);items=_grant(db,uid,offer,quantity)
            if offer.limit is not None:
                db.execute('INSERT INTO ep_purchase_counters VALUES (?,?,?,?,?) ON CONFLICT(scope,subject,template,period) DO UPDATE SET count=count+excluded.count',(*_counter_key(offer,account_id,uid),quantity))
            events=_events(after,_counts(db,offers,account_id,uid),items,encode)
            db.execute('INSERT INTO ep_purchase_receipts VALUES (?,?,?,?,?,?)',(uid,operation_id,account_id,digest,cost,json.dumps(items,sort_keys=True)))
            db.commit();return events
        except BaseException:
            db.rollback();raise


def _owner(db,account_id,uid):
    require_active_character(db,uid)
    row=db.execute('SELECT c.unit_class FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(uid,account_id)).fetchone()
    if row is None:raise ValueError('EP character does not belong to account')
    return row[0]

def snapshot(path,*,account_id,uid):
    uid=character_uid(uid)
    if type(account_id)is not int or not 1<=account_id<2**63:raise ValueError('Invalid EP account')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
        db.execute('BEGIN');unit_class=_owner(db,account_id,uid)
        offers={t:o for t,o in _offers().items()if unit_class in o.eligible_classes}
        return dict(offers=tuple(offers.values()),counts=_counts(db,offers,account_id,uid),ep=balance(db,uid))
