"""Owned retained equipment; original wear writer, no new acquisition source."""
from contextlib import closing
import sqlite3,time,uuid,struct
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.wear_moves import move
from els_server.storage import achievements as state
from els_server.storage.achievement_history import record_play_day,counts as history_counts
from els_server.storage.achievement_collections import counts
from els_server.domain.equipment_requirements import inspect_requirements
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data

def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    a=values[0];a['alt_name']=a['character_name']+'Alt';a['alt_uid']=Characters(path,a['account_id']).create(a['alt_name'],1,'owned-equipment-alt:'+str(a['uid']))['uid']
    for v in[*values,dict(uid=a['alt_uid'])]:
        LocalState(path,v['uid']).save(20001,0,0,catalog()['towns']['20001']['xyz']);v['town']=20001
    owners=[a['uid'],a['alt_uid'],values[1]['uid']]
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for uid in[v['uid']for v in values]+[a['alt_uid']]:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET ed=6000000,experience=? WHERE uid=?',(client_data().thresholds[98],uid))
        for uid in owners:grant_items(db,[dict(template=t,metadata=1,group=1,quantity=1)for t in range(118153,118157)],uid)
        grant_items(db,[dict(template=t,metadata=0,group=2,quantity=1)for t in range(189020,189026)]+[dict(template=110845,metadata=0,group=4,quantity=1)],a['uid'])
        today=(int(time.time())+28800)//86400
        for days_ago in range(1,100):record_play_day(db,a['account_id'],a['uid'],(today-days_ago)*86400-28800+3600)
    for uid,number in zip(owners,(3,2,4)):
        with closing(sqlite3.connect(path))as db:items=load_items(db,uid)
        for seq,item in enumerate((i for i in items if i['template']in range(118153,118153+number)),1):
            slot=inspect_requirements(item['template'],1)['equipment_slot'];account=a['account_id']if uid in owners[:2]else values[1]['account_id']
            move(path,struct.pack('>BiBiB',item['group'],item['slot'],9,slot,0),uid,account_id=account,session_id=str(uuid.uuid4()),sequence=seq)

def snapshot(path,values):
    result=[]
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for v in values:
            uid,account=v['uid'],v['account_id'];source=counts(db,account,uid,int(time.time()),{50});items=load_items(db,uid)
            row=dict(achievement=state.snapshot(db,account,uid),play_days=history_counts(db,account,{10}).get((10,0),0),equipped={str(key[1]):value for key,value in source.items()},items=[dict(uid=i['uid'],template=i['template'],group=i['group'],slot=i['slot'])for i in items if i['template']in range(118153,118157)or i['template']in range(189020,189026)or i['template']==110845])
            guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid,)).fetchone()if 'native_guild_members'in tables else None;row['guild']=guild[0]if guild else None
            if 'alt_uid'in v:row['alt_achievement']=state.snapshot(db,account,v['alt_uid'])
            result.append(row)
    return result
