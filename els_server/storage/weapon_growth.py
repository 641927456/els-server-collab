"""Owned weapon tasks, committed-clear counters and atomic growth rewards."""
import hashlib
import json
import sqlite3
import time
from contextlib import closing

from els_server.domain import weapon_growth as rules


def _exists(db,table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS weapon_growth_progress (
        item_uid INTEGER PRIMARY KEY, stage INTEGER NOT NULL, count INTEGER NOT NULL,
        completed_json TEXT NOT NULL)''')
    if 'objectives_json' not in {r[1] for r in db.execute('PRAGMA table_info(weapon_growth_progress)')}:
        db.execute('ALTER TABLE weapon_growth_progress ADD COLUMN objectives_json TEXT')
    db.execute('''CREATE TABLE IF NOT EXISTS weapon_growth_clears (
        owner INTEGER NOT NULL, run_id TEXT NOT NULL, item_uid INTEGER NOT NULL,
        dungeon INTEGER NOT NULL, proof_hash TEXT NOT NULL, stage INTEGER NOT NULL,
        PRIMARY KEY(owner,run_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS weapon_growth_claims (
        operation_id TEXT PRIMARY KEY, owner INTEGER NOT NULL, request_hash TEXT NOT NULL,
        result_json TEXT NOT NULL)''')


def _progress(db,item):
    stage=rules.stage(item)
    q=rules.quest(stage,item['template'])
    limits={g['subquest']:g['target'] for g in q['objectives'] if g['kind']!='collect'} if q else {}
    has_table=_exists(db,'weapon_growth_progress')
    has_json=has_table and 'objectives_json' in {r[1] for r in db.execute('PRAGMA table_info(weapon_growth_progress)')}
    row=(db.execute('SELECT stage,count,completed_json,'+('objectives_json' if has_json else 'NULL')+
                    ' FROM weapon_growth_progress WHERE item_uid=?',(item['uid'],)).fetchone() if has_table else None)
    if row is None:
        return stage,{s:0 for s in limits},[0]*stage
    counts=({int(k):v for k,v in json.loads(row[3]).items()} if row[3] is not None else
            {s:row[1] for s in limits})
    completed=json.loads(row[2])
    if (row[0]!=stage or set(counts)!=set(limits)
        or any(type(n) is not int or not 0<=n<=limits[s] for s,n in counts.items())
        or len(completed)!=stage or any(type(n) is not int or n<0 for n in completed)):
        raise ValueError('Persisted weapon growth state')
    return stage,counts,completed


def _save(db,item_uid,stage,counts,completed):
    db.execute('''INSERT INTO weapon_growth_progress (item_uid,stage,count,completed_json,objectives_json)
        VALUES (?,?,0,?,?) ON CONFLICT(item_uid) DO UPDATE SET stage=excluded.stage,count=0,
        completed_json=excluded.completed_json,objectives_json=excluded.objectives_json''',
        (item_uid,stage,json.dumps(completed),json.dumps(counts,sort_keys=True)))


def _counts(q,counts,items):
    from els_server.storage.seal_quests import _inventory_count
    return {g['subquest']:min(g['target'],_inventory_count(items,g['template'])) if g['kind']=='collect'
            else counts[g['subquest']] for g in q['objectives']}


def snapshot(db,owner,items):
    active=[];completed=[]
    for item in items:
        if item['template'] not in rules.templates():
            continue
        stage,counts,times=_progress(db,item)
        for row,at in zip(rules.chain(item['template'])['quests'][:stage],times):
            completed.append(dict(id=row['id'],item_uid=item['uid'],completed_at=at))
        q=rules.quest(stage,item['template'])
        if q is not None:
            active.append(dict(id=q['id'],owner=owner,item_uid=item['uid'],started_at=0,
                               objectives=_counts(q,counts,items)))
    return dict(item_active=active,item_completed=completed)


def _actor(db,owner,account_id,guard):
    from els_server.storage.seal_quests import load_character
    from els_server.storage.item_actor import require_active_character
    if guard is not None:
        guard(db)
    character=load_character(db,owner,account_id)
    require_active_character(db,owner)
    character['account_id']=account_id
    return character


def _equipped(items,item_uid):
    item=next((i for i in items if i['uid']==item_uid),None)
    if (item is None or item['template'] not in rules.templates() or item['count']!=1
        or item['group']!=9):
        raise ValueError('Owned equipped growth weapon required')
    from els_server.domain.equipment_requirements import catalog as equipment_catalog
    from els_server.game_data import client_data
    if item['slot']!=equipment_catalog()[1][client_data().item(item['template'])['equip_position']]:
        raise ValueError('Equipped weapon slot mismatch')
    from els_server.domain.item_expiration import require_current
    require_current(item)
    return item


def record_clear(path,owner,account_id,item_uid,run_id,dungeon,proof,guard=None,*,transaction=None,no_deaths=False):
    from els_server.storage.seal_quests import _progress_connection
    with _progress_connection(path,transaction) as db:
        return _record_clear(db,owner,account_id,item_uid,run_id,dungeon,proof,guard,no_deaths)


def _record_clear(db,owner,account_id,item_uid,run_id,dungeon,proof,guard,no_deaths):
    if not isinstance(proof,bytes) or not proof:
        raise ValueError('Weapon growth clear evidence')
    digest=hashlib.sha256(proof).hexdigest()
    from els_server.storage.inventory_state import load_items
    from els_server.storage.local_clear_rules import lookup_db
    _actor(db,owner,account_id,guard)
    items=load_items(db,owner)
    item=_equipped(items,item_uid)
    receipt=(db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone()
             if _exists(db,'reward_receipts') else None)
    assessment=lookup_db(db,owner,run_id)
    if receipt is None or assessment is None:
        raise ValueError('Committed clear receipt required')
    grant=json.loads(receipt[0])
    if (grant.get('owner',1001)!=owner or not grant.get('dungeon_clear')
        or grant['dungeon_clear'][0]!=dungeon or assessment['assessment']['dungeon']!=dungeon):
        raise ValueError('Weapon growth clear owner/dungeon mismatch')
    if _exists(db,'weapon_growth_clears'):
        old=db.execute('SELECT item_uid,dungeon,proof_hash FROM weapon_growth_clears WHERE owner=? AND run_id=?',(owner,run_id)).fetchone()
        if old is not None:
            if old!=(item_uid,dungeon,digest):
                raise ValueError('Conflicting weapon growth clear replay')
            return dict(changed=False,state=snapshot(db,owner,items))
    stage,counts,completed=_progress(db,item)
    q=rules.quest(stage,item['template'])
    if not rules.eligible_clear(stage,dungeon,item['template']):
        return dict(changed=False,state=snapshot(db,owner,items))
    updated=dict(counts)
    for goal in q['objectives']:
        if dungeon in goal.get('dungeons',()) and (goal['kind']=='clear' or no_deaths is True):
            sid=goal['subquest'];updated[sid]=min(goal['target'],counts[sid]+1)
    ensure(db)
    _save(db,item_uid,stage,updated,completed)
    db.execute('INSERT INTO weapon_growth_clears VALUES (?,?,?,?,?,?)',(owner,run_id,item_uid,dungeon,digest,stage))
    if guard is not None:
        guard(db)
    return dict(changed=updated!=counts,state=snapshot(db,owner,items))


def claim(path,owner,account_id,item_uid,quest_id,operation_id,encode,guard=None,*,now=None):
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=240:
        raise ValueError('Weapon growth operation identity')
    now=int(time.time()) if now is None else now
    if type(now) is not int or not 0<now<2**63:
        raise ValueError('Weapon growth claim time')
    request_hash=hashlib.sha256(json.dumps([owner,item_uid,quest_id]).encode()).hexdigest()
    from els_server.storage.inventory_state import load_items
    from els_server.storage.equipment_options import replace
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        character=_actor(db,owner,account_id,guard)
        ensure(db)
        old=db.execute('SELECT owner,request_hash,result_json FROM weapon_growth_claims WHERE operation_id=?',(operation_id,)).fetchone()
        if old is not None:
            if old[:2]!=(owner,request_hash):
                raise ValueError('Conflicting weapon growth claim replay')
            result=json.loads(old[2])
            items=load_items(db,owner)
            result.update(items=items,updated=next((i for i in items if i['uid']==item_uid),None),
                          state=snapshot(db,owner,items),character=character,replayed=True)
            result['consumed']=[(pos,next((i for i in items if [i['group'],i['slot']]==pos),None))
                                for pos in result.get('consumed_positions',[])]
            _unit_state(db,owner,character,result)
            result['events']=encode(result)
            if guard is not None:
                guard(db)
            return result
        items=load_items(db,owner)
        item=_equipped(items,item_uid)
        stage,counts,completed=_progress(db,item)
        q=rules.quest(stage,item['template'])
        current=_counts(q,counts,items) if q else {}
        if q is None or q['id']!=quest_id or any(current[g['subquest']]<g['target'] for g in q['objectives']):
            raise ValueError('Weapon growth task is incomplete or stale')
        consumed=_consume(db,owner,q,items)
        groups=item.get('option_groups',{})
        updated_groups={**groups,'17':list(q['options'])}
        replace(db,owner,item_uid,groups,updated_groups)
        item['option_groups']=updated_groups
        completed=completed+[now]
        next_q=rules.quest(stage+1,item['template'])
        _save(db,item_uid,stage+1,{g['subquest']:0 for g in next_q['objectives'] if g['kind']!='collect'} if next_q else {},completed)
        items=load_items(db,owner)
        result=dict(items=items,updated=dict(item),state=snapshot(db,owner,items),
                    character=character,quest_id=quest_id,item_uid=item_uid,completed_at=now,replayed=False,
                    consumed=consumed,consumed_positions=[pos for pos,_ in consumed])
        _unit_state(db,owner,character,result)
        db.execute('INSERT INTO weapon_growth_claims VALUES (?,?,?,?)',(operation_id,owner,request_hash,json.dumps(result,sort_keys=True)))
        result['events']=encode(result)
        if guard is not None:
            guard(db)
        return result


def _consume(db,owner,q,items):
    from els_server.domain.item_locks import locked
    from els_server.domain.item_expiration import expired
    from els_server.domain.cartridge_registration_rules import require_unbound
    from els_server.storage.item_instances import remove
    needs={}
    for goal in q['objectives']:
        if goal['kind']=='collect':needs[goal['template']]=needs.get(goal['template'],0)+goal['target']
    changed=[]
    for template,remaining in needs.items():
        for item in items:
            if item['template']!=template or item['group']==9 or locked(item) or expired(item):continue
            require_unbound(db,item['uid'])
            take=min(remaining,item['count']);remaining-=take
            if take==item['count']:
                remove(db,owner,item);after=None
            else:
                db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(take,owner,item['uid']))
                after=dict(item,count=item['count']-take)
            changed.append(((item['group'],item['slot']),after))
            if not remaining:break
        if remaining:raise ValueError('Weapon growth materials changed')
    return changed


def _unit_state(db,owner,character,result):
    from els_server.storage.seal_quests import current_slots
    from els_server.storage.reward_state import validate_balances
    result['slots']=current_slots(db,character)
    result['balances']=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
