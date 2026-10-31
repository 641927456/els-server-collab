"""Consume one owned synergy ticket and extend its character's original timer."""
import json,sqlite3,time
from contextlib import closing
from pathlib import Path
from els_server.domain.el_search_collection_tickets import catalog,CollectionTicketError
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,owned_template
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.el_search_collection_messages import notice
from els_server.protocol.protocol_codec import encode_event

TABLE='character_search_collection_synergy_time'
MAX_SECONDS=90*86400


def expiry(db,owner,account):
    from els_server.storage.el_search_collection import exists,identity
    identity(db,owner,account)
    if not exists(db,TABLE):return 0
    row=db.execute('SELECT account_id,expires_at,updated_at FROM character_search_collection_synergy_time WHERE owner=?',(owner,)).fetchone()
    if row is None:return 0
    if row[0]!=account or any(type(v)is not int or not 0<v<2**63 for v in row[1:]) or not 0<row[1]-row[2]<=MAX_SECONDS:
        raise ValueError('Collection synergy timer integrity')
    return row[1]


def use(path,owner,account,payload,operation,guard,*,now=None):
    source=use_request(payload)
    owner,digest=_identity(owner,0x219,str(account).encode()+b':collection-ticket:'+payload,operation)
    if not callable(guard):raise ValueError('Collection ticket actor guard')
    stamp=int(time.time())if now is None else now
    if type(stamp)is not int or not 0<stamp<2**63-MAX_SECONDS:raise ValueError('Collection ticket clock')
    from els_server.storage.el_search_collection import snapshot,identity
    from els_server.storage.item_actor import require_active_character
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,owner);identity(db,owner,account)
        old=_previous(db,operation,digest)
        if old is None and owned_template(db,owner,source)not in catalog():return None
        state=snapshot(db,owner,account)
        if state is None or not state['active']:
            raise CollectionTicketError(2487,'Open the El Search Party Collection before using a synergy ticket')
        items=load_items(db,owner)
        item=next((i for i in items if i['uid']==source),None)
        ed,revision=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if old is not None:
            proof=json.loads(db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()[0])
            if len(proof)!=1 or proof[0]['uid']!=source or proof[0]['template']not in catalog() or not state['expiry']:
                raise ValueError('Collection ticket receipt source')
            events=[use_ack(current_changes(db,operation,owner,0x219,old,items),proof[0]['template'],ed),notice(state)]
            for event in events:encode_event(event)
            guard(db);return events
        if item['group']!=4 or item['metadata']!=0 or item.get('sealed',False):raise ValueError('Collection ticket owned bag')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=stamp);require_unlocked(item,now=stamp)
        updated=max(stamp,state['expiry'])+catalog()[item['template']]
        if updated>stamp+MAX_SECONDS:raise CollectionTicketError(2489,'Collection synergy duration cannot exceed90days')
        if not 0<=revision<2**63-1:raise ValueError('Collection ticket inventory revision')
        db.execute('CREATE TABLE IF NOT EXISTS character_search_collection_synergy_time (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),expires_at INTEGER NOT NULL CHECK(expires_at>0),updated_at INTEGER NOT NULL CHECK(updated_at>0))')
        db.execute('INSERT INTO character_search_collection_synergy_time VALUES (?,?,?,?) ON CONFLICT(owner) DO UPDATE SET expires_at=excluded.expires_at,updated_at=excluded.updated_at',(owner,account,updated,stamp))
        remaining=dict(item,count=item['count']-1)if item['count']>1 else None
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(source,owner))
        else:
            from els_server.storage.item_instances import remove
            remove(db,owner,item)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        state=snapshot(db,owner,account)
        position=(item['group'],item['slot'])
        events=[use_ack([(position,remaining)],item['template'],ed),notice(state)]
        for event in events:encode_event(event)
        guard(db)
        _commit(db,operation,digest,owner,0x219,[position],[item],[remaining]if remaining else [])
        return events
