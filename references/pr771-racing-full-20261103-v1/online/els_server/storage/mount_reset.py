"""Native A8E: one owned crystal, saved reroll and receipt in one transaction."""
import hashlib,json,secrets,sqlite3,struct,time
from contextlib import closing
from els_server.domain.mount_racing_rules import policy,reset
from els_server.protocol import mount_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import mount_growth
from els_server.storage.character_schema import character_uid

def perform(path,owner,account_id,payload,operation,*,prepare,randbelow=secrets.randbelow):
    owner=character_uid(owner)
    if len(payload)!=8 or not isinstance(operation,str) or not 1<=len(operation)<=160:
        raise ValueError('Mount reset request')
    uid=struct.unpack('>Q',payload)[0]
    if not 0<uid<2**63:raise ValueError('Mount reset UID')
    digest=hashlib.sha256(payload).hexdigest();p=policy()
    from els_server.storage.companion_state import ensure as companions
    from els_server.storage.mount_state import owned
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    from els_server.storage.inventory_state import load_items
    from els_server.storage.companion_receipt_inventory import delta
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prepare(db);require_active_character(db,owner);require_owner(db,owner,account_id)
        if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]<p['minimum_character_level']:
            raise ValueError('Mount racing reset character level')
        companions(db);mount=owned(db,owner,uid)
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='mount_race_busy'").fetchone()and db.execute('SELECT 1 FROM mount_race_busy WHERE uid=?',(uid,)).fetchone():raise ValueError('Racing mount cannot reset during a race')
        if 'expires_at'in mount or mount['unit']>=10000:raise ValueError('Permanent player mount required')
        db.execute('''CREATE TABLE IF NOT EXISTS mount_reset_receipts (
            owner INTEGER NOT NULL,operation TEXT NOT NULL,digest TEXT NOT NULL,
            context TEXT NOT NULL,PRIMARY KEY(owner,operation))''')
        previous=db.execute('SELECT digest,context FROM mount_reset_receipts WHERE owner=? AND operation=?',(owner,operation)).fetchone()
        saved=mount_growth.read(db,owner,uid)
        if previous:
            if previous[0]!=digest:raise ValueError('Conflicting mount reset retry')
            context=json.loads(previous[1]);answer=wire.reset_ack(mount=dict(mount,racing=saved),**delta(load_items(db,owner),context['item']))
        else:
            from els_server.domain.item_expiration import expired
            from els_server.domain.item_locks import locked
            now=int(time.time())
            items=[i for i in load_items(db,owner)if i['template']in p['reset_templates']and not expired(i,now=now)and not locked(i,now=now)]
            if not items:raise ValueError('Owned mount reset crystal required')
            item=min(items,key=lambda i:(i.get('expires_at',2**63),p['reset_templates'].index(i['template']),i['slot'],i['uid']))
            if p['reset_ed']!=0 or p['reset_quantity']!=1:raise ValueError('Unsupported mount reset fee policy')
            updated=reset(saved['experience'],saved['stats'],randbelow)
            if item['count']>1:
                db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner));remaining=dict(item,count=item['count']-1)
            else:
                from els_server.storage.item_instances import remove
                remove(db,owner,item);remaining=None
            mount_growth.save(db,owner,uid,updated)
            answer=wire.reset_ack(mount=dict(mount,racing=updated),updates=[remaining]if remaining else [],removed=None if remaining else item)
            db.execute('INSERT INTO mount_reset_receipts VALUES (?,?,?,?)',(owner,operation,digest,json.dumps(dict(item=item,policy=p['policy']),sort_keys=True)))
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        encode_event(answer);prepare(db)
        return [answer]
