"""Owned finite reforge/life states and atomic current-UID transaction receipts."""
import json,secrets,sqlite3,time
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_reforge_rules import DEFAULT,catalog,target,state,validate_instance,expected_options,demand,profession_fee,advance,restore,guaranteed
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_reforge_messages import request,acknowledge,restore_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_options import replace as replace_options
from els_server.storage.npc_trade import balances,charge
from els_server.storage.profession_state import require_owner
from els_server.storage.manufacture_debits import apply_debits

def exists(db):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_reforge_states'").fetchone() is not None

def ensure(db):
    if not db.in_transaction:raise ValueError('Reforge schema requires transaction')
    # SQLite CHECK cannot join inventory to recover the real template/class.
    # Keep the approved four-column schema portable; state()/attach()/replace()
    # enforce the stricter original actual-class threshold on every owned path.
    bounds=catalog()['global_failure_bounds_by_level']
    maximum='CASE level '+''.join(f'WHEN {level} THEN {int(bounds[str(level)])} ' for level in range(22))+'ELSE -1 END'
    db.execute('''CREATE TABLE IF NOT EXISTS equipment_reforge_states (
      item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
      level INTEGER NOT NULL CHECK(typeof(level)='integer' AND level BETWEEN 0 AND 21),
      life INTEGER NOT NULL CHECK(typeof(life)='integer' AND life BETWEEN 0 AND 100),
      failures INTEGER NOT NULL CHECK(typeof(failures)='integer' AND failures>=0 AND failures<=('''+maximum+')))')

def attach(db,items,owner):
    if not exists(db):return
    owned={item['uid']:item for item in items}
    for uid,level,life,failures in db.execute('SELECT r.item_uid,r.level,r.life,r.failures FROM equipment_reforge_states r JOIN inventory_items i ON i.uid=r.item_uid WHERE i.owner=?',(owner,)):
        if uid in owned:owned[uid]['reforge']=state(owned[uid]['template'],[level,life,failures])

def replace(db,owner,uid,expected,updated):
    if not db.in_transaction:raise ValueError('Reforge state replacement requires transaction')
    row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone()
    if row is None or row[1]!=1:raise ValueError('Owned single reforge target required')
    expected=state(row[0],expected);updated=state(row[0],updated)
    old=db.execute('SELECT r.level,r.life,r.failures FROM equipment_reforge_states r JOIN inventory_items i ON i.uid=r.item_uid WHERE r.item_uid=? AND i.owner=?',(uid,owner)).fetchone() if exists(db) else None
    if (list(old) if old else DEFAULT)!=expected:raise ValueError('Stale reforge state')
    if updated==DEFAULT:
        if old:db.execute('DELETE FROM equipment_reforge_states WHERE item_uid=?',(uid,))
        return
    ensure(db)
    db.execute('INSERT INTO equipment_reforge_states VALUES(?,?,?,?) ON CONFLICT(item_uid) DO UPDATE SET level=excluded.level,life=excluded.life,failures=excluded.failures',(uid,*updated))

def require_item(item,*,equipment,now,restore_target=False):
    if item is None or item.get('sealed') or item.get('enhancement',0)<0:raise ValueError('Reforge current unsealed instance required')
    require_current(item,now=now)
    # Original2020 Hongye lock exception is for life restoration only.
    # Other families retain their existing lock gate until independently proved.
    if not (equipment and restore_target is True and (target(item['template']) or {}).get('reforge_class')==1):
        require_unlocked(item,now=now)
    if equipment:
        if item['group'] not in (1,9) or item['count']!=1 or item.get('identified') is False or target(item['template']) is None:raise ValueError('Reforge identified owned bag target required')
        state(item['template'],item.get('reforge',DEFAULT));validate_instance(item)
    else:
        row=catalog()['materials'].get(str(item['template']))
        if row is None or (item['group'],item['metadata'])!=(row['group'],row['metadata']):raise ValueError('Reforge finite material required')

def allocation(items,requirements,now):
    result=[]
    for template,needed in requirements.items():
        for item in sorted((i for i in items if i['template']==template),key=lambda i:i['uid']):
            try:require_item(item,equipment=False,now=now)
            except ValueError:continue
            take=min(needed,item['count'])
            if take:result.append(dict(uid=item['uid'],quantity=take));needed-=take
            if not needed:break
        if needed:raise ValueError('Insufficient current reforge materials')
    return result

