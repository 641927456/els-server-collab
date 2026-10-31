"""Persisted original expedition lifecycle and explicitly approved region1 economy."""
from contextlib import closing
import hashlib
import json
import secrets
import sqlite3
import struct
import time

from els_server.protocol import pet_expedition_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.companion_state import rows
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.life_stamina import day, snapshot as life_snapshot


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS pet_expedition_runs(
        owner INTEGER PRIMARY KEY REFERENCES characters(uid),mission INTEGER NOT NULL CHECK(mission BETWEEN 1 AND 4),
        pets TEXT NOT NULL,started_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,
        refresh_day INTEGER NOT NULL,generation INTEGER NOT NULL,rate INTEGER NOT NULL CHECK(rate BETWEEN 0 AND 200))''')
    db.execute('''CREATE TABLE IF NOT EXISTS pet_expedition_receipts(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,account INTEGER NOT NULL,action TEXT NOT NULL,
        digest TEXT NOT NULL,result_json TEXT NOT NULL)''')


def authority(db, owner, account, guard):
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    if not db.in_transaction or not callable(guard):raise ValueError('Expedition actual actor writer required')
    guard(db);require_active_character(db,owner);require_owner(db,owner,account)
    if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()!=(99,):
        raise ValueError('Original expedition level99')


def _draw(randbelow, bound):
    value=randbelow(bound)
    if type(value) is not int or not 0<=value<bound:raise ValueError('Expedition random range')
    return value


def board(db, owner, now, randbelow):
    current=db.execute('SELECT mission,pets,started_at,ends_at,refresh_day,generation,rate FROM pet_expedition_runs WHERE owner=?',(owner,)).fetchone()
    if current is None:
        current=(_draw(randbelow,4)+1,'[]',0,0,day(now),1,0)
        db.execute('INSERT INTO pet_expedition_runs VALUES(?,?,?,?,?,?,?,?)',(owner,*current))
    elif not json.loads(current[1]) and current[4]<day(now):
        current=(_draw(randbelow,4)+1,'[]',0,0,day(now),current[5]+1,0)
        db.execute('UPDATE pet_expedition_runs SET mission=?,pets=?,started_at=?,ends_at=?,refresh_day=?,generation=?,rate=? WHERE owner=?',(*current,owner))
    return current


def projection(db, owner, current):
    selected=json.loads(current[1]);pets={p['uid']:p for p in rows(db,owner,'pet')} if selected else {}
    if len(set(selected))!=len(selected) or any(p not in pets for p in selected):
        raise ValueError('Expedition saved owned pets changed')
    return dict(mission=current[0],region=1,pets=[pets[p]for p in selected],started_at=current[2],ends_at=current[3])


def initialize(path, owner, account, guard, *, now=None, randbelow=secrets.randbelow):
    now=int(time.time()) if now is None else now
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        authority(db,owner,account,guard);ensure(db)
        event=wire.board_notice({1:projection(db,owner,board(db,owner,now,randbelow))})
        encode_event(event);authority(db,owner,account,guard)
        return [event]


def require_available(db, owner, pet):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pet_expedition_runs'").fetchone():return
    row=db.execute('SELECT pets FROM pet_expedition_runs WHERE owner=?',(owner,)).fetchone()
    if row and pet in json.loads(row[0]):raise ValueError('Pet is exploring; cancel or complete expedition first')


def _discount(base, rate):
    # Current22B1E61..22B1E93 and22B1EFD..22B1F29 round a binary32 rate
    # to per-thousand units, then use signed integer division by1000.
    def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
    units=int(f32(f32(f32(rate)*1000.0)+0.5))
    value=base*(1000-units)
    if value<0:raise ValueError('Original expedition discount exceeds cost')
    return value//1000


def perform(path,owner,account,kind,payload,operation,guard,*,now=None,randbelow=secrets.randbelow):
    now=int(time.time()) if now is None else now
    if type(now) is not int or now<=0 or not isinstance(operation,str) or not 1<=len(operation)<=200:
        raise ValueError('Expedition clock/operation')
    region,mission,selected=wire.request(kind,payload)
    if region!=1 or mission not in range(1,5):raise ValueError('Only approved original region1 missions are open')
    action={0x8c1:'start',0x8c3:'complete',0x8c5:'cancel'}[kind]
    digest=hashlib.sha256(struct.pack('>QI',owner,kind)+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        authority(db,owner,account,guard);ensure(db)
        old=db.execute('SELECT owner,account,action,digest,result_json FROM pet_expedition_receipts WHERE operation=?',(operation,)).fetchone()
        current=(db.execute('SELECT mission,pets,started_at,ends_at,refresh_day,generation,rate FROM pet_expedition_runs WHERE owner=?',(owner,)).fetchone() if old else board(db,owner,now,randbelow))
        if current is None:raise ValueError('Expedition receipt missing current saved board')
        rewards={};changes=[];quest_events=[]
        if old:
            if old[:4]!=(owner,account,action,digest):raise ValueError('Conflicting expedition replay')
            result=json.loads(old[4]);rewards={int(k):v for k,v in result['rewards'].items()}
            # Reproject original changed positions from current owned inventory.
            inventory={(i['group'],i['slot']):i for i in load_items(db,owner)}
            changes=[inventory[p]for p in map(tuple,result['positions'])if p in inventory]
        else:
            if current[0]!=mission:raise ValueError('Expedition mission was replaced')
            active=json.loads(current[1])
            if action=='start':
                if active:raise ValueError('One expedition per character')
                from els_server.domain.pet_expedition import source_terms
                saved={p['uid']:p for p in rows(db,owner,'pet')}
                if any(p not in saved for p in selected):raise ValueError('Owned expedition pets required')
                active_pet=(db.execute('SELECT pet FROM companion_active WHERE owner=?',(owner,)).fetchone()or(0,))[0]
                facts=source_terms(mission,[saved[p]for p in selected],active_pet=active_pet)
                ed=_discount(facts['original_ed'],facts['ed_reduce_rate'])
                minutes=_discount(facts['original_minutes'],facts['time_reduce_rate'])
                life=life_snapshot(db,owner,account)
                if life['current']<facts['original_life']:raise ValueError('Insufficient saved expedition life')
                if db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=? AND ed>=?',(ed,owner,ed)).rowcount!=1:
                    raise ValueError('Insufficient expedition ED')
                from els_server.storage.life_stamina import debit
                debit(db,owner,account,facts['original_life'],expedition=True)
                current=(mission,json.dumps(selected),now,now+minutes*60,current[4],current[5]+1,facts['native_display_percent'])
            else:
                if not active:raise ValueError('No expedition is running')
                if action=='complete':
                    if now<current[3]:raise ValueError('Expedition original deadline has not elapsed')
                    rate=current[6]
                    if rate>=100 or _draw(randbelow,100)<rate:rewards[135984]=1
                    if rate>100 and _draw(randbelow,100)<rate-100:rewards[135985]=1
                    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
                    changes=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)for t,n in rewards.items()],owner)
                    current=(_draw(randbelow,4)+1,'[]',0,0,day(now),current[5]+1,0)
                else:
                    current=(mission,'[]',0,0,current[4],current[5]+1,0)
            db.execute('UPDATE pet_expedition_runs SET mission=?,pets=?,started_at=?,ends_at=?,refresh_day=?,generation=?,rate=? WHERE owner=?',(*current,owner))
            result=dict(rewards=rewards,positions=[[i['group'],i['slot']]for i in changes])
            db.execute('INSERT INTO pet_expedition_receipts VALUES(?,?,?,?,?,?)',(operation,owner,account,action,digest,json.dumps(result,sort_keys=True)))
            if action=='complete':
                from els_server.storage.account_fishing_tasks_scope import record_expedition
                quest_events=record_expedition(db,owner,account,operation,guard)
        state=projection(db,owner,current)
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
        if action=='complete':
            events=[wire.completion_ack(result=0,state=state,rewards=rewards,changes=changes)]
        else:
            # Current24933B0/2493870 read but never use the auxiliaryi32.
            events=[wire.state_ack(0x8c2 if action=='start'else 0x8c6,result=0,native_auxiliary=0,ed=ed,state=state)]
        from els_server.protocol.fishing_messages import life_notice
        events += [life_notice(life_snapshot(db,owner,account)['current'],show_delta=False)] + quest_events
        for event in events:encode_event(event)
        authority(db,owner,account,guard)
        return events
