"""Original campaign boxes use shared inventory, expiry, preset and receipts."""
import sqlite3,struct,time
from contextlib import closing
from els_server.domain import abyss_weapon_2026 as rules
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
from els_server.storage.abyss_weapon_2026 import Campaign

def open_box(path,owner,template,payload,operation,*,account_id,prepare):
    request=use_request(payload)
    if request.option not in(0,1)or request.choices or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):
        raise ValueError('Campaign box accepts one box without client-selected class')
    owner,digest=_identity(owner,0x196,struct.pack('>i',template)+payload,operation)
    from els_server.storage.fixed_cubes import _legacy_actor
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');_legacy_actor(db,owner,account_id,prepare)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            events=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
        else:
            item=next((i for i in before if i['uid']==request.uid),None)
            if item is None or item['template']!=template or item['group']!=4:raise ValueError('Owned campaign box required')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            require_current(item);require_unlocked(item)
            cls=db.execute('SELECT unit_class FROM characters WHERE uid=?',(owner,)).fetchone()[0]
            outputs=rules.preview(template,cls);plan=[];now=int(time.time())
            for row in outputs:plan+=rules.plan(row['template'],row['quantity'])
            if template==rules.BOX:
                campaign=Campaign(db);bound=campaign.participant(account_id,owner)
                if bound['box_uid']!=item['uid'] or bound['weapon_uid']:raise ValueError('Only the exact account-issued weapon box may open')
                plan[0].update(enhancement=11,expires_at=now+90*86400)
            source=(item['group'],item['slot'])
            if item['count']==1:remove(db,owner,item)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
            grants=grant_items(db,plan,owner)
            if template==rules.BOX:
                if len(grants)!=1:raise ValueError('Single Abyss weapon grant required')
                from els_server.domain.weapon_growth import preset
                from els_server.storage.equipment_options import replace
                weapon=grants[0];replace(db,owner,weapon['uid'],weapon.get('option_groups',{}),
                    {**weapon.get('option_groups',{}),**rules.engraving_options(cls),'17':preset(weapon['template'])['options']})
                db.execute('UPDATE abyss2026_accounts SET weapon_uid=?WHERE account=?',(weapon['uid'],account_id))
            after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
            positions=sorted({source,*[(i['group'],i['slot'])for i in grants]})
            events=result(balance['ed'],[(p,current.get(p))for p in positions],[(r['template'],r['quantity'])for r in outputs])
            for event in events:encode_event(event)
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
            _commit(db,operation,digest,owner,0x196,positions,before,after)
        for event in events:encode_event(event)
        _legacy_actor(db,owner,account_id,prepare)
        return events
