"""Local ice draws: consume, allocate reward and commit replayable result atomically."""
import hashlib,json,secrets,sqlite3
from contextlib import closing
from els_server.storage.character_schema import character_uid,stored_character_type
from els_server.domain.ice_rules import role_pools,reward_quantity
from els_server.domain.inventory_items import native_ice_catalog,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.inventory_state import ensure_inventory,load_items,grant_items
from els_server.protocol.ice_messages import use_request,result_ack,result_events
from els_server.storage.reward_state import validate_balances

# Explicit local test policy. Retail weights are not present in recovered tables.
POOL_VERSION='native-series-official-common-local-weighted-v4'
POOLS=role_pools(1)  # Backward-compatible Elsword fixture; live draws resolve owner.
POOL=POOLS[800000]

def draw(path,payload,operation_id,*,randbelow=secrets.randbelow,uid=1001):
    uid=character_uid(uid)
    if uid!=1001:operation_id=f"{uid}:{operation_id}"
    request=use_request(payload)
    if request.choices or request.option!=0 or any(x not in (0,1) for x in (request.flag1,request.flag2,request.flag3)):
        raise ValueError('Unsupported ice use mode')
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=100:raise ValueError('Invalid ice operation identity')
    digest=hashlib.sha256(payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE');ensure_inventory(db)
            db.execute('CREATE TABLE IF NOT EXISTS ice_draw_receipts (operation_id TEXT PRIMARY KEY,request_sha256 TEXT NOT NULL,consumed_uid INTEGER NOT NULL,outcome_json TEXT NOT NULL,response BLOB NOT NULL)')
            old=db.execute('SELECT request_sha256,response FROM ice_draw_receipts WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Conflicting ice retry')
                result_events(old[1])
                db.commit();return old[1]
            item=next((i for i in load_items(db,uid) if i['uid']==request.uid),None)
            pools=role_pools(stored_character_type(db,uid))
            if item is None or item['template'] not in pools or item['group']!=4:raise ValueError('Owned character-compatible ice consumable required')
            from els_server.domain.item_expiration import require_current
            require_current(item)
            pool=pools[item['template']]
            balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
            total=sum(w for _,w in pool);roll=randbelow(total)
            if type(roll) is not int or not 0<=roll<total:raise ValueError('Invalid random source')
            remaining=roll
            for template,weight in pool:
                if remaining<weight:break
                remaining-=weight
            quantity=reward_quantity(item['template'],template)
            original=dict(item);updates=[]
            if item['count']==1:
                from els_server.storage.item_expiration import forget
                forget(db,item['uid'])
                db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item['uid'],uid))
            else:
                item['count']-=1;db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',(item['count'],item['uid'],uid));updates.append(item)
            rewards=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)],uid)
            updates+=rewards
            balances['revision']+=1;validate_balances(tuple(balances[k] for k in ('ed','experience','revision')))
            response=result_ack(0,updates,balances['ed'],rewards=((template,quantity),),removed=original if original['count']==1 else None).payload
            # Validate the actual AD8/197 response before spending is committed.
            # A framing failure must roll back consumption, reward and receipt.
            result_events(response)
            outcome={'pool_version':POOL_VERSION,'pool':pool,'roll':roll,'total_weight':total,'reward_quantity':quantity,'consumed':original,'reward':rewards,'balances':balances}
            db.execute('UPDATE reward_balances SET revision=? WHERE uid=?',(balances['revision'],uid))
            db.execute('INSERT INTO ice_draw_receipts VALUES (?,?,?,?,?)',(operation_id,digest,item['uid'],json.dumps(outcome,sort_keys=True),response))
            db.commit();return response
        except BaseException:
            db.rollback();raise
