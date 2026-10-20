"""One owned role-dependent box, four complete instances, one atomic receipt."""
import sqlite3,struct
from contextlib import closing
from els_server.domain.boosting_2026_participation_gear import BOX,POLICY,enabled,outputs_for
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances

def open_gear(path,owner,payload,operation):
    if not enabled():raise ValueError('Participation gear is not registered')
    request=use_request(payload)
    if request.option!=0 or request.choices or any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3)):
        raise ValueError('Participation box does not accept a client class or choice')
    owner,digest=_identity(owner,0x196,struct.pack('>i',BOX)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            return _updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
        item=next((i for i in before if i['uid']==request.uid),None)
        if item is None or item['template']!=BOX or item['group']!=4:raise ValueError('Owned participation box required')
        require_current(item);require_unlocked(item)
        role=db.execute('SELECT unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
        if role is None:raise ValueError('Participation owner missing')
        outputs=outputs_for(role[0])
        if balance['revision']>=2**63-1:raise ValueError('Participation inventory revision overflow')
        source=(item['group'],item['slot'])
        if item['count']==1:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
        grants=grant_items(db,[dict(template=r['template'],metadata=1,group=1,quantity=1,enhancement=11) for r in outputs],owner)
        if len(grants)!=4 or {r['template'] for r in grants}!={r['template'] for r in outputs}:raise ValueError('Participation gear factory changed')
        from els_server.storage.equipment_reforge import replace as reforge
        from els_server.storage.equipment_options import replace as options
        for item in grants:
            row=next(r for r in outputs if r['template']==item['template'])
            reforge(db,owner,item['uid'],[0,100,0],list(row['reforge']))
            options(db,owner,item['uid'],{},dict({'13':list(row['reforge_options'])}))
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({source,*[(i['group'],i['slot']) for i in grants]})
        events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(r['template'],1) for r in outputs])
        for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events
