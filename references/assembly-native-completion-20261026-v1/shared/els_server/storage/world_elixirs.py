"""Atomic owned elixir consumption and original absolute-end persistence.

One row owns one mutually exclusive ordinary group. Other actor effects are
not ledger entries. No EP offer, client effect, damage or countdown is made.
"""
from contextlib import closing
import json,sqlite3,struct,time
from els_server.domain.elixir_items import ITEMS,catalog
from els_server.protocol.world_buff_messages import request
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes

def _exists(db,table):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def _owner(db,owner,account_id):
    from els_server.storage.profession_state import require_owner
    from els_server.storage.character_lifecycle import states
    require_owner(db,owner,account_id)
    state=states(db,(owner,)).get(owner,{})
    if state.get('requested_at') or state.get('finalized_at'):raise ValueError('Unavailable elixir actor')

def _clock(now):
    now=int(time.time())if now is None else now
    if type(now)is not int or not 1<=now<2**31-7200:raise ValueError('Elixir epoch bounds')
    return now

def _ordinary_state(db,owner,now):
    if not _exists(db,'world_elixir_state'):return dict(owner=owner,revision=0,rows=[])
    r=db.execute('SELECT revision,template,source_uid,starts_at,ends_at,operation_id FROM world_elixir_state WHERE owner=?',(owner,)).fetchone()
    if r is None:return dict(owner=owner,revision=0,rows=[])
    revision,template,source,starts,ends,operation=r
    if type(revision)is not int or not 1<=revision<2**63:raise ValueError('Elixir revision')
    if template==0:
        if (source,starts,ends,operation)!=(0,0,0,''):raise ValueError('Elixir empty state')
        rows=[]
    else:
        rule=catalog().get(template)
        if not rule or any(type(v)is not int for v in(source,starts,ends))or not 0<source<2**63 or not 1<=starts<ends<2**31 or ends-starts!=rule['period_seconds']:raise ValueError('Unqualified elixir state')
        _source(db,operation,owner,source,template)
        rows=[dict(owner=owner,template=template,source_uid=source,start=starts,end=ends)]if now<ends else []
    return dict(owner=owner,revision=revision,rows=rows)

def _group(template):
    group=catalog()[template].get('supplemental_group',0)
    if group not in(0,310777,722990,190401,310775,310776)or(group and group!=template):raise ValueError('Elixir explicit native group')
    return group


def _battle_state(db,owner,now):
    ordinary=_ordinary_state(db,owner,now)
    if any(_group(r['template'])for r in ordinary['rows']):raise ValueError('Supplement in ordinary elixir state')
    rows=list(ordinary['rows']);revision=ordinary['revision']
    if _exists(db,'world_elixir_supplements'):
        saved=db.execute('SELECT group_id,revision,template,source_uid,starts_at,ends_at,operation_id FROM world_elixir_supplements WHERE owner=? ORDER BY group_id',(owner,)).fetchall()
        if len(saved)>2:raise ValueError('Elixir finite additional rows')
        for group,rev,template,source,start,end,operation in saved:
            if group not in(310777,722990)or type(rev)is not int or not 1<=rev<2**63:raise ValueError('Elixir additional group/revision')
            revision+=rev
            if template==0:
                if(source,start,end,operation)!=(0,0,0,''):raise ValueError('Elixir inactive additional state')
                continue
            if template!=group or _group(template)!=group or any(type(v)is not int for v in(source,start,end))or not 0<source<2**63 or not 1<=start<end<2**31 or end-start!=catalog()[template]['period_seconds']:raise ValueError('Elixir additional source/duration')
            _source(db,operation,owner,source,template)
            if now<end:rows.append(dict(owner=owner,template=template,source_uid=source,start=start,end=end))
    if not 0<=revision<2**63:raise ValueError('Elixir aggregate revision overflow')
    return dict(owner=owner,revision=revision,_moment=now,rows=sorted(rows,key=lambda r:(_group(r['template']),r['template'])))


