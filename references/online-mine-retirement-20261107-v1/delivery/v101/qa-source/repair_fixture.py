"""Seed exactly one owned role's existing admission prerequisites."""
from contextlib import closing
import hashlib,sqlite3

def seed(path,values):
 from els_server.storage.local_state import LocalState
 from els_server.storage.seal_quests import QuestState
 from els_server.game_data import client_data
 for v in values:
  uid=v['uid'];LocalState(path,uid).save(20000,0,0,(1.,2.,3.))
  QuestState(path,uid,account_id=v['account_id']).snapshot()
  with closing(sqlite3.connect(path))as db,db:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
   assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(v['account_id'],)
   db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
   db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
   db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26650,1,'{}'))

def snapshot(path,values):
 with closing(sqlite3.connect(path))as db:
  db.execute('BEGIN');out=[]
  for v in values:
   uid=v['uid'];assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(v['account_id'],)
   balances=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone()
   items=db.execute('SELECT *FROM inventory_items WHERE owner=?ORDER BY uid',(uid,)).fetchall()
   out.append(dict(balances=balances,items_sha256=hashlib.sha256(repr(items).encode()).hexdigest()))
  return out
