"""Owned chip counters and atomic install/tune transactions; lazy private schema."""
import json,secrets,sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_chip_rules import TEMPLATE,catalog,target,source_options,armor_options,state,resolved,advance
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_chip_messages import installation,tuning,install_ack,tuning_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_options import replace as replace_options
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge

def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_chip_tuning'").fetchone() is not None

def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS equipment_chip_tuning (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        attempts INTEGER NOT NULL CHECK(attempts BETWEEN 0 AND 10),
        successes INTEGER NOT NULL CHECK(successes BETWEEN 0 AND attempts),
        probability INTEGER NOT NULL CHECK(probability IN (0,30,40,50,60,70)))''')

def attach(db,items,owner):
    from els_server.storage.equipment_chip_reset_history import hydrate
    owned={i['uid']:i for i in items}
    if exists(db):
        for uid,attempts,successes,probability in db.execute('SELECT c.item_uid,c.attempts,c.successes,c.probability FROM equipment_chip_tuning c JOIN inventory_items i ON i.uid=c.item_uid WHERE i.owner=?',(owner,)):
            item=owned.get(uid)
            if item is not None:item['chip_tuning']=state(item['template'],[attempts,successes,probability,0])
    for item in items:
        if item['template']==TEMPLATE:item.update(hydrate(db,item))

def replace(db,owner,uid,expected,updated):
    if not db.in_transaction:raise ValueError('Chip state replacement requires transaction')
    row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone()
    if row is None or row[0]!=TEMPLATE or row[1]!=1:raise ValueError('Owned single chip state required')
    expected=state(TEMPLATE,expected);updated=state(TEMPLATE,updated)
    old=db.execute('SELECT c.attempts,c.successes,c.probability FROM equipment_chip_tuning c JOIN inventory_items i ON i.uid=c.item_uid WHERE c.item_uid=? AND i.owner=?',(uid,owner)).fetchone() if exists(db) else None
    from els_server.storage.equipment_chip_reset_history import used
    count=used(db,uid)
    if [*(old or (0,0,0)),count]!=expected:raise ValueError('Stale chip tuning state')
    if updated[3]!=count:raise ValueError('Chip tuning cannot rewrite reset history')
    if updated[:3]==[0,0,0]:
        if old:db.execute('DELETE FROM equipment_chip_tuning WHERE item_uid=?',(uid,))
        return
    ensure(db)
    db.execute('INSERT INTO equipment_chip_tuning VALUES (?,?,?,?) ON CONFLICT(item_uid) DO UPDATE SET attempts=excluded.attempts,successes=excluded.successes,probability=excluded.probability',(uid,*updated[:3]))

def require_item(item,*,chip):
    if item is None or item['group']!=1 or item['count']!=1 or item.get('identified') is False or item.get('sealed') or item.get('enhancement',0)<0:raise ValueError('Owned identified unequipped unsealed item required')
    if (item['template']!=TEMPLATE if chip else target(item['template']) is None):raise ValueError('Unsupported chip operation template')
    require_current(item);require_unlocked(item)
    if chip:
        if set(item.get('option_groups',{}))!={'1'}:raise ValueError('Chip base options required')
        source_options(item['option_groups']['1']);state(TEMPLATE,item.get('chip_tuning',[0,0,0,0]))

def receipt_success(db,operation,uid):
    row=db.execute('SELECT before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    before,after=({i['uid']:i for i in json.loads(raw)} for raw in row)
    if uid not in before or uid not in after:raise ValueError('Chip tuning receipt identity')
    old=state(TEMPLATE,before[uid].get('chip_tuning',[0,0,0,0]));new=state(TEMPLATE,after[uid].get('chip_tuning',[0,0,0,0]))
    if new[0]!=old[0]+1 or new[1]-old[1] not in (0,1):raise ValueError('Chip tuning receipt counters')
    return new[1]>old[1]

def response_changes(items,positions,uid):
    current={(i['group'],i['slot']):i for i in items};positions=list(positions)
    # A retry must describe the affected UID's current location, and retain any
    # replacement now occupying an old slot rather than clearing it.
    for i in items:
        pos=(i['group'],i['slot'])
        if i['uid']==uid and pos not in positions:positions.append(pos)
    return [(p,current.get(p)) for p in positions]

def perform(path,owner,payload,operation,*,install,account_id=None,randbelow=secrets.randbelow,encode=None):
    if type(install) is not bool:raise ValueError('Chip operation kind')
    uid,source=installation(payload) if install else (tuning(payload),None)
    kind=0x6e7 if install else 0xbb8;owner,digest=_identity(owner,kind,payload,operation)
    encode=(install_ack if install else tuning_ack) if encode is None else encode
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone():raise ValueError('Unknown chip owner')
        if account_id is not None:
            from els_server.storage.profession_state import require_owner
            require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            kwargs={} if install else dict(success=receipt_success(db,operation,uid))
            response=encode(uid,balance['ed'],response_changes(before,old,uid),**kwargs);encode_event(response)
            return [response]
        owned={i['uid']:i for i in before};item=owned.get(uid);require_item(item,chip=not install)
        positions=[(item['group'],item['slot'])]
        if install:
            chip=owned.get(source);require_item(chip,chip=True)
            if state(chip['template'],chip.get('chip_tuning',[0,0,0,0]))[0]!=catalog()['max_attempts']:
                raise ValueError('Chip installation requires all tuning attempts completed')
            previous=item.get('option_groups',{})
            if '27' in previous:armor_options(item['template'],previous['27'])
            values=armor_options(item['template'],resolved(chip));fee=catalog()['install_fee']
            positions.append((chip['group'],chip['slot']))
            ed=charge(db,owner,balance,fee);remove(db,owner,chip)
            replace_options(db,owner,uid,previous,{**previous,'27':values});kwargs={}
        else:
            updated,success,fee=advance(item,randbelow)
            ed=charge(db,owner,balance,fee)
            replace(db,owner,uid,item.get('chip_tuning',[0,0,0,0]),updated);kwargs=dict(success=success)
        after=load_items(db,owner)
        response=encode(uid,ed,response_changes(after,positions,uid),**kwargs)
        encode_event(response)  # All native BB9/6E8 records complete before receipt/commit.
        from els_server.storage.equipment_chip_reset_history import legacy
        _commit(db,operation,digest,owner,kind,positions,[legacy(i) for i in before],[legacy(i) for i in after])
        return [response]
