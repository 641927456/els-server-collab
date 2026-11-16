"""Three owned identities and a sibling; actual Noah class and valid saved rooms."""
from contextlib import closing
import sqlite3
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import InventoryState,grant_items,load_items
from els_server.storage import achievements as state
from els_server.storage.achievement_history import counts
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data

def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    a=values[0];a['alt_name']=a['character_name']+'Alt';a['alt_uid']=Characters(path,a['account_id']).create(a['alt_name'],14,'owned-notebook-alt:'+str(a['uid']))['uid']
    c=values[2];c['alt_name']=c['character_name']+'Alt';c['alt_uid']=Characters(path,c['account_id']).create(c['alt_name'],1,'owned-spa-alt:'+str(c['uid']))['uid']
    for v,town in zip(values,(20012,20012,1500)):
        v['town']=town;LocalState(path,v['uid']).save(town,0,0,(0.,0.,0.)if town==1500 else catalog()['towns'][str(town)]['xyz'])
    LocalState(path,a['alt_uid']).save(20012,0,0,catalog()['towns']['20012']['xyz'])
    LocalState(path,c['alt_uid']).save(20000,0,0,catalog()['towns']['20000']['xyz'])
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for v,unit in zip(values,(14,14,1)):
            assert db.execute('SELECT unit_type FROM characters WHERE uid=?',(v['uid'],)).fetchone()==(unit,)
        for uid in[v['uid']for v in values]+[a['alt_uid'],c['alt_uid']]:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET ed=25000000,experience=? WHERE uid=?',(client_data().thresholds[98],uid))
        grant_items(db,[dict(template=710012,metadata=2,group=6,quantity=1)],c['alt_uid'])

def snapshot(path,values):
    result=[]
    for v in values:
        with closing(sqlite3.connect(path))as db:
            db.execute('BEGIN');history=counts(db,v['account_id'],{10,34,66});row=dict(achievement=state.snapshot(db,v['account_id'],v['uid']),notes={str(n):history.get((66,n),0)for n in range(10372,10376)},days=history.get((10,0),0),bought=history.get((34,710012),0))
            if 'alt_uid'in v:
                row['alt_achievement']=state.snapshot(db,v['account_id'],v['alt_uid'])
                row['alt_items']=load_items(db,v['alt_uid'])
        row['wallet']=InventoryState(path,v['uid']).snapshot();result.append(row)
    return result
