"""Owned mystery shards, fee and all random results share one SQL transaction."""
import secrets,sqlite3,time
from collections import Counter
from contextlib import closing
from els_server.domain.el_shard_identification import OUTCOMES,unit_fee,outcome
from els_server.protocol.el_shard_identification_messages import request,acknowledgement
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items,grant_items,InventoryFull
from els_server.storage.item_instances import remove
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.npc_trade import balances,charge
from els_server.storage.bag_capacity import allowances
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
from els_server.domain.item_locks import require_unlocked
from els_server.domain.item_expiration import require_current

def _capacity(db,owner,before,item,quantity):
    # All six outputs have at least999 slots per stack, and this exact source
    # is bounded by999. Thus each type needs at most one newly allocated slot.
    # The cheapest first-overflow thresholds give the maximum possible number
    # of new slots over every draw distribution, before any random draw.
    if quantity>999 or any(TEMPLATE_MAX_STACKS[t]<999 for t,w in OUTCOMES):
        raise ValueError('Current shard stack bound')
    costs=sorted(1+sum(TEMPLATE_MAX_STACKS[t]-i['count'] for i in before
        if(i['template'],i['metadata'],i['group'])==(t,2,4)and'expires_at'not in i)for t,w in OUTCOMES)
    required=spent=0
    for cost in costs:
        if spent+cost>quantity:break
        spent+=cost;required+=1
    occupied=sum(i['group']==4 for i in before)-(quantity==item['count'])
    if required>allowances(db,owner)[4]-occupied:raise InventoryFull('Every shard result must fit before drawing')

def identify(path,owner,payload,operation,randbelow=secrets.randbelow,*,account_id,prepare=None,encode=acknowledgement):
    uid,quantity=request(payload);owner,digest=_identity(owner,0x206,payload,operation)
    def authorize():
        if prepare is not None:prepare()
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        authorize();require_active_character(db,owner);require_owner(db,owner,account_id)
        before=load_items(db,owner);old=_previous(db,operation,digest);balance=balances(db,owner)
        if old is not None:
            changes=current_changes(db,operation,owner,0x206,old,before)
            response=[Event(0x201,kind=0x207,payload=encode(balance['ed'],changes))]
            for event in response:encode_event(event)
            authorize();return response
        item=next((i for i in before if i['uid']==uid),None)
        if(item is None or(item['template'],item['metadata'],item['group'])!=(130047,2,4)
                or quantity>item['count']or'expires_at'in item):
            raise ValueError('Owned permanent mystery shard required')
        now=int(time.time());require_current(item,now=now);require_unlocked(item,now=now)
        _capacity(db,owner,before,item,quantity)
        # Current native InitUI price2000, then original quantity*Price display;
        # no solver item is consumed and no unadvertised free-event is opened.
        ed=charge(db,owner,balance,unit_fee()*quantity)
        rewards=Counter(outcome(randbelow(100))for _ in range(quantity))
        if quantity==item['count']:remove(db,owner,item)
        elif db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=? AND count=?',
                        (quantity,owner,uid,item['count'])).rowcount!=1:raise ValueError('Shard count changed')
        changed={}
        for template,count in sorted(rewards.items()):
            for issued in grant_items(db,[dict(template=template,metadata=2,group=4,quantity=count)],owner):changed[issued['uid']]=issued
        positions=sorted({(item['group'],item['slot'])}|{(i['group'],i['slot'])for i in changed.values()})
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        response=[Event(0x201,kind=0x207,payload=encode(ed,[(p,current.get(p))for p in positions],dict(rewards)))]
        for event in response:encode_event(event)
        _commit(db,operation,digest,owner,0x206,positions,before,after)
        authorize();return response
