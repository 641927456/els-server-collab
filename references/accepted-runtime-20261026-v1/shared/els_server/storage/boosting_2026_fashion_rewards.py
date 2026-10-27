"""One committed role-specific opening produces timed instances exactly once."""
import sqlite3,struct,time
from contextlib import closing
from els_server.domain.boosting_2026_fashion_rewards import BOXES,outputs_for
from els_server.domain.item_expiration import require_current,validate
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
from els_server.storage.luciel_state import active_state

def open_fashion(path,owner,template,payload,operation,*,now=None):
    request=use_request(payload)
    if template not in BOXES or request.option or request.choices or any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3)):
        raise ValueError('Role fashion90 box has no client-selected reward')
    owner,digest=_identity(owner,0x196,struct.pack('>i',template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prior=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if prior is not None:return _updates(current_changes(db,operation,owner,0x196,prior,before))+result(balance['ed'])
        source=next((i for i in before if i['uid']==request.uid),None)
        if source is None or source['template']!=template or source['group']!=4:raise ValueError('Owned fashion90 source box required')
        epoch=int(time.time()) if now is None else now
        if type(epoch) is not int or epoch<0:raise ValueError('Fashion90 opening epoch')
        deadline=validate(epoch+90*86400);require_current(source,now=epoch);require_unlocked(source,now=epoch)
        character=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
        if character is None:raise ValueError('Fashion90 owner missing')
        active=active_state(db,owner)['active_unit'] if character[0]==10 else 0
        if request.flag2!=active:raise ValueError('Fashion90 use active state mismatch')
        outputs=outputs_for(template,character[1],active)
        if balance['revision']>=2**63-1:raise ValueError('Fashion90 inventory revision overflow')
        position=(source['group'],source['slot'])
        if source['count']==1:remove(db,owner,source)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(source['uid'],owner))
        grants=grant_items(db,[dict(template=r['template'],metadata=r['metadata'],group=27,quantity=1,expires_at=deadline) for r in outputs],owner)
        if len(grants)!=len(outputs) or any(i['count']!=1 or i['expires_at']!=deadline for i in grants):raise ValueError('Fashion90 complete timed instance factory')
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=sorted({position,*[(i['group'],i['slot']) for i in grants]})
        events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(r['template'],1) for r in outputs])
        for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events