def _battle_put(db,owner,template,source,start,end,operation):
    group=_group(template)
    if group:
        db.execute('CREATE TABLE IF NOT EXISTS world_elixir_supplements(owner INTEGER NOT NULL REFERENCES characters(uid),group_id INTEGER NOT NULL CHECK(group_id IN(310777,722990)),revision INTEGER NOT NULL CHECK(revision>0),template INTEGER NOT NULL,source_uid INTEGER NOT NULL,starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL,PRIMARY KEY(owner,group_id))')
        old=db.execute('SELECT revision FROM world_elixir_supplements WHERE owner=? AND group_id=?',(owner,group)).fetchone();revision=old[0]+1 if old else 1
        if not 1<=revision<2**63:raise ValueError('Additional elixir revision overflow')
        db.execute('INSERT INTO world_elixir_supplements VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(owner,group_id) DO UPDATE SET revision=excluded.revision,template=excluded.template,source_uid=excluded.source_uid,starts_at=excluded.starts_at,ends_at=excluded.ends_at,operation_id=excluded.operation_id',(owner,group,revision,template,source,start,end,operation))
    else:
        old=db.execute('SELECT revision FROM world_elixir_state WHERE owner=?',(owner,)).fetchone();revision=old[0]+1 if old else 1
        if not 1<=revision<2**63:raise ValueError('Ordinary elixir revision overflow')
        db.execute('INSERT INTO world_elixir_state VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET revision=excluded.revision,template=excluded.template,source_uid=excluded.source_uid,starts_at=excluded.starts_at,ends_at=excluded.ends_at,operation_id=excluded.operation_id',(owner,revision,template,source,start,end,operation))


ECONOMY_GROUPS=(190401,310775,310776)
ECONOMY_TABLE_SQL='CREATE TABLE world_elixir_economy_state(owner INTEGER NOT NULL REFERENCES characters(uid),group_id INTEGER NOT NULL CHECK(group_id IN(190401,310775,310776)),revision INTEGER NOT NULL CHECK(revision>0),template INTEGER NOT NULL,source_uid INTEGER NOT NULL,starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL,PRIMARY KEY(owner,group_id))'

def _state(db,owner,now):
    current=_battle_state(db,owner,now);rows=list(current['rows']);revision=current['revision']
    if _exists(db,'world_elixir_economy_state'):
        saved=db.execute('SELECT group_id,revision,template,source_uid,starts_at,ends_at,operation_id FROM world_elixir_economy_state WHERE owner=? ORDER BY group_id',(owner,)).fetchall()
        if len(saved)>3:raise ValueError('Elixir finite economic groups')
        for group,rev,template,source,start,end,operation in saved:
            if group not in ECONOMY_GROUPS or type(rev)is not int or not 1<=rev<2**63:raise ValueError('Elixir economic group/revision')
            revision+=rev
            if template==0:
                if(source,start,end,operation)!=(0,0,0,''):raise ValueError('Elixir empty economic group')
                continue
            if template!=group or _group(template)!=group or any(type(v)is not int for v in(source,start,end))or not 0<source<2**63 or not 1<=start<end<2**31 or end-start!=catalog()[template]['period_seconds']:raise ValueError('Elixir economic source/duration')
            _source(db,operation,owner,source,template)
            if now<end:rows.append(dict(owner=owner,template=template,source_uid=source,start=start,end=end))
    if not 0<=revision<2**63:raise ValueError('Elixir total revision overflow')
    # Closing new admissions for compatible code recovery suspends their wire
    # effects without erasing owned saved deadlines or inventory/award history.
    rows=[r for r in rows if catalog()[r['template']].get('admitted',True)]
    return dict(owner=owner,revision=revision,_moment=now,rows=sorted(rows,key=lambda r:(_group(r['template']),r['template'])))


