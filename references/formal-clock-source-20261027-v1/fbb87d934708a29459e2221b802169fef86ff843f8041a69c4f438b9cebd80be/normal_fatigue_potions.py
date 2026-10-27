"""Original196/197 ordinary-fatigue recovery, in one inventory/state writer."""
from contextlib import closing
import json,sqlite3,struct
from els_server.domain.normal_fatigue_rules import admitted,potions,read_existing,policy
from els_server.protocol.ice_messages import use_request
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage import normal_fatigue as fatigue

def recognizes(path,owner,payload,operation):
    if type(payload)is not bytes or len(payload)<8:return False
    uid=struct.unpack_from('>Q',payload)[0]
    with closing(sqlite3.connect(path,timeout=10))as db:
        r=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if r and r[0]in admitted():return True
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone()and db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=?',(operation,owner,0x196)).fetchone()and fatigue._exists(db,'normal_fatigue_operations')and db.execute('SELECT 1 FROM normal_fatigue_operations WHERE operation=? AND owner=? AND kind=?',(operation,owner,'potion')).fetchone())

def result(ed,current,changes=(),code=0):
    from els_server.domain.fashion_state import move_ack
    vector=move_ack(changes)[:-4]
    # Original197 +8 is absolute ordinary fatigue; +4 resurrection stays0.
    ack=Event(0x201,kind=0x197,payload=struct.pack('>iiii',code,0,current,0)+vector+struct.pack('>QBBBi',ed,0,0,0,0))
    events=([Event(0x201,kind=0xad8,payload=vector)]if changes else[])+[ack]
    for e in events:encode_event(e)
    return events

def perform(path,owner,account,payload,operation,*,prepare,now=None):
    req=use_request(payload)
    if req.choices or any((req.flag1,req.flag2,req.flag3,req.option)):raise ValueError('Original ordinary-fatigue single draw')
    owner,digest=_identity(owner,0x196,payload,operation)
    from els_server.storage.inventory_state import load_items
    from els_server.storage.npc_trade import balances
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');fatigue._actor(db,owner,account);prepare(db)
        old=_previous(db,operation,digest);items=load_items(db,owner);wallet=balances(db,owner)
        if old is not None:
            before_raw=db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=?',(operation,owner,0x196)).fetchone()
            before=json.loads(before_raw[0])if before_raw else[]
            if len(before)!=1 or before[0]['uid']!=req.uid:raise ValueError('Ordinary-fatigue spent UID receipt')
            read_existing(dict(before[0]));r=potions()[before[0]['template']]
            applied=fatigue._apply(db,path,owner,account,operation,'potion',dict(uid=req.uid,template=before[0]['template'],payload_sha256=digest),policy()['sha256'],r['restore'],prepare=prepare,now=now)
            if not applied['replayed']:raise ValueError('Missing original fatigue receipt')
            events=result(wallet['ed'],applied['state']['current'],current_changes(db,operation,owner,0x196,old,items));prepare(db);return events
        item=next((i for i in items if i['uid']==req.uid),None)
        if item is None or item['template']not in admitted():raise ValueError('Owned admitted ordinary-fatigue potion required')
        r=potions()[item['template']];read_existing(dict(item));require_current(item);require_unlocked(item)
        if item.get('sealed',False):raise ValueError('Sealed ordinary-fatigue potion')
        level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
        if level<r['minimum_level']:raise ValueError('Ordinary-fatigue potion minimum level')
        applied=fatigue._apply(db,path,owner,account,operation,'potion',dict(uid=req.uid,template=item['template'],payload_sha256=digest),policy()['sha256'],r['restore'],prepare=prepare,now=now)
        if applied['replayed']:raise ValueError('Orphan fatigue consumption receipt')
        after=read_existing(dict(item,count=item['count']-1))if item['count']>1 else None
        events=result(wallet['ed'],applied['state']['current'],[((item['group'],item['slot']),after)])
        if after:
            if db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=? AND count=?',(owner,req.uid,item['count'])).rowcount!=1:raise ValueError('Ordinary-fatigue potion changed')
        else:
            from els_server.storage.item_instances import remove
            remove(db,owner,item)
        _commit(db,operation,digest,owner,0x196,[(item['group'],item['slot'])],[dict(item)],[dict(after)]if after else[])
        prepare(db);return events
