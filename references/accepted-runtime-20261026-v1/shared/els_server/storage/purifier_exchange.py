"""Owned purifier stacks to deterministic NPC goods in one saved transaction."""
from contextlib import closing
import sqlite3
import struct
import time
from pathlib import Path
from els_server.domain.purifier_exchange_rules import recipe
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.manufacture_requirements import inventory_candidates
from els_server.protocol.purifier_exchange_messages import request, acknowledgement
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.reward_state import validate_balances
from els_server.storage.character_schema import stored_character_type


def exchange(path, owner, town, payload, operation, *, account_id, now=None):
    r=request(payload);rule=recipe(r)
    if town!=20013:
        raise ValueError('Purifier exchange requires the current NPC town')
    if now is None:now=int(time.time())
    if type(now) is not int or now<0 or type(account_id) is not int or not 1<=account_id<2**63:
        raise ValueError('Purifier exchange clock')
    owner,digest=_identity(owner,0x223,struct.pack('>i',town)+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        stored_character_type(db,owner)
        if not db.execute('SELECT 1 FROM character_owners WHERE uid=? AND account_id=?',(owner,account_id)).fetchone():
            raise ValueError('Purifier exchange character owner mismatch')
        if db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(town,):
            raise ValueError('Purifier exchange saved town mismatch')
        old=_previous(db,operation,digest)
        before=load_items(db,owner)
        balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
        if old is not None:
            # Refresh current affected slots (including moved/replaced rows),
            # never replay old rewards or a historical currency balance.
            changes=current_changes(db,operation,owner,0x223,old,before)
            return [Event(0x201,kind=0x224,payload=acknowledgement(balance['ed'],changes))]
        demand=rule['source_quantity']*r.quantity
        candidates=inventory_candidates(before,now=now).get(r.source,())
        if sum(n for uid,n in candidates)<demand:
            raise ValueError('Insufficient current unlocked owned purifier stacks')
        by_uid={i['uid']:i for i in before};positions=[]
        # Native sourceUID0 selects a fungible stack material by template.
        # Stable bag order is a local allocation policy, not a retail UID rule.
        for uid,count in sorted(candidates,key=lambda p:(by_uid[p[0]]['group'],by_uid[p[0]]['slot'])):
            if not demand:break
            item=by_uid[uid];take=min(count,demand);demand-=take
            positions.append((item['group'],item['slot']))
            if take==count:remove(db,owner,item)
            elif db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=? AND count=?',(take,uid,owner,count)).rowcount!=1:
                raise ValueError('Purifier exchange stack changed')
        changes=grant_items(db,[dict(template=r.destination,metadata=VERIFIED_TEMPLATES[r.destination],group=TEMPLATE_BAG_GROUPS[r.destination],quantity=r.quantity)],owner)
        positions=list(dict.fromkeys(positions+[(i['group'],i['slot']) for i in changes]))
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        changes=[(p,current.get(p)) for p in positions]
        wire=acknowledgement(balance['ed'],changes,[(r.destination,r.quantity)])
        response=[Event(0x201,kind=0x224,payload=wire)]
        for event in response:encode_event(event)
        _commit(db,operation,digest,owner,0x223,positions,before,after)
        return response
