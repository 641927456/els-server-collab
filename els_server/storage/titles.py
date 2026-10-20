"""Atomic title item consumption, account sharing and character equipment."""
from contextlib import closing
import hashlib,sqlite3,time
from els_server.storage.character_schema import character_uid
from els_server.domain.titles import catalog,definition,eligible,scope
from els_server.protocol import title_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.domain.boosting_2026_title_rewards import is_coupon

def character(db,uid):
    row=db.execute('SELECT c.uid,c.name,c.unit_type,c.unit_class,c.level,o.account_id FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(character_uid(uid),)).fetchone()
    if row is None:raise ValueError('Unknown title owner')
    result=dict(zip(('uid','name','unit_type','unit_class','level','account_id'),row))
    result['title_completed_quests']=completed_for_equipment(db,result['uid'])
    return result

def exists(db,table):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS title_ownership (scope TEXT NOT NULL CHECK(scope IN ('account','character')), subject INTEGER NOT NULL, title INTEGER NOT NULL, acquired_by TEXT NOT NULL, acquired_at INTEGER NOT NULL, expires_at INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(scope,subject,title))")
    db.execute('CREATE TABLE IF NOT EXISTS title_equipment (owner INTEGER PRIMARY KEY REFERENCES characters(uid), title INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS title_item_receipts (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, owner INTEGER NOT NULL, bag_group INTEGER NOT NULL, slot INTEGER NOT NULL, title INTEGER NOT NULL)')

def completed_for_equipment(db,uid):
    # Read the existing committed per-character quest rows in this transaction.
    # Active tasks and another character/account's completion do not qualify.
    if not exists(db,'completed_quests'):return ()
    return tuple(r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=? ORDER BY quest',(character_uid(uid),)))


def owned(db,c,now):
    if not exists(db,'title_ownership'):return []
    rows=db.execute("SELECT title,acquired_by,expires_at,scope,subject FROM title_ownership WHERE (scope='character' AND subject=?) OR (scope='account' AND subject=?) ORDER BY title",(c['uid'],c['account_id'])).fetchall()
    result=[]
    for title,name,end,kind,subject in rows:
        if (not end or now<end) and (kind,subject)==scope(c,title):result.append(dict(title=title,name=name,expires_at=end))
    return result

def snapshot(db,uid,now=None):
    now=int(time.time()) if now is None else now;c=character(db,uid);rows=owned(db,c,now)
    selected=db.execute('SELECT title FROM title_equipment WHERE owner=?',(uid,)).fetchone() if exists(db,'title_equipment') else None
    active=selected[0] if selected and any(r['title']==selected[0] for r in rows) and eligible(c,selected[0]) else 0
    # The original client already owns all 932 static definitions. C23 rebuilds
    # its list, overlays acquired rows and restores open mission state.
    from els_server.storage.title_clears import opened
    return dict(owned=rows,missions=opened(db,c,rows),title=active)

def state(path,uid):
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        value=snapshot(db,uid)
        if not value['title'] and exists(db,'title_equipment'):db.execute('UPDATE title_equipment SET title=0 WHERE owner=? AND title<>0',(uid,))
        return value

def equip(path,uid,title):
    if type(title) is not int or title<0:raise ValueError('Title identity')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');current=snapshot(db,uid);c=character(db,uid)
        if title and (not any(r['title']==title for r in current['owned']) or not eligible(c,title)):raise ValueError('Title is not owned or eligible')
        answer=wire.equipment(title);schema(db)
        db.execute('INSERT INTO title_equipment VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET title=excluded.title',(uid,title))
        return answer

def use_item(path,uid,payload,operation_id,now=None):
    from els_server.protocol.career_messages import use_request,use_ack
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_expiration import require_current
    item_uid=use_request(payload);uid=character_uid(uid)
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Title operation identity')
    now=int(time.time()) if now is None else now
    if type(now) is not int or not 0<=now<2**40:raise ValueError('Title clock')
    digest=hashlib.sha256(str(uid).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');c=character(db,uid)
        if exists(db,'title_item_receipts'):
            old=db.execute('SELECT request_hash,owner,bag_group,slot,title FROM title_item_receipts WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old[:2]!=(digest,uid):raise ValueError('Conflicting title item retry')
                ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                items=load_items(db,uid);current={(i['group'],i['slot']):i for i in items}
                positions=[old[2:4]]
                # The request digest above binds this exact original source UID.
                # Preserve the historical slot's current occupant, then refresh
                # the surviving source at its current position/current count.
                # Never find a replacement source by template or restore a UID.
                for item in items:
                    pos=item['group'],item['slot']
                    if item['uid']==item_uid and pos not in positions:positions.append(pos)
                changes=[(pos,current.get(pos)) for pos in positions]
                return dict(replayed=True,ack=use_ack(changes,ed=ed),state=snapshot(db,uid,now))
        item=next((i for i in load_items(db,uid) if i['uid']==item_uid),None)
        rule=catalog()['items'].get(str(item['template'])) if item else None
        if rule is None:return None
        if item['group']!=4:raise ValueError('Title item outside owned consumables bag')
        require_current(item,now=now)
        from els_server.domain.item_locks import require_unlocked
        require_unlocked(item,now=now)
        title=rule['title']
        from els_server.game_data import client_data
        raw=client_data().item(item['template'])['record']
        if (c['level']<raw[209] or raw[210] not in (0,c['unit_type']) or raw[211] not in (0,c['unit_class'])):raise ValueError('Title item native character restrictions')
        if c['level']<rule['level'] or not eligible(c,title):raise ValueError('Title item requirements')
        if any(r['title']==title for r in owned(db,c,now)):raise ValueError('Title already owned')
        selected=is_coupon(item['template'])
        if selected and db.execute('SELECT revision FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]>=2**63-1:raise ValueError('Selected title revision overflow')
        remaining=dict(item,count=item['count']-1) if item['count']>1 else None
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
        ack=use_ack([((item['group'],item['slot']),remaining)],item['template'],ed)
        schema(db);kind,subject=scope(c,title);end=now+rule['period_days']*86400 if rule['period_days'] else 0
        # Re-acquiring an expired title does not reactivate an old selection.
        if kind=='account':db.execute('UPDATE title_equipment SET title=0 WHERE title=? AND owner IN (SELECT uid FROM character_owners WHERE account_id=?)',(title,subject))
        else:db.execute('UPDATE title_equipment SET title=0 WHERE title=? AND owner=?',(title,uid))
        db.execute('INSERT INTO title_ownership VALUES (?,?,?,?,?,?) ON CONFLICT(scope,subject,title) DO UPDATE SET acquired_by=excluded.acquired_by,acquired_at=excluded.acquired_at,expires_at=excluded.expires_at',(kind,subject,title,c['name'],now,end))
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,uid))
        else:
            from els_server.storage.item_expiration import forget
            forget(db,item_uid);db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,uid))
            from els_server.storage.item_locks import forget as forget_lock
            forget_lock(db,item_uid)
        db.execute('INSERT INTO title_item_receipts VALUES (?,?,?,?,?,?)',(operation_id,digest,uid,item['group'],item['slot'],title))
        result=snapshot(db,uid,now);initial=wire.initialization(result)
        if selected:
            encode_event(ack);encode_event(initial)
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(uid,))
        return dict(replayed=False,ack=ack,state=result)
