"""Account appearance entitlements and owned item state in one SQLite tx.

Registration survives destruction of its original item, as the CN guide states.
No grants, prices, client stat calculation, timers or new appearance UI.
"""
import hashlib,json,sqlite3
from contextlib import closing
from els_server.storage.character_schema import character_uid


def present(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()is not None


def ensure(db):
    if not db.in_transaction:raise ValueError('Wardrobe schema needs transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_sources (
        item_uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL CHECK(account_id>0),
        template INTEGER NOT NULL CHECK(template>0),registered_owner INTEGER NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS wardrobe_sources_account ON wardrobe_sources(account_id,template)')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_item_state (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) ON DELETE CASCADE,
        appearance INTEGER NOT NULL CHECK(appearance>=0),hanger INTEGER NOT NULL CHECK(hanger IN (0,1)))''')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_receipts (
        operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,
        account_id INTEGER NOT NULL,kind INTEGER NOT NULL,uids_json TEXT NOT NULL)''')


def counts(db,owner,account_id):
    character_uid(owner)
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account_id,):
        raise ValueError('Wardrobe account owner mismatch')
    if not present(db,'wardrobe_sources'):return {}
    return dict(db.execute('SELECT template,COUNT(*) FROM wardrobe_sources WHERE account_id=? GROUP BY template',(account_id,)))


def snapshot(path,owner,account_id):
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');return counts(db,owner,account_id)


def attach(db,items,owner):
    if not present(db,'wardrobe_item_state'):return
    by_uid={i['uid']:i for i in items}
    for uid,appearance,hanger in db.execute('SELECT s.item_uid,s.appearance,s.hanger FROM wardrobe_item_state s JOIN inventory_items i ON i.uid=s.item_uid WHERE i.owner=?',(owner,)):
        if hanger not in (0,1):raise ValueError('Corrupt wardrobe hanger')
        by_uid[uid].update(appearance_template=appearance,wardrobe_hanger=bool(hanger))


def assign(db,owner,item):
    from els_server.domain.wardrobe import validate_state
    validate_state(item)
    if not db.in_transaction or db.execute('SELECT 1 FROM inventory_items WHERE uid=? AND owner=?',(item['uid'],owner)).fetchone()is None:
        raise ValueError('Wardrobe instance owner/transaction')
    ensure(db)
    db.execute('INSERT INTO wardrobe_item_state VALUES(?,?,?) ON CONFLICT(item_uid) DO UPDATE SET appearance=excluded.appearance,hanger=excluded.hanger',
               (item['uid'],item.get('appearance_template',0),int(item.get('wardrobe_hanger',False))))


def change(path,owner,account_id,kind,payload,operation,*,validate=lambda:None):
    from els_server.protocol.wardrobe_messages import register_request,apply_request,acknowledgement
    from els_server.domain.wardrobe import definition,require_owner,validate_state
    from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
    from els_server.domain.ordinary_accessories import definitions as accessories
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_locks import require_unlocked
    if kind not in (0x4af,0x4b1) or not isinstance(operation,str)or not 1<=len(operation)<=160:raise ValueError('Wardrobe operation identity')
    request=register_request(payload)if kind==0x4af else apply_request(payload)
    owner=character_uid(owner);digest=hashlib.sha256(str((owner,account_id,kind)).encode()+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
        registry=counts(db,owner,account_id);before=load_items(db,owner);by_uid={i['uid']:i for i in before}
        ensure(db)
        old=db.execute('SELECT request_hash,owner,account_id,kind,uids_json FROM wardrobe_receipts WHERE operation_id=?',(operation,)).fetchone()
        if old:
            if old[:4]!=(digest,owner,account_id,kind):raise ValueError('Conflicting wardrobe retry')
            changes=[((i['group'],i['slot']),i)for uid in json.loads(old[4])if(i:=by_uid.get(uid))is not None]
            result=acknowledgement(kind,registry,changes);validate();return result
        row=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
        character=dict(unit_type=row[0],unit_class=row[1]);affected=[]
        targets=[request]if kind==0x4af else [r[2]for r in request]
        for uid in targets:
            item=by_uid.get(uid)
            if item is None or item['group']not in (1,2,7,27,9)or item['count']!=1:raise ValueError('Wardrobe needs owned equipment')
            definition(item['template']);require_owner(item['template'],character)
            if 'expires_at'in item or item.get('sealed',False)or item.get('identified')is False:
                raise ValueError('Timed/sealed/unidentified wardrobe target')
            if kind==0x4af:require_unlocked(item)
        if kind==0x4af:
            item=dict(by_uid[request]);t=item['template']
            existing=db.execute('SELECT account_id,template FROM wardrobe_sources WHERE item_uid=?',(request,)).fetchone()
            if existing is not None and existing!=(account_id,t):raise ValueError('Wardrobe source identity conflict')
            if existing is None:db.execute('INSERT INTO wardrobe_sources VALUES(?,?,?,?)',(request,account_id,t,owner))
            if t in FASHION_EQUIP_SLOTS or t in accessories():
                item.update(wardrobe_hanger=True,appearance_template=item.get('appearance_template',0));assign(db,owner,item)
            affected=[request]
        else:
            for position,template,uid in request:
                item=dict(by_uid[uid]);base=definition(item['template']);chosen=definition(template)
                require_owner(template,character)
                if position!=base['equip_position']or not registry.get(template):raise ValueError('Unregistered appearance or wrong target position')
                from els_server.domain.normal_equipment import definitions as normal
                if item['template']not in normal()and not item.get('wardrobe_hanger',False):raise ValueError('Target has no registered hanger')
                item['appearance_template']=template;item.setdefault('wardrobe_hanger',False)
                validate_state(item);assign(db,owner,item);affected.append(uid)
        after=load_items(db,owner);current={i['uid']:i for i in after}
        # Only appearance/binding fields can change; identity, location and stats persist.
        strip=lambda i:{k:v for k,v in i.items()if k not in ('appearance_template','wardrobe_hanger')}
        if [strip(i)for i in after]!=[strip(i)for i in before]:raise ValueError('Wardrobe altered base inventory')
        result=acknowledgement(kind,counts(db,owner,account_id),[((current[u]['group'],current[u]['slot']),current[u])for u in affected])
        db.execute('INSERT INTO wardrobe_receipts VALUES(?,?,?,?,?,?)',(operation,digest,owner,account_id,kind,json.dumps(affected)))
        validate();return result
