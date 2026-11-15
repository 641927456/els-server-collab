"""Finite source-authoritative fishing epochs and one locked settlement writer."""
import hashlib,json,math,secrets,sqlite3,time,uuid
from contextlib import closing
from pathlib import Path
from els_server.domain.fishing_equipment import FISHING_TOWNS, SHOP_RODS, OPTIONS
from els_server.domain import demon_fishing
from els_server.storage import life_stamina as life
from els_server.storage.fishing_vip import snapshot as vip_expiry
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit

INTERVAL=35
WEIGHTS=((135933,1),(135934,9),(135935,15),(135936,25),(135937,50))
WRITER_ENABLED=True

class FishingEligibilityError(ValueError):
    def __init__(self, result, message):
        super().__init__(message)
        self.result = result

def attempt_policies(items, town):
    success = wait = endurance = 0
    for item in items.values():
        chance_bonus, wait_reduction, endurance_reduction = OPTIONS.get(item['template'], (0, 0, 0))
        success += chance_bonus
        wait += wait_reduction
        endurance += endurance_reduction
    if town == demon_fishing.DIANA_TOWN:
        success += demon_fishing.ROD_SUCCESS[items[(22, 0)]['template']]
    else:
        success += 80
    normal = dict(life=20, tool=40 * (100 - endurance) // 100,
                  interval=INTERVAL * (100 - wait) / 100, success=success)
    premium = dict(life=10, tool=40 * (50 - endurance) // 100,
                   interval=INTERVAL * (50 - wait) / 100, success=success)
    return normal, premium


