"""Atomic opening of the explicit published2026 reward bundles, using the inventory action ledger.

No network route or automatic activity reward producer is registered here.
The authenticated caller supplies owner and operation; startup must explicitly
load the verified definition and register its inventory templates first.
"""
import sqlite3,struct
from contextlib import closing
from els_server.domain.published_2026_bundles import PublishedBundle,enabled
from els_server.protocol.protocol_codec import encode_event
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes

def open_bundle(path,owner,payload,operation,*,definition):
    if type(definition) is not PublishedBundle or enabled().get(definition.template) is not definition:
        raise TypeError('Explicit registered published bundle required')
    request=use_request(payload)
    # Current native single-use723635 sends tail1; older controlled callers send0.
    # This narrow observed-value compatibility never authorizes bulk opening.
    # Other bundle types keep their existing option0 guard.
    options=(0,1) if definition.template==723635 else (0,)
    if request.option not in options or request.choices or any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3)):
        raise ValueError('All-items bundle has no choices or option')
    owner,digest=_identity(owner,0x196,struct.pack('>i',definition.template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            return _updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
        item=next((i for i in before if i['uid']==request.uid),None)
        if item is None or item['template']!=definition.template or item['group']!=4:
            raise ValueError('Owned published bundle instance required')
        require_current(item);require_unlocked(item)
        if balance['revision']>=2**63-1:raise ValueError('Inventory revision overflow')
        source=(item['group'],item['slot'])
        if item['count']==1:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
        plan=[]
        for output in definition.outputs:
            quantity=output.quantity
            while quantity:
                delta=min(quantity,99);quantity-=delta
                plan.append(dict(template=output.template,metadata=output.metadata,group=output.group,quantity=delta))
        grants=grant_items(db,plan,owner)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({source,*[(i['group'],i['slot']) for i in grants]})
        events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(r.template,r.quantity) for r in definition.outputs])
        for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events
