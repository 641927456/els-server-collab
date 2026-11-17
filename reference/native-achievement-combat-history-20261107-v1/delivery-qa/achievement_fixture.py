"""Owned retained official profiles; no fabricated timed-clear record."""
from contextlib import closing
import sqlite3
from achievement_pvp_fixture import balanced_profiles,register_fixture
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievements as state,achievement_history as history
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data


def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    first=values[0];first['alt_name']=first['character_name']+'Alt'
    first['alt_uid']=Characters(path,first['account_id']).create(first['alt_name'],4,'owned-combat-alternative')['uid']
    for value in [*values,dict(uid=first['alt_uid'])]:
        LocalState(path,value['uid']).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for index,value in enumerate(values):
            owner,account=value['uid'],value['account_id'];level=99 if index==2 else 75
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()==(account,)
            assert not history.counts(db,account,{2}).get((2,41400))
            db.execute('UPDATE characters SET level=?WHERE uid=?',(level,owner))
            db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[level-1],owner))
        db.execute('UPDATE characters SET level=75 WHERE uid=?',(first['alt_uid'],))
        db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[74],first['alt_uid']))
    for actor,profile in zip(values,balanced_profiles()):register_fixture(path,actor,profile)


def snapshot(path,values):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');result=[]
        for value in values:
            owner,account=value['uid'],value['account_id'];counts=history.counts(db,account,{2,4,5})
            row=dict(achievement=state.snapshot(db,account,owner),best=counts.get((2,41400)),
                wins=counts.get((4,12),0),losses=counts.get((5,12),0))
            if 'alt_uid'in value:row['alt_achievement']=state.snapshot(db,account,value['alt_uid'])
            result.append(row)
        return result
