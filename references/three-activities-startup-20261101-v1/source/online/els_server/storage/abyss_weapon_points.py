"""Consume existing owned10P items through the shared operation receipt."""
from els_server.storage.abyss_weapon_2026 import Campaign
from els_server.domain import abyss_weapon_2026 as rules
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.career_messages import use_ack
from els_server.storage.npc_trade import balances

def use(db,account,owner,item_uid,payload,operation):
    owner,digest=_identity(owner,0x219,payload,operation);t=Campaign(db)
    row=t.participant(account,owner);before=load_items(db,owner);balance=balances(db,owner)
    old=_previous(db,operation,digest)
    if old is not None:return use_ack(current_changes(db,operation,owner,0x219,old,before),template=rules.POINT_ITEM,ed=balance['ed'])
    item=next((i for i in before if i['uid']==item_uid),None)
    if item is None or item['template']!=rules.POINT_ITEM or item['group']!=4:raise ValueError('Owned Abyss point item required')
    if row['points']==500:raise ValueError('Abyss points already full')
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    require_current(item);require_unlocked(item)
    if item['count']==1:remove(db,owner,item)
    else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,owner))
    t.db.execute('UPDATE abyss2026_accounts SET points=min(points+10,500)WHERE account=?',(account,))
    after=load_items(db,owner);position=(item['group'],item['slot'])
    current=next((i for i in after if(i['group'],i['slot'])==position),None)
    answer=use_ack([(position,current)],template=rules.POINT_ITEM,ed=balance['ed'])
    from els_server.protocol.protocol_codec import encode_event
    encode_event(answer)
    db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
    _commit(db,operation,digest,owner,0x219,[position],before,after)
    return answer
