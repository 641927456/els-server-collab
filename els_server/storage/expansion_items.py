"""Consume a character-owned ordinary skill coupon and unlock in one transaction."""
from contextlib import closing
import hashlib,sqlite3
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.skill_expansion import grant_ordinary
from els_server.protocol.career_messages import use_request,use_ack

ORDINARY_COUPON=274160


def use_expansion_item(path,uid,payload,operation_id):
    """Return None for other item families; replays work after the item is gone."""
    uid=character_uid(uid);item_uid=use_request(payload)
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Expansion operation identity')
    digest=hashlib.sha256(str(uid).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='expansion_use_receipts'").fetchone()
        if exists:
            old=db.execute('SELECT request_hash,bag_group,slot FROM expansion_use_receipts WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Conflicting expansion retry')
                # The old slot may now hold another item. Reconcile its current
                # contents, never replay an obsolete decrement or whole-bag NEW.
                current=next((i for i in load_items(db,uid) if (i['group'],i['slot'])==old[1:]),None)
                ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                return dict(replayed=True,response=use_ack([(old[1:],current)],ed=ed).payload)
        item=next((i for i in load_items(db,uid) if i['uid']==item_uid),None)
        if item is None or item['template']!=ORDINARY_COUPON:return None
        if item['group']!=4:raise ValueError('Expansion coupon outside owned consumable inventory')
        from els_server.domain.item_expiration import require_current
        require_current(item)
        # Reject an already unlocked character before consuming another coupon.
        grant_ordinary(db,uid)
        remaining=dict(item,count=item['count']-1) if item['count']>1 else None
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,uid))
        else:
            from els_server.storage.item_expiration import forget
            forget(db,item_uid)
            db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,uid))
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
        response=use_ack([((item['group'],item['slot']),remaining)],ORDINARY_COUPON,ed).payload
        db.execute('CREATE TABLE IF NOT EXISTS expansion_use_receipts (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, owner INTEGER NOT NULL, item_uid INTEGER NOT NULL, template INTEGER NOT NULL, bag_group INTEGER NOT NULL, slot INTEGER NOT NULL)')
        db.execute('INSERT INTO expansion_use_receipts VALUES (?,?,?,?,?,?,?)',(operation_id,digest,uid,item_uid,ORDINARY_COUPON,item['group'],item['slot']))
        return dict(replayed=False,response=response)
