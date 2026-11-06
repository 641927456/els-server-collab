"""Original 528/529 guild shop: one cart, one currency and inventory transaction."""
import struct
from els_server.domain import guild_shop_items,guild_rules
from els_server.storage import guild_system_state as system
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import remove
from els_server.storage.inventory_actions import _commit,_previous
from els_server.protocol.social_messages import Reader
from els_server.protocol.guild_system_messages import reply

KINDS=frozenset((0x528,))

def changed(changes):
    from els_server.domain.fashion_state import record,empty_record
    rows=list(changes)
    if len({tuple(p)for p,i in rows})!=len(rows):raise ValueError('Guild inventory changed positions')
    return struct.pack('>I',len(rows))+b''.join(empty_record(*p)if i is None else record(i)for p,i in rows)

def ack(coins=0,banner=0,changes=(),code=0):return reply(0x529,struct.pack('>iii',code,coins,banner)+changed(changes))

def replay(db,saved,kind,payload,operation,digest,now):
    from els_server.storage.equipment_receipt_state import current_changes
    positions=_previous(db,operation,digest)
    if positions is None:raise ValueError('Guild shop receipt lost inventory producer')
    return [ack(*system.currency(db,saved['id']),current_changes(db,operation,saved['owner'],kind,positions,load_items(db,saved['owner'])))]

def command(db,s,event,saved,operation,now):
    if s.phase!='guild_agit_ready':raise ValueError('Guild shop requires actual GuildAgit')
    r=Reader(event.payload);count=r.scalar('I')
    if not 1<=count<=len(guild_shop_items.catalog()):raise ValueError('Guild shop cart count')
    cart={};cost=[0,0,0]
    for _ in range(count):
        template=r.scalar('i');quantity=r.scalar('i');row=guild_shop_items.catalog().get(str(template))
        if row is None or template in cart or quantity<1:raise ValueError('Guild shop cart item')
        cart[template]=quantity;cost[row['currency']]+=quantity*row['cost']
    r.end()
    if (cost[0]or cost[1])and not guild_rules.permission(saved,saved['system'],3):raise ValueError('Guild fund spending authority')
    coins,banner=system.currency(db,saved['id'])
    if cost[0]>coins or cost[1]>banner:raise ValueError('Insufficient guild shop funds')
    owner=saved['owner'];before=load_items(db,owner);positions=[]
    tickets=[i for i in before if i['template']==400154]
    if sum(i['count']for i in tickets)<cost[2]:raise ValueError('Insufficient owned seed exchange tickets')
    remaining=cost[2]
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    for item in tickets:
        if not remaining:break
        require_current(item,now=now);require_unlocked(item,now=now)
        amount=min(remaining,item['count']);remaining-=amount;positions.append((item['group'],item['slot']))
        if amount==item['count']:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(amount,owner,item['uid']))
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    from els_server.domain import guild_emblems
    parts=guild_emblems.shop_parts()
    direct={400209,400210,400211}|parts.keys()
    state=saved['system'];notes=[]
    for t,q in cart.items():
        if t==400209:
            if state['fertilizer']+q>=2**31:raise ValueError('Guild fertilizer bound')
            state['fertilizer']+=q;notes.append(reply(0x809,struct.pack('>ii',0,state['fertilizer'])))
        elif t in(400210,400211):
            slots=t-400208
            if q!=1 or slots!=state['farm_slots']+1:raise ValueError('Guild farm expansion stage')
            from els_server.domain.guild_farm import water
            for member in saved['members']:
                amount=water(state,member,now);amount['count']+=1;state['watering'][str(member)]=amount
            state['farm_slots']=slots
        elif t in parts:
            definition=parts[t];offer=guild_shop_items.catalog()[str(t)]
            currency=0 if definition['NEED_ITEM_ID_FOR_ACQUISITION']==400152 else 1
            if(q!=1 or offer['currency']!=currency or offer['cost']!=definition['NEED_ITEM_NUM_FOR_ACQUISITION']):raise ValueError('Guild emblem source price/quantity')
            guild_emblems.acquire(state,definition['EMBLEM_ID'],now)
    plan=[dict(template=t,quantity=q,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t])for t,q in cart.items()if t not in direct]
    grants=grant_items(db,plan,owner)if plan else []
    positions=sorted(set(positions+[(i['group'],i['slot'])for i in grants]))
    if cost[0]or cost[1]:system.change_currency(db,saved['id'],-cost[0],-cost[1],operation,'current Myu cart',now)
    after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
    import hashlib
    digest=hashlib.sha256(str(owner).encode()+b':'+str(event.kind).encode()+b':'+event.payload).hexdigest()
    _commit(db,operation,digest,owner,event.kind,positions,before,after)
    system.write(db,saved['id'],state)
    notes.append(reply(0x7ec,struct.pack('>i',system.currency(db,saved['id'])[0])))
    if any(t in parts for t in cart):
        from els_server.protocol.guild_emblem_messages import changed as emblem_changed
        notes.append(emblem_changed(guild_emblems.rows(state,now),db.execute('SELECT name FROM characters WHERE uid=?',(owner,)).fetchone()[0]))
    if any(t in cart for t in(400210,400211)):
        from els_server.domain.guild_farm import rows
        from els_server.protocol.guild_farm_messages import updated
        notes.append(updated(rows(db,saved,now)))
    return [ack(*system.currency(db,saved['id']),[(p,current.get(p))for p in positions])],notes

def failure(kind):return ack(code=1)
