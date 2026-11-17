"""Explicit owned guild license/level fixtures; CP comes from test requests."""
from contextlib import closing
import sqlite3
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import achievements as state
from els_server.storage.achievement_history import counts
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data

def seed(path,values):
    assert len(values)==2
    a=values[0];a['alt_name']=a['character_name']+'Alt'
    a['alt_uid']=Characters(path,a['account_id']).create(a['alt_name'],2,'owned-cp-guild-alt:'+str(a['uid']))['uid']
    owners=[v['uid']for v in values]+[a['alt_uid']]
    for owner in owners:LocalState(path,owner).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    with closing(sqlite3.connect(path))as db,db:
        for owner in owners:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,))
            db.execute('UPDATE reward_balances SET ed=6000000,experience=?WHERE uid=?',(client_data().thresholds[98],owner))
        grant_items(db,[dict(template=110845,metadata=0,group=4,quantity=1)],a['uid'])
        a['license_uid']=next(r['uid']for r in load_items(db,a['uid'])if r['template']==110845)
    for value in values:value['town']=20001

def snapshot(path,values):
    rows=[]
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN')
        has_guild=db.execute("SELECT 1 FROM sqlite_master WHERE name='native_guild_members'").fetchone()
        for value in values:
            owner=value['uid'];account=value['account_id']
            guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(owner,)).fetchone()if has_guild else None
            rows.append(dict(uid=owner,achievement=state.snapshot(db,account,owner),
                alt_achievement=state.snapshot(db,account,value['alt_uid'])if'alt_uid'in value else None,
                banner_count=counts(db,account,{59}).get((59,0),0),guild_id=guild[0]if guild else None,
                economy={str(uid):dict(balance=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone(),
                    items=load_items(db,uid))for uid in[owner]+([value['alt_uid']]if'alt_uid'in value else[])}))
    return rows
