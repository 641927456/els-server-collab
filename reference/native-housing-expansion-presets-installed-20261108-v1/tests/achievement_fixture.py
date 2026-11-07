"""Only the owned actor's level/currency, first contract and grown pet are fixtures."""
from contextlib import closing
import sqlite3
from els_server.game_data import client_data
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.item_instances import next_uid
from els_server.storage import companion_state,pet_progression,housing_rooms,housing_layouts,housing_presets,housing_expansions,housing_pets,achievements

def seed(path,values):
 assert len(values)==1
 value=values[0];owner=value['uid'];value['town']=20000
 LocalState(path,owner).save(20000,0,0,(5454.82861328125,123.39099884033203,-488.52203369140625))
 with closing(sqlite3.connect(path))as db,db:
  db.execute('BEGIN IMMEDIATE')
  db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,))
  db.execute('UPDATE reward_balances SET ed=600000000,experience=? WHERE uid=?',(client_data().thresholds[98],owner))
  first=grant_items(db,[dict(template=713275,metadata=0,group=4,quantity=1)],owner)[0]
  value['first_contract_uid']=first['uid'];companion_state.ensure(db);pet_uid=next_uid(db)
  db.execute('INSERT INTO companions VALUES(?,?,?,?,?,?)',(pet_uid,owner,'pet',1,'OwnedHousePet',0))
  pet=companion_state.rows(db,owner,'pet')[0];pet.update(step=3,growth=0);pet_progression.save(db,owner,pet);value['pet_uid']=pet_uid

def snapshot(path,values):
 result=[]
 with closing(sqlite3.connect(path))as db:
  db.execute('BEGIN')
  for value in values:
   uid=value['uid'];aid=value['account_id']
   result.append(dict(uid=uid,items=load_items(db,uid),balance=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone(),
    room=housing_rooms.snapshot(db,uid,aid),layouts=housing_layouts.states(db,uid,aid),presets=housing_presets.snapshot(db,uid,aid),extra_presets=housing_expansions.preset_expansions(db,uid,aid),
    placed_pets=housing_pets.saved(db,uid),pets=companion_state.rows(db,uid,'pet'),achievement=achievements.snapshot(db,aid,uid)))
 return result