def receipt_details(db,operation,uid,*,restoration):
    row=db.execute('SELECT positions_json,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    positions={tuple(p) for p in json.loads(row[0])};before=json.loads(row[1]);after=json.loads(row[2])
    affected={i['uid'] for i in before+after if (i['group'],i['slot']) in positions}
    if restoration:return affected,0
    b=next((i for i in before if i['uid']==uid),None);a=next((i for i in after if i['uid']==uid),None)
    if a is None or b is None or a['template']!=b['template']:raise ValueError('Reforge receipt target identity')
    old=state(b['template'],b.get('reforge',DEFAULT));new=state(a['template'],a.get('reforge',DEFAULT))
    paid_life=new[1]==old[1]-catalog()['life_per_attempt']
    free_guarantee=(new[1]==old[1] and guaranteed(b['template'],old)
        and new[0]==old[0]+1 and new[2]==0)
    # Retain already committed paid guarantee receipts from earlier releases.
    if not (paid_life or free_guarantee):raise ValueError('Reforge receipt life transition')
    if new[0]==old[0]+1 and new[2]==0:return affected,1
    if new[0]==old[0] and new[2]==old[2]+1:return affected,2
    raise ValueError('Reforge receipt outcome transition')

def changes(items,positions,affected):
    positions=list(positions);current={(i['group'],i['slot']):i for i in items}
    for i in items:
        pos=(i['group'],i['slot'])
        if i['uid'] in affected and pos not in positions:positions.append(pos)
    return [(p,current.get(p)) for p in positions]

def perform(path,owner,payload,operation,*,restoration,account_id,randbelow=secrets.randbelow,now=None,encode=None):
    if type(restoration) is not bool:raise ValueError('Reforge operation kind')
    parsed=request(payload,restoration=restoration);uid=parsed[0];kind=0x8d9 if restoration else 0x8d5
    owner,digest=_identity(owner,kind,payload,operation);now=int(time.time()) if now is None else now
    if type(now) is not int or now<0:raise ValueError('Reforge transaction clock')
    encode=(restore_ack if restoration else acknowledge) if encode is None else encode
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner);owned={i['uid']:i for i in before}
        if old is not None:
            affected,status=receipt_details(db,operation,uid,restoration=restoration);change=changes(before,old,affected)
            current=owned.get(uid);level=state(current['template'],current.get('reforge',DEFAULT))[0] if current is not None else 0
            response=encode(change) if restoration else encode(uid,balance['ed'],level,status,change)
            encode_event(response);return [response]
        item=owned.get(uid);require_item(item,equipment=True,now=now,restore_target=restoration);prior=state(item['template'],item.get('reforge',DEFAULT));groups=item.get('option_groups',{})
        if restoration:
            source=owned.get(parsed[1]);quantity=parsed[2];require_item(source,equipment=False,now=now)
            updated=restore(item,source['template'],quantity)
            if quantity>source['count']:raise ValueError('Reforge restore stack overdraw')
            requirements={source['template']:quantity};debits=[dict(uid=source['uid'],quantity=quantity)];ed=balance['ed'];status=0
        else:
            requirements,fee=demand(item['template'],prior,parsed[1]);debits=allocation(before,requirements,now)
            if len(parsed)==3:
                # Full gauge is already free; the native UI does not send the
                # coupon bit there. Never burn a coupon for that forged input.
                if guaranteed(item['template'],prior):raise ValueError('Full guarantee does not consume ED coupons')
                from els_server.domain.equipment_reforge_coupons import allocate as coupon_allocation
                extra,owned_coupon=coupon_allocation(before,target(item['template'])['reforge_class'],now=now)
                if set(extra)&set(requirements):raise ValueError('Coupon/material identity overlap')
                requirements={**requirements,**extra};debits+=owned_coupon;fee=0
            if fee:
                from els_server.storage.profession_state import snapshot as profession_snapshot
                fee=profession_fee(fee,profession_snapshot(db,owner,account_id)['state'])
            if fee>balance['ed'] or (fee and balance['revision']>=2**63-1):raise ValueError('Reforge ED/revision bound')
            updated,success=advance(item,randbelow)
            ed=charge(db,owner,balance,fee) if fee else balance['ed'];status=1 if success else 2
        affected={uid,*[row['uid'] for row in debits]};positions=[(i['group'],i['slot']) for i in before if i['uid'] in affected]
        apply_debits(db,owner,account_id,requirements,debits,now=now)
        replace_options(db,owner,uid,groups,{**groups,'13':expected_options(item['template'],updated[0])})
        replace(db,owner,uid,prior,updated)
        after=load_items(db,owner);change=changes(after,positions,affected)
        response=encode(change) if restoration else encode(uid,ed,updated[0],status,change)
        encode_event(response)
        _commit(db,operation,digest,owner,kind,positions,before,after)
        return [response]
