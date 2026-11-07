"""Reuse the frozen notebook/spa fixtures and add one owned clear actor."""
from pathlib import Path
from importlib.machinery import SourceFileLoader
from contextlib import closing
import sqlite3,time,uuid
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.reward_state import RewardState
from els_server.storage.seal_quests import ensure as ensure_quests
from els_server.storage import achievements as state
from els_server.storage.achievement_history import counts
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data

# This file is a retained fixture implementation, not a runtime dependency.
prior=SourceFileLoader('owned_notebook_spa_fixture',str(Path(__file__).with_name('achievement_fixture.py.parent'))).load_module()

def seed(path,values):
    prior.seed(path,values)
    c=values[2];c['clear_name']=c['character_name']+'Clr'
    uid=c['clear_uid']=Characters(path,c['account_id']).create(c['clear_name'],1,'owned-clear-role:'+str(c['uid']))['uid']
    LocalState(path,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    with closing(sqlite3.connect(path))as db,db:
        db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
        db.execute('UPDATE reward_balances SET ed=25000000,experience=? WHERE uid=?',(client_data().thresholds[98],uid))
        ensure_quests(db);db.execute('INSERT INTO completed_quests VALUES (?,?,?,?)',(uid,26650,int(time.time()),'[]'))
    store=RewardState(path,uid,account_id=c['account_id'])
    for n in range(99):
        result=store.grant(str(uuid.uuid4()),('owned-34350-history:'+str(n)).encode(),0,0,
            lambda balances,best:b'owned-clear-history',dungeon_clear=(34350,1))
        assert not result['replayed']

def snapshot(path,values):
    rows=prior.snapshot(path,values)
    for row,value in zip(rows,values):
        with closing(sqlite3.connect(path))as db:
            row['clear_count']=counts(db,value['account_id'],{49}).get((49,34350),0)
            if 'clear_uid'in value:row['clear_achievement']=state.snapshot(db,value['account_id'],value['clear_uid'])
    return rows
