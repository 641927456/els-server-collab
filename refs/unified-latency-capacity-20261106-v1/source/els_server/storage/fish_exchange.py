"""Consume held original fish and save original exchange awards atomically."""
import sqlite3,time,secrets,struct
from collections import Counter
from contextlib import closing
from pathlib import Path
from els_server.domain.fish_exchange_rules import recipe
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances
from els_server.protocol import fish_exchange_messages as wire
from els_server.protocol.protocol_codec import Event,encode_event

WRITES_ENABLED=True

def exchange(path,owner,payload,operation,*,account_id,guard,now=None):
    r=wire.request(payload);rows=recipe(r)
    if not callable(guard):raise ValueError('Fish exchange actor guard required')
    if type(account_id)is not int or account_id<=0:raise ValueError('Fish exchange account')
    owner,digest=_identity(owner,0x223,b'House40256:'+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,owner)
        if not db.execute('SELECT 1 FROM character_owners WHERE uid=? AND account_id=?',(owner,account_id)).fetchone():raise ValueError('Fish exchange owner')
        location=db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(owner,)).fetchone()
        if location is None or location[0]!=1500:raise ValueError('Fish exchange current House40256 scene')
        def check():
            guard(db)
            if db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(owner,)).fetchone()!=location:raise ValueError('Fish exchange location changed')
        before=load_items(db,owner)
        balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
        old=_previous(db,operation,digest)
        if old is not None:
            changes=current_changes(db,operation,owner,0x223,old,before)
            answer=[Event(0x201,kind=0x224,payload=wire.acknowledgement(balance['ed'],changes,exchange_type=r.exchange_type))]
            for event in answer:encode_event(event)
            check();return answer
        if not WRITES_ENABLED:raise ValueError('New fish exchange held')
        if now is None:now=int(time.time())
        if type(now)is not int or now<0:raise ValueError('Fish exchange clock')
        candidates=[]
        for item in before:
            if item['template']!=r.source or item['group']!=21:continue
            try:require_current(item,now=now);require_unlocked(item)
            except ValueError:continue
            candidates.append(item)
        demand=r.source_quantity*r.quantity
        if sum(i['count']for i in candidates)<demand:raise ValueError('Insufficient unlocked held original fish')
        # Draw only after owned source quantity validates, under this write lock.
        erp_source=None
        from els_server.domain.fish_exchange_erp import begin,supports
        if supports(r):erp_source=begin(db,owner,account_id,payload,operation,before,guard)
        awards=Counter()
        for _ in range(r.quantity):
            if r.exchange_type==2:
                roll=secrets.randbelow(100);chosen=None
                if erp_source is not None:erp_source.draw(roll)
                for row in rows:
                    roll-=row['rate']
                    if roll<0:chosen=row;break
                if chosen is None:raise ValueError('Original fish exchange rate sum')
            else:
                chosen=rows[0]
                if erp_source is not None:erp_source.choose(chosen)
            awards[chosen['destination']]+=chosen['quantity']
        positions=[]
        for item in sorted(candidates,key=lambda i:(i['slot'],i['uid'])):
            if not demand:break
            take=min(demand,item['count']);demand-=take;positions.append((item['group'],item['slot']))
            if take==item['count']:remove(db,owner,item)
            elif db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=? AND count=?',(take,item['uid'],owner,item['count'])).rowcount!=1:raise ValueError('Fish exchange source changed')
        grants=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=min(999,n-offset))for t,n in sorted(awards.items())for offset in range(0,n,999)]
        added=grant_items(db,grants,owner,fish_erp_source=erp_source)
        positions=list(dict.fromkeys(positions+[(i['group'],i['slot'])for i in added]))
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        changes=[(p,current.get(p))for p in positions]
        answer=[Event(0x201,kind=0x224,payload=wire.acknowledgement(balance['ed'],changes,sorted(awards.items()),exchange_type=r.exchange_type))]
        for event in answer:encode_event(event)
        check()
        if erp_source is not None:erp_source.verify_after()
        if not WRITES_ENABLED:raise ValueError('Fish exchange held before commit')
        _commit(db,operation,digest,owner,0x223,positions,before,after)
        from els_server.storage.account_fishing_tasks_scope import record_exchange
        notices=record_exchange(db,owner,account_id,operation,payload,guard)
        for event in notices:encode_event(event)
        check()
        if erp_source is not None:erp_source.verify_after()
        if not WRITES_ENABLED:raise ValueError('Fish exchange held after task notification')
        return answer+notices
