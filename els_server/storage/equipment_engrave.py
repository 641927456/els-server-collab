"""Owned atomic paid engraving previews and exactly-once confirmations."""
import json,secrets,sqlite3,time
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_engrave_rules import catalog,target,require_line,material,candidate,generate,options
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_engrave_messages import request,body,acknowledge
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_options import replace as replace_options
from els_server.storage.npc_trade import balances,charge
from els_server.storage.profession_state import require_owner
from els_server.storage.manufacture_debits import apply_debits

def exists(db):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_engrave_previews'").fetchone() is not None

def ensure(db):
    if not db.in_transaction:raise ValueError('Engraving schema requires transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS equipment_engrave_previews (
      operation_id TEXT NOT NULL PRIMARY KEY CHECK(typeof(operation_id)='text' AND length(operation_id) BETWEEN 1 AND 160),
      item_uid INTEGER NOT NULL REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED CHECK(typeof(item_uid)='integer' AND item_uid>0),
      line INTEGER NOT NULL CHECK(typeof(line)='integer' AND line BETWEEN 0 AND 2),
      component INTEGER NOT NULL CHECK(typeof(component)='integer' AND component BETWEEN 0 AND 2),
      candidate_id INTEGER NOT NULL CHECK(typeof(candidate_id)='integer' AND candidate_id>0),
      source_template INTEGER NOT NULL CHECK(typeof(source_template)='integer' AND source_template IN (136040,136041,136042,136043,136044,136045,136046,136047,136048)),
      source_uid INTEGER NOT NULL CHECK(typeof(source_uid)='integer' AND source_uid>0 AND source_uid!=item_uid),
      state INTEGER NOT NULL CHECK(typeof(state)='integer' AND state BETWEEN 0 AND 2))''')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS equipment_engrave_one_pending ON equipment_engrave_previews(item_uid,line,component) WHERE state=0')

def require_item(item,*,equipment,now,component=0):
    if item is None or item.get('sealed') or item.get('enhancement',0)<0:raise ValueError('Engraving owned current unsealed item')
    require_current(item,now=now);require_unlocked(item,now=now)
    if equipment:
        if item['group']!=1 or item['count']!=1 or item.get('identified') is False or target(item['template']) is None:raise ValueError('Engraving identified bag target')
    else:
        row=material(item['template'],component)
        from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
        if (item['group'],item['metadata'])!=(row['group'],row['metadata']) or not 1<=item['count']<=TEMPLATE_MAX_STACKS[item['template']]:raise ValueError('Engraving finite ordinary source')

def receipt(db,operation):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():raise ValueError('Engraving paid receipt missing')
    row=db.execute('SELECT request_hash,owner,kind,positions_json,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None:raise ValueError('Engraving paid receipt missing')
    try:
        positions=json.loads(row[3]);before=json.loads(row[4]);after=json.loads(row[5])
        if not isinstance(before,list) or not isinstance(after,list) or any(not isinstance(i,dict) for i in before+after):raise ValueError('Engraving receipt instance arrays')
        return row[:3],positions,before,after
    except (TypeError,KeyError,json.JSONDecodeError) as exc:raise ValueError('Engraving stored receipt format') from exc

def pending(db,owner,item,line,component,*,operation=None):
    """Read only, including proof that the preview has an atomic paid receipt."""
    require_line(item['template'],line,component)
    if not exists(db):return None
    where='p.operation_id=?' if operation is not None else 'p.line=? AND p.component=? AND p.state=0'
    args=(operation,) if operation is not None else (line,component)
    rows=db.execute('SELECT p.*,i.template FROM equipment_engrave_previews p JOIN inventory_items i ON i.uid=p.item_uid WHERE i.owner=? AND p.item_uid=? AND '+where,(owner,item['uid'],*args)).fetchall()
    if len(rows)>1:raise ValueError('Engraving ambiguous active pending')
    if not rows:return None
    op,uid,stored_line,stored_component,value,template,source,status,real_template=rows[0]
    if (not isinstance(op,str) or not 1<=len(op)<=160 or any(type(v) is not int for v in rows[0][1:]) or real_template!=item['template'] or uid!=item['uid'] or (stored_line,stored_component)!=(line,component) or not 0<source<2**63 or source==uid or status not in (0,1,2)):raise ValueError('Engraving stored pending identity')
    candidate(template,component,value)
    (digest,paid_owner,kind),positions,before,after=receipt(db,op)
    if paid_owner!=owner or kind!=0x6e7 or digest!=_identity(owner,0x6e7,body(uid,line,component,source,5),op)[1]:raise ValueError('Engraving unpaid or mismatched pending')
    old={i.get('uid'):i for i in before};new={i.get('uid'):i for i in after};equipment=old.get(uid);used=old.get(source);remaining=new.get(source)
    if (equipment is None or new.get(uid)!=equipment or equipment.get('template')!=item['template'] or used is None or used.get('template')!=template or used.get('group')!=4 or used.get('metadata')!=2 or type(used.get('count')) is not int or (remaining is not None and (remaining.get('template')!=template or type(remaining.get('count')) is not int))):raise ValueError('Engraving paid source/target history')
    if used['count']-(remaining['count'] if remaining else 0)!=1:raise ValueError('Engraving preview did not consume exactly one source')
    return dict(operation=op,uid=uid,line=line,component=component,candidate=value,template=template,source_uid=source,state=status)

def changed(items,positions,affected):
    positions=list(map(tuple,positions));current={(i['group'],i['slot']):i for i in items}
    for i in items:
        p=(i['group'],i['slot'])
        if i['uid'] in affected and p not in positions:positions.append(p)
    return [(p,current.get(p)) for p in positions]

def replay_changes(db,operation,items):
    info,positions,before,after=receipt(db,operation);points=set(map(tuple,positions))
    affected={i['uid'] for i in before+after if (i['group'],i['slot']) in points}
    return changed(items,positions,affected)

def perform(path,owner,payload,operation,*,account_id,randbelow=secrets.randbelow,now=None,encode=acknowledge):
    uid,line,component,source_uid,mode=request(payload);owner,digest=_identity(owner,0x6e7,payload,operation)
    now=int(time.time()) if now is None else now
    if type(now) is not int or now<0:raise ValueError('Engraving clock')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_owner(db,owner,account_id)
        previous=_previous(db,operation,digest);before=load_items(db,owner);owned={i['uid']:i for i in before};balance=balances(db,owner);item=owned.get(uid)
        if previous is not None:
            preview=0;result=0
            if mode==5:
                result=2005
                if item is not None:
                    require_item(item,equipment=True,now=now);old=pending(db,owner,item,line,component,operation=operation)
                    if old is not None and old['state']==0:preview=old['candidate'];result=0
            response=encode(uid,balance['ed'],replay_changes(db,operation,before),mode=mode,preview=preview,result=result);encode_event(response);return [response]
        require_item(item,equipment=True,now=now);require_line(item['template'],line,component);old=pending(db,owner,item,line,component)
        groups=item.get('option_groups',{});positions=[(item['group'],item['slot'])];affected={uid};expected=item
        if mode==5:
            source=owned.get(source_uid);require_item(source,equipment=False,component=component,now=now);row=material(source['template'],component);fee=catalog()['fees'][str(row['grade'])]
            if balance['ed']<fee or balance['revision']>=2**63-1:raise ValueError('Engraving ED/revision bound')
            preview,actual_fee=generate(source['template'],component,randbelow)
            if fee!=actual_fee:raise ValueError('Engraving fee identity')
            ed=charge(db,owner,balance,fee);apply_debits(db,owner,account_id,{source['template']:1},[dict(uid=source_uid,quantity=1)],now=now)
            ensure(db);db.execute('UPDATE equipment_engrave_previews SET state=2 WHERE item_uid=? AND line=? AND component=? AND state=0',(uid,line,component))
            db.execute('INSERT INTO equipment_engrave_previews VALUES(?,?,?,?,?,?,?,0)',(operation,uid,line,component,preview,source['template'],source_uid))
            positions.append((source['group'],source['slot']));affected.add(source_uid)
        else:
            if old is None:raise ValueError('Engraving confirmation requires paid active pending')
            if source_uid:
                source=owned.get(source_uid);require_item(source,equipment=False,component=component,now=now)
                if source['template']!=old['template']:raise ValueError('Engraving confirmation material reference changed template')
            # Zero is explicitly compatible only after the above paid-history check.
            values=list(groups.get(str(14+line),[0,0,0]));values[component]=old['candidate'];updated={**groups,str(14+line):options(item['template'],14+line,values)}
            replace_options(db,owner,uid,groups,updated)
            if db.execute('UPDATE equipment_engrave_previews SET state=1 WHERE operation_id=? AND state=0',(old['operation'],)).rowcount!=1:raise ValueError('Stale engraving confirmation')
            ed=balance['ed'];preview=0;expected={**item,'option_groups':updated}
        after=load_items(db,owner)
        if next((i for i in after if i['uid']==uid),None)!=expected:raise ValueError('Engraving target changed during transaction')
        response=encode(uid,ed,changed(after,positions,affected),mode=mode,preview=preview);encode_event(response)
        _commit(db,operation,digest,owner,0x6e7,positions,before,after);return [response]