def scheduled_policy(stamp, expiry, normal, premium):
    # A shortened cycle must fit inside the paid term.
    return premium if stamp + premium['interval'] < expiry else normal


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _clock(now):
    value=time.time()if now is None else now()
    if type(value)not in(int,float)or not math.isfinite(value)or value<0:raise ValueError('Fishing server clock')
    return value


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS fishing_active_epochs (
      account INTEGER PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),
      connection TEXT NOT NULL,cycle TEXT NOT NULL UNIQUE,serial INTEGER NOT NULL CHECK(serial>=0),
      started REAL NOT NULL,deadline REAL NOT NULL,source_json TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS fishing_attempts (
      account INTEGER NOT NULL,owner INTEGER NOT NULL REFERENCES characters(uid),cycle TEXT NOT NULL,
      serial INTEGER NOT NULL,operation_id TEXT NOT NULL UNIQUE,source_json TEXT NOT NULL,
      completed_at REAL NOT NULL,caught INTEGER NOT NULL CHECK(caught IN(0,1)),
      fish INTEGER,life_after INTEGER NOT NULL,PRIMARY KEY(cycle,serial))''')


def _actor(db,owner,account,guard,expected_town):
    if not db.in_transaction or not callable(guard):raise ValueError('Fishing active SQL source guard')
    guard(db);life.owner(db,owner,account)
    if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()!=(99,):
        raise FishingEligibilityError(2304, 'Fishing requires level 99')
    location=db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(owner,)).fetchone()
    if expected_town not in FISHING_TOWNS or location is None or location[0] != expected_town:
        raise FishingEligibilityError(2303, 'Fishing requires the current saved spa')
    if expected_town == demon_fishing.DIANA_TOWN:
        demon_fishing.require_access(db, owner, account)
    return location


def tools(db,owner):
    from els_server.domain.fishing_equipment import definition
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    result={}
    for item in load_items(db,owner):
        if item['group']not in(22,23):continue
        rule=definition(item['template'])
        if (item['group'],item['slot'])!=(rule['equipped'],rule['slot']):raise ValueError('Fishing original equipped location')
        require_current(item);require_unlocked(item)
        if item.get('sealed',False):raise ValueError('Fishing sealed source')
        result[(item['group'],item['slot'])]=item
    if (22,0) not in result:raise FishingEligibilityError(2298, 'Fishing rod required')
    if (23,0) not in result:raise FishingEligibilityError(2300, 'Fishing bait required')
    if result[(22,0)]['template'] not in SHOP_RODS:
        raise ValueError('Finite normal fishing rod source')
    if any(item['group'] == 22 and item['count'] != 1 for item in result.values()):
        raise ValueError('Fishing original tool count')
    return result


def require_durability(items, cost):
    if any(item['group'] == 22 and item.get('durability', 0) < cost for item in items.values()):
        raise FishingEligibilityError(2305, 'Fishing tool durability is too low')


def source_projection(items):
    # Positions and immutable identities stay bound; ordinary quantity and
    # condition change only through this cycle's authoritative transactions.
    return {str(p):dict(uid=i['uid'],template=i['template'],group=i['group'],slot=i['slot'])for p,i in items.items()}


def start(path,owner,account,connection,prepare,guard,*,expected_town,active_cycle=None,now=None):
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            location=_actor(db,owner,account,guard,expected_town)
            if not WRITER_ENABLED:raise ValueError('New fishing start held')
            stamp=_clock(now);items=tools(db,owner)
            expiry=vip_expiry(db,owner,account)
            policy=scheduled_policy(stamp,expiry,*attempt_policies(items,expected_town))
            require_durability(items,policy['tool'])
            state=life.snapshot(db,owner,account)
            if state['current']<policy['life']:raise FishingEligibilityError(2301, 'Fishing life exhausted')
            source=canonical(dict(gear=source_projection(items),location=location));ensure(db)
            if active_cycle is not None:
                old=db.execute('SELECT owner,connection,cycle,serial,started,deadline,source_json FROM fishing_active_epochs WHERE account=?',(account,)).fetchone()
                if old is None or old[:3] != (owner,connection,active_cycle) or old[6]!=source:
                    raise ValueError('Fishing active source changed')
                cycle=dict(cycle=old[2],serial=old[3],started=old[4],deadline=old[5],source_json=source)
            else:
                cycle=dict(cycle=str(uuid.uuid4()),serial=0,started=stamp,deadline=stamp+policy['interval'],source_json=source)
                db.execute('INSERT INTO fishing_active_epochs VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(account) DO UPDATE SET owner=excluded.owner,connection=excluded.connection,cycle=excluded.cycle,serial=excluded.serial,started=excluded.started,deadline=excluded.deadline,source_json=excluded.source_json',(account,owner,connection,cycle['cycle'],0,stamp,stamp+policy['interval'],source))
            answer=prepare(cycle,state);_actor(db,owner,account,guard,expected_town)
            if tools(db,owner)!=items or db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(owner,)).fetchone()!=location or not WRITER_ENABLED or vip_expiry(db,owner,account)!=expiry:raise ValueError('Fishing start source changed before commit')
            return cycle,answer


def stop(path,owner,account,connection,cycle,prepare,guard,*,expected_town):
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            _actor(db,owner,account,guard,expected_town)
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fishing_active_epochs'").fetchone():
                db.execute('DELETE FROM fishing_active_epochs WHERE account=? AND owner=? AND connection=? AND cycle=?',(account,owner,connection,cycle))
            answer=prepare();_actor(db,owner,account,guard,expected_town);return answer


def settle(path,owner,account,connection,cycle,serial,prepare,guard,*,expected_town,quest=None,now=None,randbelow=secrets.randbelow):
    operation='fishing-attempt:'+str(uuid.uuid5(uuid.UUID(cycle),str(serial)))
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            location=_actor(db,owner,account,guard,expected_town)
            ensure(db)
            old=db.execute('SELECT account,owner,source_json FROM fishing_attempts WHERE cycle=? AND serial=?',(cycle,serial)).fetchone()
            if old is not None:
                if old[:2]!=(account,owner):raise ValueError('Fishing previous owner mismatch')
                return dict(replayed=True,reply=[])
            if not WRITER_ENABLED:raise ValueError('New fishing attempt held')
            active=db.execute('SELECT owner,connection,serial,deadline,source_json FROM fishing_active_epochs WHERE account=? AND cycle=?',(account,cycle)).fetchone()
            if active is None or active[:3]!=(owner,connection,serial):raise ValueError('Fishing active source generation')
            stamp=_clock(now);due=active[3]
            if stamp<due:raise ValueError('Fishing not yet due')
            items=tools(db,owner)
            if canonical(dict(gear=source_projection(items),location=location))!=active[4]:raise ValueError('Fishing original source moved')
            expiry=vip_expiry(db,owner,account)
            normal,premium=attempt_policies(items,expected_town)
            # The saved deadline keeps a late server tick from removing VIP benefits.
            policy=premium if due<expiry else normal
            next_policy=scheduled_policy(stamp,expiry,normal,premium)
            require_durability(items,policy['tool'])
            before=load_items(db,owner);state=life.debit(db,owner,account,policy['life'],premium_at=due if policy is premium else None)
            roll=randbelow(100)
            if type(roll)is not int or not 0<=roll<100:raise ValueError('Fishing success draw')
            caught=roll<policy['success'];fish=None
            if caught:
                weights = demon_fishing.FISH_WEIGHTS if expected_town == demon_fishing.DIANA_TOWN else WEIGHTS
                total = sum(weight for _, weight in weights)
                roll=randbelow(total)
                if type(roll)is not int or not 0<=roll<total:raise ValueError('Fishing fish draw')
                for template,weight in weights:
                    roll-=weight
                    if roll<0:fish=template;break
                if fish is None:raise ValueError('Fishing finite weight mass')
            bait=items[(23,0)];remaining=bait['count']-1
            if remaining:
                if db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=? AND count=? AND bag_group=23 AND slot=0',(remaining,bait['uid'],owner,bait['count'])).rowcount!=1:raise ValueError('Fishing bait compare-and-set')
            else:
                from els_server.storage.item_instances import remove
                remove(db,owner,bait)
            consumed=[(bait['uid'],remaining)]
            from els_server.storage.equipment_durability import replace_durability
            for position,item in items.items():
                if item['group']!=22:continue
                updated=replace_durability(db,owner,item['uid'],item.get('durability',0),item['durability']-policy['tool'])
                consumed.append((item['uid'],updated))
            if caught:
                from els_server.domain.reward_rules import item_plan
                plan = [item_plan(fish,1)]
                authority = None
                if expected_town == demon_fishing.DIANA_TOWN:
                    from els_server.domain.raid_reward_items import _issue_source

                    def current_catch(writer):
                        return writer is db and _actor(writer, owner, account, guard, expected_town) == location

                    source = dict(reward_source=demon_fishing.REWARD_SOURCE, town=expected_town)
                    authority = _issue_source(db, owner, operation, 'fishing', source, plan, current_catch)
                grant_items(db,plan,owner,raid_reward_source=authority)
            after=load_items(db,owner);by={(i['group'],i['slot']):i for i in after}
            changed=sorted({(i['group'],i['slot'])for i in before+after if next((r for r in before if r['uid']==i['uid']),None)!=next((r for r in after if r['uid']==i['uid']),None)})
            changes=[(p,by.get(p))for p in changed]
            _,digest=_identity(owner,0x8b8,canonical(dict(cycle=cycle,serial=serial,source=active[4])).encode(),operation)
            db.execute('INSERT INTO fishing_attempts VALUES(?,?,?,?,?,?,?,?,?,?)',(account,owner,cycle,serial,operation,active[4],stamp,int(caught),fish,state['current']))
            notices=quest(db,operation)if quest is not None else []
            next_deadline=stamp+next_policy['interval']  # Never accrue offline/missed-deadline bursts.
            if db.execute('UPDATE fishing_active_epochs SET serial=serial+1,deadline=? WHERE account=? AND owner=? AND connection=? AND cycle=? AND serial=?',(next_deadline,account,owner,connection,cycle,serial)).rowcount!=1:raise ValueError('Fishing cycle compare-and-set')
            continuable=remaining>0 and state['current']>=next_policy['life'] and all(value>=next_policy['tool'] for _,value in consumed[1:])
            prepared_state=dict(state,continue_fishing=continuable)
            answer=prepare(caught,consumed,changes,prepared_state,notices)
            _actor(db,owner,account,guard,expected_town)
            if load_items(db,owner)!=after or life.snapshot(db,owner,account)!=state or vip_expiry(db,owner,account)!=expiry:raise ValueError('Fishing late saved state changed')
            if db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(owner,)).fetchone()!=location or not WRITER_ENABLED:raise ValueError('Fishing late source/writer changed')
            _commit(db,operation,digest,owner,0x8b8,changed,before,after)
            guard(db)
            if not WRITER_ENABLED:raise ValueError('Fishing held before final commit')
            return dict(replayed=False,reply=answer,serial=serial+1,deadline=next_deadline,life=state,continuable=continuable)

from els_server.storage.sqlite_timing import write_transaction
