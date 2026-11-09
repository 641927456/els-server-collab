"""Original506/507 Rose weapon preference, bound to the actual GuildAgit actor."""
from contextlib import closing
import sqlite3,hashlib,struct

def preference(path,uid):
 with closing(sqlite3.connect(path))as db:
  exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='native_guild_rose_weapons_v2'").fetchone()
  row=db.execute('SELECT weapon FROM native_guild_rose_weapons_v2 WHERE owner=?',(uid,)).fetchone()if exists else None
 if row is None:return 0
 if row[0]not in range(4):raise ValueError('GuildAgit saved Rose weapon')
 return row[0]

def notification(uid,value):
 from els_server.protocol.protocol_codec import Event
 if type(value)is not int or value not in range(4):raise ValueError('Original Rose weapon enum')
 return Event(0x201,kind=0x507,payload=struct.pack('>QB',uid,value))

def handle(s,event,sequence):
 from els_server.domain.luciel_state import style_context,validate_style_context,prepare_style,_guild_guard
 from els_server.game_data import client_data
 if(s.phase!='guild_agit_ready'or event.kind!=0x506 or len(event.payload)!=1 or event.payload[0]not in range(4)
  or type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))
  or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('GuildAgit Rose original request')
 c=s.account.character();owner=s.account.uid
 if c['uid']!=owner or c['unit_type']!=11 or client_data().unit(c['unit_class'])['unitType']!=11:raise ValueError('Actual owned Rose character')
 captured=style_context(s);value=event.payload[0]
 operation=s.shop_session_id+':guild-rose:'+str(owner)+':'+str(sequence)
 digest=hashlib.sha256(event.payload).hexdigest()
 with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
  try:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');_guild_guard(db,s,captured['targets'])
   db.execute('CREATE TABLE IF NOT EXISTS native_guild_rose_weapons_v2(owner INTEGER PRIMARY KEY REFERENCES characters(uid),weapon INTEGER NOT NULL CHECK(weapon BETWEEN 0 AND 3))')
   db.execute('CREATE TABLE IF NOT EXISTS native_guild_rose_operations_v2(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,request_hash TEXT NOT NULL)')
   old=db.execute('SELECT owner,request_hash FROM native_guild_rose_operations_v2 WHERE operation=?',(operation,)).fetchone()
   if old is not None:
    if old!=(owner,digest):raise ValueError('Guild Rose conflicting retry')
    value=db.execute('SELECT weapon FROM native_guild_rose_weapons_v2 WHERE owner=?',(owner,)).fetchone()[0]
   answer=[notification(owner,value)]
   publication=prepare_style(s,captured,answer)
   if old is None:
    db.execute('INSERT INTO native_guild_rose_weapons_v2 VALUES(?,?)ON CONFLICT(owner)DO UPDATE SET weapon=excluded.weapon',(owner,value))
    db.execute('INSERT INTO native_guild_rose_operations_v2 VALUES(?,?,?)',(operation,owner,digest))
   validate_style_context(s,captured);_guild_guard(db,s,captured['targets']);db.commit()
  except BaseException:db.rollback();raise
 for peer,box in publication[3]:peer.mailbox=box
 return answer
