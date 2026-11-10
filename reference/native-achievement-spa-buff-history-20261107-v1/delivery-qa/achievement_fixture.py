"""Explicit retained99-spa-grant history for three owned QA accounts."""
from contextlib import closing
import sqlite3
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import environment_buffs as buffs,achievement_history as history,achievements as state
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data


def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    first=values[0];first['alt_name']=first['character_name']+'Alt'
    first['alt_uid']=Characters(path,first['account_id']).create(first['alt_name'],4,'owned-spa-alternative:'+str(first['uid']))['uid']
    actors=[*values,dict(uid=first['alt_uid'],town=1500)]
    for i,value in enumerate(values):value['town']=1500 if i<2 else 20001
    for value in actors:
        town=value['town'];xyz=(0.,0.,0.)if town==1500 else catalog()['towns'][str(town)]['xyz']
        LocalState(path,value['uid']).save(town,0,0,xyz)
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for value in actors:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(value['uid'],))
            db.execute('UPDATE reward_balances SET ed=6000000,experience=?WHERE uid=?',(client_data().thresholds[98],value['uid']))
        db.execute('UPDATE reward_balances SET ed=0 WHERE uid=?',(values[1]['uid'],))
        for n in range(99):buffs.put(db,first['uid'],'spa','owned-spa-retained:'+str(first['uid'])+':'+str(n),1700000000+n)


def snapshot(path,values):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');result=[]
        for value in values:
            row=dict(count=history.counts(db,value['account_id'],{7}).get((7,964),0),
                ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(value['uid'],)).fetchone()[0],
                achievement=state.snapshot(db,value['account_id'],value['uid']))
            if 'alt_uid'in value:row['alt_achievement']=state.snapshot(db,value['account_id'],value['alt_uid'])
            result.append(row)
        return result