def _put(db,owner,template,source,start,end,operation):
    group=_group(template)
    if group not in ECONOMY_GROUPS:return _battle_put(db,owner,template,source,start,end,operation)
    db.execute(ECONOMY_TABLE_SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
    old=db.execute('SELECT revision FROM world_elixir_economy_state WHERE owner=? AND group_id=?',(owner,group)).fetchone();revision=old[0]+1 if old else 1
    if not 1<=revision<2**63:raise ValueError('Elixir economic group revision overflow')
    db.execute('INSERT INTO world_elixir_economy_state VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(owner,group_id) DO UPDATE SET revision=excluded.revision,template=excluded.template,source_uid=excluded.source_uid,starts_at=excluded.starts_at,ends_at=excluded.ends_at,operation_id=excluded.operation_id',(owner,group,revision,template,source,start,end,operation))


def snapshot(path,owner,account_id,*,now=None):
    now=_clock(now)
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');_owner(db,owner,account_id);return _state(db,owner,now)

def _ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS world_elixir_state(owner INTEGER PRIMARY KEY REFERENCES characters(uid),revision INTEGER NOT NULL CHECK(revision>0),template INTEGER NOT NULL,source_uid INTEGER NOT NULL,starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL)')

def _source(db,operation,owner,source,template):
    if not isinstance(operation,str)or not 1<=len(operation)<=160 or not _exists(db,'inventory_action_receipts'):raise ValueError('Elixir source receipt missing')
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,0x219):raise ValueError('Elixir source receipt missing')
    try:
        before,after=(json.loads(v)for v in row[2:])
        if not isinstance(before,list)or len(before)!=1 or not isinstance(before[0],dict):raise ValueError('Elixir source receipt missing')
        item=before[0]
        if (item['uid'],item['template'],item['group'],item['metadata'])!=(source,template,4,catalog()[template]['metadata'])or type(item['count'])is not int or item['count']<1:raise ValueError('Elixir source receipt missing')
        expected=[dict(item,count=item['count']-1)]if item['count']>1 else []
        if after!=expected:raise ValueError('Elixir source receipt missing')
    except(KeyError,TypeError,json.JSONDecodeError)as exc:raise ValueError('Elixir source receipt missing')from exc

def candidate(path,owner,payload,operation):
    # Read-only finite interception. No generic 219 interpretation or mutation.
    if not isinstance(payload,bytes)or len(payload)<8:return False
    uid=struct.unpack_from('>Q',payload)[0]
    with closing(sqlite3.connect(path,timeout=10))as db:
        item=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if item and item[0]in ITEMS:return True
        return bool(_exists(db,'inventory_action_receipts')and db.execute('SELECT 1 FROM inventory_action_receipts WHERE owner=? AND kind=? AND operation_id=?',(owner,0x219,operation)).fetchone())

