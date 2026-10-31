"""Original deterministic Force exchanges, with character weekly quota."""
from contextlib import closing
from pathlib import Path
import json,sqlite3,struct,time
from els_server.domain.native_force_catalog import catalog
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.manufacture_requirements import inventory_candidates
from els_server.protocol.purifier_exchange_messages import ExchangeRequest
from els_server.protocol.fish_exchange_messages import acknowledgement
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.manufacture_quota import window

EXCHANGES_ENABLED=True

def request(payload):
    if not isinstance(payload,bytes)or len(payload)!=37:raise ValueError('Force exchange request length')
    r=ExchangeRequest(*struct.unpack('>iQiiiiiBi',payload))
    rows=[x for x in catalog()['exchanges']if (x['house'],x['source'],x['type'],x['source_quantity'])==(r.house,r.source,r.exchange_type,r.source_quantity)and (r.destination==x['destination']if r.exchange_type==3 else r.destination==0)]
    if (len(rows)!=1 or r.source_uid!=0 or r.source_quantity!=rows[0]['source_quantity']or
        r.native_flag!=1 or r.native_index!=0 or not 1<=r.quantity<=999):raise ValueError('Unknown native Force exchange')
    return r,rows[0]

def authorize_output(template,authority):
    if authority is None:return False
    from els_server.domain.raid_reward_items import validate_source
    a=validate_source(authority);source=json.loads(a._source)
    if source.get('reward_source')!='native-force-npc-exchange-v1':return False
    rows=[r for r in catalog()['exchanges']if r==source.get('rule')]
    if (a.kind!='box'or len(rows)!=1 or template!=rows[0]['destination']or source.get('owner')!=a.owner
        or source.get('operation')!=a.operation or source.get('town')not in catalog()['npc_towns'][str(rows[0]['house'])]):raise ValueError('Force exchange source identity')
    a.validate_template(template)
    return True

def exchange(path,owner,town,payload,operation,*,account_id,authorize,now=None):
    r,rule=request(payload)
    if town not in catalog()['npc_towns'][str(r.house)]:raise ValueError('Force NPC town')
    output=rule['destination']
    now=int(time.time())if now is None else now
    owner,digest=_identity(owner,0x223,struct.pack('>i',town)+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        def guard(writer):
            return bool(authorize()is True and writer.execute('SELECT 1 FROM character_owners WHERE uid=? AND account_id=?',(owner,account_id)).fetchone()and writer.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()==(town,))
        if not guard(db):raise ValueError('Force exchange authority')
        old=_previous(db,operation,digest);before=load_items(db,owner)
        balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
        if old is not None:
            changes=current_changes(db,operation,owner,0x223,old,before)
            return [Event(0x201,kind=0x224,payload=acknowledgement(balance['ed'],changes,exchange_type=r.exchange_type))]
        if not EXCHANGES_ENABLED:raise ValueError('New Force exchanges paused')
        if rule.get('weekly_limit'):
            begin,_=window(now,region='CN')
            db.execute('''CREATE TABLE IF NOT EXISTS native_force_exchange_quota(owner INTEGER NOT NULL,destination INTEGER NOT NULL,period INTEGER NOT NULL,used INTEGER NOT NULL CHECK(used=1),PRIMARY KEY(owner,destination,period))''')
            if r.quantity!=1 or db.execute('SELECT 1 FROM native_force_exchange_quota WHERE owner=? AND destination=? AND period>=?',(owner,output,begin)).fetchone():raise ValueError('Force weekly exchange exhausted')
            db.execute('INSERT INTO native_force_exchange_quota VALUES(?,?,?,1)',(owner,output,begin))
        demand=rule['source_quantity']*r.quantity;candidates=inventory_candidates(before,now=now).get(r.source,())
        if sum(n for uid,n in candidates)<demand:raise ValueError('Insufficient Force exchange materials')
        by_uid={i['uid']:i for i in before};positions=[]
        for uid,count in sorted(candidates,key=lambda p:(by_uid[p[0]]['group'],by_uid[p[0]]['slot'])):
            if not demand:break
            item=by_uid[uid];take=min(count,demand);demand-=take;positions.append((item['group'],item['slot']))
            if take==count:remove(db,owner,item)
            elif db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=? AND count=?',(take,uid,owner,count)).rowcount!=1:raise ValueError('Force material stack changed')
        plan=[dict(template=output,metadata=VERIFIED_TEMPLATES[output],group=TEMPLATE_BAG_GROUPS[output],quantity=r.quantity)]
        from els_server.domain.raid_reward_items import _issue_source
        source=_issue_source(db,owner,operation,'box',dict(reward_source='native-force-npc-exchange-v1',owner=owner,operation=operation,town=town,rule=rule),plan,guard)
        changes=grant_items(db,plan,owner,raid_reward_source=source)
        positions=list(dict.fromkeys(positions+[(i['group'],i['slot'])for i in changes]));after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        wire=acknowledgement(balance['ed'],[(p,current.get(p))for p in positions],[(output,r.quantity)],exchange_type=r.exchange_type)
        response=[Event(0x201,kind=0x224,payload=wire)]
        for e in response:encode_event(e)
        if not guard(db):raise ValueError('Force exchange authority expired')
        _commit(db,operation,digest,owner,0x223,positions,before,after)
        return response
