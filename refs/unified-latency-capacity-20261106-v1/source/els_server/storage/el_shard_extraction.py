"""Exact owned shard UID conversion in the original inventory transaction."""
import sqlite3,time
from contextlib import closing
from els_server.protocol.el_shard_messages import request,acknowledgement
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import remove
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.domain.item_locks import require_unlocked
from els_server.domain.item_expiration import require_current

def extract(path,owner,payload,operation,*,account_id,prepare=None,encode=acknowledgement):
    uid,quantity=request(payload)
    owner,digest=_identity(owner,0x45e,payload,operation)
    def authorize():
        if prepare is not None:prepare()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        authorize();require_active_character(db,owner);require_owner(db,owner,account_id)
        before=load_items(db,owner);old=_previous(db,operation,digest)
        if old is not None:
            changes=current_changes(db,operation,owner,0x45e,old,before)
            # Current slots only: no new decrement, UID, or earned-item popup.
            response=[Event(0x201,kind=0x45f,payload=encode(changes))]
            for event in response:encode_event(event)
            authorize();return response
        item=next((i for i in before if i['uid']==uid),None)
        if (item is None or item['template'] not in range(130048,130054)
                or (item['metadata'],item['group'])!=(2,4) or quantity>item['count']
                or 'expires_at' in item or quantity>0x7fffffff//3):
            raise ValueError('Exact owned permanent elemental shard required')
        now=int(time.time());require_current(item,now=now);require_unlocked(item,now=now)
        if quantity==item['count']:remove(db,owner,item)
        elif db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=? AND count=?',
                        (quantity,owner,uid,item['count'])).rowcount!=1:
            raise ValueError('El Shard source count changed')
        # Existing six identified shards retain the archived CN1->3 conversion;
        # current native client owns the dialog, notification and skill effect.
        remaining=quantity*3;changed={}
        while remaining:
            count=min(999,remaining)
            for issued in grant_items(db,[dict(template=130208,metadata=2,group=4,quantity=count)],owner):
                changed[issued['uid']]=issued
            remaining-=count
        positions=sorted({(item['group'],item['slot'])}|{(i['group'],i['slot']) for i in changed.values()})
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        changes=[(p,current.get(p)) for p in positions]
        response=[Event(0x201,kind=0x45f,payload=encode(changes,{130208:quantity*3}))]
        for event in response:encode_event(event)
        _commit(db,operation,digest,owner,0x45e,positions,before,after)
        authorize();return response