def use(path,owner,account_id,payload,operation,prepare,*,now=None):
    item_uid,additional=request(payload)
    owner,digest=_identity(owner,0x219,payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=_clock(now);_owner(db,owner,account_id)
        old=_previous(db,operation,digest)
        from els_server.storage.inventory_state import load_items
        from els_server.storage.npc_trade import balances
        items=load_items(db,owner);ed=balances(db,owner)['ed'];state=_state(db,owner,now)
        if old is not None:
            receipt=db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
            try:template=json.loads(receipt[0])[0]['template']
            except(TypeError,IndexError,KeyError,json.JSONDecodeError)as exc:raise ValueError('Elixir source receipt missing')from exc
            if template not in ITEMS:raise ValueError('Elixir source receipt missing')
            _source(db,operation,owner,item_uid,template)
            events=[use_ack(current_changes(db,operation,owner,0x219,old,items),ed=ed)]+prepare(db,state,items)
            for event in events:encode_event(event)
            return dict(events=events,state=state,replayed=True,result=0)
        item=next((i for i in items if i['uid']==item_uid),None)
        if item is None or item['template']not in ITEMS or(item['group'],item['metadata'])!=(4,catalog()[item['template']]['metadata'])or item.get('sealed',False):raise ValueError('Owned elixir required')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=now);require_unlocked(item,now=now)
        level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
        if level<catalog()[item['template']].get('minimum_level',0):raise ValueError('Elixir level requirement')
        if additional==1 and any(_group(r['template'])==_group(item['template'])for r in state['rows']):
            # No DDL/receipt/expiry cleanup: the original confirmation is 0-write.
            return dict(events=[use_ack(result=403)],state=state,replayed=False,result=403)
        if state['revision']>=2**63-1:raise ValueError('Elixir revision overflow')
        after=dict(item,count=item['count']-1)if item['count']>1 else None
        row=dict(owner=owner,template=item['template'],source_uid=item_uid,start=now,end=now+catalog()[item['template']]['period_seconds'])
        new=dict(owner=owner,revision=state['revision']+1,_moment=now,rows=sorted([r for r in state['rows']if _group(r['template'])!=_group(item['template'])]+[row],key=lambda r:(_group(r['template']),r['template'])))
        remaining=[after if i['uid']==item_uid else i for i in items if i['uid']!=item_uid or after]
        # Preflight the exact ACK and canonical full-set notification inside
        # this transaction. Encoder/profile failure cannot consume a stack.
        events=[use_ack([((item['group'],item['slot']),after)],item['template'],ed)]+prepare(db,new,remaining)
        for event in events:encode_event(event)
        _ensure(db)
        if after:
            if db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',(item_uid,owner,item['count'])).rowcount!=1:raise ValueError('Elixir stack changed')
        else:
            from els_server.storage.item_instances import remove
            remove(db,owner,item)
        _put(db,owner,item['template'],item_uid,now,row['end'],operation)
        _commit(db,operation,digest,owner,0x219,[(item['group'],item['slot'])],[item],[after]if after else [])
        return dict(events=events,state=new,replayed=False,result=0)

def expire(path,owner,account_id,prepare,*,now=None):
    now=_clock(now)
    def due(db):
        ordinary=bool(_exists(db,'world_elixir_state')and db.execute('SELECT 1 FROM world_elixir_state WHERE owner=? AND template!=0 AND ends_at<=?',(owner,now)).fetchone())
        supplements=bool(_exists(db,'world_elixir_supplements')and db.execute('SELECT 1 FROM world_elixir_supplements WHERE owner=? AND template!=0 AND ends_at<=?',(owner,now)).fetchone())
        economy=bool(_exists(db,'world_elixir_economy_state')and db.execute('SELECT 1 FROM world_elixir_economy_state WHERE owner=? AND template!=0 AND ends_at<=?',(owner,now)).fetchone())
        return ordinary or supplements or economy
    with closing(sqlite3.connect(path,timeout=10))as probe:
        probe.execute('BEGIN');_owner(probe,owner,account_id)
        if not due(probe):return None
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');_owner(db,owner,account_id)
        if not due(db):return None
        _state(db,owner,now)  # Validate every original receipt before cleanup.
        if _exists(db,'world_elixir_state'):
            db.execute("UPDATE world_elixir_state SET revision=revision+1,template=0,source_uid=0,starts_at=0,ends_at=0,operation_id='' WHERE owner=? AND template!=0 AND ends_at<=?",(owner,now))
        if _exists(db,'world_elixir_supplements'):
            db.execute("UPDATE world_elixir_supplements SET revision=revision+1,template=0,source_uid=0,starts_at=0,ends_at=0,operation_id='' WHERE owner=? AND template!=0 AND ends_at<=?",(owner,now))
        if _exists(db,'world_elixir_economy_state'):
            db.execute("UPDATE world_elixir_economy_state SET revision=revision+1,template=0,source_uid=0,starts_at=0,ends_at=0,operation_id='' WHERE owner=? AND template!=0 AND ends_at<=?",(owner,now))
        state=_state(db,owner,now);events=prepare(db,state,None)
        for event in events:encode_event(event)
        return dict(events=events,state=state)


def notice(path,owner,account_id,prepare,*,now=None):
    now=_clock(now)
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');_owner(db,owner,account_id);state=_state(db,owner,now)
        return dict(state=state,events=prepare(db,state,None)if state['revision']else [])
