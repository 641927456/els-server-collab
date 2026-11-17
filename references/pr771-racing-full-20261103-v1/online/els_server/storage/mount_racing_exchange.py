"""One original crystal exchange and current-position receipt projection."""
from contextlib import closing
import sqlite3,struct,time
from els_server.domain.mount_racing_exchange import catalog,request
from els_server.domain.reward_rules import item_plan
from els_server.domain.manufacture_requirements import inventory_candidates
from els_server.protocol.fish_exchange_messages import acknowledgement
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner


def exchange(path,owner,account_id,town,payload,operation,*,prepare):
    quantity=request(payload)
    if town not in catalog()['towns']:raise ValueError('Current Camilla village required')
    owner,digest=_identity(owner,0x223,struct.pack('>iQ',town,account_id)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prepare(db);require_active_character(db,owner);require_owner(db,owner,account_id)
        if db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(town,):raise ValueError('Saved Camilla village required')
        before=load_items(db,owner);old=_previous(db,operation,digest)
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
        if old is not None:
            changes=current_changes(db,operation,owner,0x223,old,before)
            events=[Event(0x201,kind=0x224,payload=acknowledgement(ed,changes,exchange_type=1))]
        else:
            now=int(time.time());available=inventory_candidates(before,now=now).get(714109,())
            needed=20*quantity
            if sum(count for uid,count in available)<needed:raise ValueError('Insufficient usable racing fragments')
            by_uid={i['uid']:i for i in before};positions=[]
            for uid,count in sorted(available,key=lambda p:(by_uid[p[0]]['slot'],p[0])):
                if not needed:break
                item=by_uid[uid];take=min(needed,count);needed-=take;positions.append((item['group'],item['slot']))
                if take==count:
                    from els_server.storage.item_instances import remove
                    remove(db,owner,item)
                else:db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=?',(take,uid,owner))
            gained=grant_items(db,[item_plan(714108,quantity)],owner)
            positions=list(dict.fromkeys(positions+[(i['group'],i['slot'])for i in gained]))
            after=load_items(db,owner);_commit(db,operation,digest,owner,0x223,positions,before,after)
            changes=current_changes(db,operation,owner,0x223,positions,after)
            events=[Event(0x201,kind=0x224,payload=acknowledgement(ed,changes,[(714108,quantity)],exchange_type=1))]
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        for event in events:encode_event(event)
        prepare(db)
        return events
