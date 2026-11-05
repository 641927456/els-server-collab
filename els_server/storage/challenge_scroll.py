"""Reset committed current-week challenge clear information; never award loot.

The original reward receipts retain owner, dungeon, attempt and clear time.
Resetting advances a receipt boundary, retaining all historical clear evidence.
Both categories remain open under the human-confirmed 2026-11-01 server rule.
"""
from contextlib import closing
import json,sqlite3,struct,time
from els_server.domain.owned_scroll_families import catalog
from els_server.domain.dungeon_routes import route_catalog
from els_server.storage.raid_economy_state import week_at,exists
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character
from els_server.storage.npc_trade import balances,charge
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import Event,encode_event

def recognizes(path,owner,payload,operation):
    if type(payload)is not bytes or len(payload)<8:return False
    uid=int.from_bytes(payload[:8],'big')
    if not 0<uid<2**63:return False
    with closing(sqlite3.connect(path))as db:
        row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if row and row[0]in catalog()['challenge']:return True
        return bool(exists(db,'inventory_action_receipts')and db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=0x219',(operation,owner)).fetchone())

def snapshot(db,owner,category,now):
    if category not in(4,5):raise ValueError('Challenge category')
    week=week_at(now);used=boundary=0
    if exists(db,'challenge_scroll_resets'):
        used,boundary=db.execute('SELECT COUNT(*),COALESCE(MAX(receipt_boundary),0) FROM challenge_scroll_resets WHERE owner=? AND category=? AND week=?',(owner,category,week)).fetchone()
    phases=route_catalog()._data['challenges']
    nodes={n['dungeon']:n['count']for p in phases if p['challenge']==category for n in p['nodes']}
    encounters={};cleared=set();latest=boundary
    if exists(db,'reward_receipts'):
        # A split encounter's ordinal belongs to its original attempt. Include
        # the possible pre-reset-day part of an attempt before selecting this
        # week's claims, so repeated first halves never become second halves.
        start=week-max(p['seconds']for p in phases)
        for rowid,raw in db.execute("SELECT rowid,grant_json FROM reward_receipts WHERE json_extract(grant_json,'$.challenge_clear.now')>=? AND json_extract(grant_json,'$.challenge_clear.now')<=? AND COALESCE(json_extract(grant_json,'$.owner'),1001)=? ORDER BY rowid",(start,now,owner)):
            grant=json.loads(raw);effect=grant['challenge_clear'];dungeon=effect['dungeon']
            if dungeon in nodes:
                key=(effect['attempt'],dungeon);ordinal=encounters.get(key,0);encounters[key]=ordinal+1
                if ordinal>=nodes[dungeon]:raise ValueError('Committed challenge encounter exceeds its native count')
                if rowid>boundary and effect['now']>=week:
                    cleared.add((dungeon,ordinal));latest=max(latest,rowid)
    return dict(category=category,used=used,clears=len(cleared),boundary=latest,week=week)

def notice(value):
    # BD9830's existing 69-byte7C1 value. Challenge uses the normal reset
    # clear count at+8;1021340 divides by native reward count. Opaque
    # display scalars stay zero; weekly use limits stay server-owned.
    event=Event(0x201,kind=0x7c1,payload=struct.pack('>7iI9i?',value['category'],0,0,value['clears'],0,0,0,9,*([0]*9),False))
    encode_event(event);return event

def perform(path,owner,account,payload,operation,*,prepare,now=None):
    if type(payload)is not bytes or len(payload)!=29:raise ValueError('Challenge scroll request size')
    uid,count,a,b,n,flag=struct.unpack('>QQiiIB',payload)
    if not 0<uid<2**63 or count not in(0,1)or a or b or n or flag not in(0,1):raise ValueError('Challenge scroll single-use fields')
    owner,digest=_identity(owner,0x219,payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_owner(db,owner,account);require_active_character(db,owner);prepare(db)
        # Sample after the lock and the identity recheck: a scroll that expires
        # while queued must not open a challenge, and the new deadline has to
        # start from the moment this request actually owns the write lock.
        now=int(time.time())if now is None else now
        old=_previous(db,operation,digest);before=load_items(db,owner)
        if old is not None:
            saved=db.execute('SELECT category FROM challenge_scroll_resets WHERE operation=? AND owner=?',(operation,owner)).fetchone()
            if saved is None:raise ValueError('Challenge reset receipt missing')
            result=[use_ack(current_changes(db,operation,owner,0x219,old,before),ed=balances(db,owner)['ed']),notice(snapshot(db,owner,saved[0],now))]
            for event in result:encode_event(event)
            prepare(db);return result
        item=next((i for i in before if i['uid']==uid),None)
        if item is None or item['template']not in catalog()['challenge']or item['group']!=4 or item.get('sealed'):raise ValueError('Owned challenge scroll required')
        require_current(item,now=now);require_unlocked(item,now=now)
        if exists(db,'challenge_attempts')and db.execute('SELECT 1 FROM challenge_attempts WHERE uid=? AND complete=0 AND deadline>?',(owner,now)).fetchone():raise ValueError('Challenge is still active')
        value=snapshot(db,owner,catalog()['challenge'][item['template']]['category'],now)
        if value['used']>=2 or value['clears']==0:raise ValueError('Challenge reset requires progress and fewer than two weekly uses')
        db.execute('CREATE TABLE IF NOT EXISTS challenge_scroll_resets(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,category INTEGER NOT NULL CHECK(category IN(4,5)),week INTEGER NOT NULL,receipt_boundary INTEGER NOT NULL)')
        db.execute('INSERT INTO challenge_scroll_resets VALUES(?,?,?,?,?)',(operation,owner,value['category'],value['week'],value['boundary']))
        if item['count']==1:remove(db,owner,item);remaining=None
        else:
            db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,uid));remaining=dict(item,count=item['count']-1)
        charge(db,owner,balances(db,owner),0);position=(item['group'],item['slot'])
        result=[use_ack([(position,remaining)],item['template'],balances(db,owner)['ed']),notice(snapshot(db,owner,value['category'],now))]
        for event in result:encode_event(event)
        _commit(db,operation,digest,owner,0x219,[position],[item],[remaining]if remaining else[]);prepare(db);return result
