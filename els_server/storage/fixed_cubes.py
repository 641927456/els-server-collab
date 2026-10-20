"""Consume one owned fixed cube and deliver its original contents atomically."""
import secrets,sqlite3,struct
from contextlib import closing
from els_server.domain.cubes import catalog
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
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


def open_cube(path,owner,expected_template,payload,operation,randbelow=secrets.randbelow):
    from els_server.domain.published_2026_bundles import enabled
    definition=enabled().get(expected_template)
    if definition is not None:
        from els_server.storage.published_2026_bundles import open_bundle
        return open_bundle(path,owner,payload,operation,definition=definition)
    from els_server.domain.boosting_2026_force_rewards import boxes as force_boxes
    if expected_template in force_boxes():
        from els_server.storage.boosting_2026_force_rewards import open_box
        return open_box(path,owner,expected_template,payload,operation)
    from els_server.domain.boosting_2026_participation_gear import BOX,enabled as gear_enabled
    if expected_template==BOX and gear_enabled():
        from els_server.storage.boosting_2026_participation_gear import open_gear
        return open_gear(path,owner,payload,operation)
    from els_server.domain.boosting_2026_fashion_rewards import BOXES,entries as fashion_entries
    if expected_template in BOXES and fashion_entries():
        from els_server.storage.boosting_2026_fashion_rewards import open_fashion
        return open_fashion(path,owner,expected_template,payload,operation)
    request=use_request(payload)
    if (request.option!=0 or any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3))
        or expected_template not in catalog()):raise ValueError('Unsupported fixed cube use')
    row=catalog()[expected_template]
    if row['selection_count']:
        if len(request.choices)!=1:raise ValueError('Select exactly one native cube item')
        output=next((e for e in row['entries'] if e['template']==request.choices[0]),None)
        if output is None:raise ValueError('Choice is outside this cube')
    else:
        if request.choices:raise ValueError('Fixed cube does not accept a choice')
        output=None if row.get('random') else row['entries'][0]
    owner,digest=_identity(owner,0x196,struct.pack('>i',expected_template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            return _updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
        item=next((i for i in before if i['uid']==request.uid),None)
        if item is None or item['template']!=expected_template or item['group']!=4:
            raise ValueError('Fixed cube does not match owned previewed instance')
        require_current(item);require_unlocked(item)
        if balance['revision']>=2**63-1:raise ValueError('Fixed cube revision overflow')
        if row.get('random'):
            from els_server.domain.regional_boss_cubes import draw
            output=draw(row,randbelow(10000))
        source=(item['group'],item['slot'])
        if item['count']==1:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
        quantity=output['quantity'];plan=[]
        while quantity:
            delta=min(quantity,99);quantity-=delta
            plan.append(dict(template=output['template'],metadata=VERIFIED_TEMPLATES[output['template']],
                group=TEMPLATE_BAG_GROUPS[output['template']],quantity=delta))
        grants=grant_items(db,plan,owner)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({source,*[(i['group'],i['slot']) for i in grants]})
        events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(output['template'],output['quantity'])])
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events
