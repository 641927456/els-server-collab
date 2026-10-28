"""Durable native bank history from actual owned coin donations only."""
from contextlib import closing
import json,sqlite3
from els_server.protocol import guild_bank_history_messages as wire
from els_server.protocol.protocol_codec import encode_event
def _exists(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(name,)).fetchone()is not None
def record_donation(db,saved,owner,account,quantity,operation,stamp):
 if not db.in_transaction:raise ValueError('Guild coin history caller writer')
 from els_server.storage.seal_quests import load_character
 from els_server.domain.character_rules import transcendental_stage
 c=load_character(db,owner,account)
 row=dict(owner=owner,unit_class=c['unit_class'],level=c['level'],direction=0,grade=saved['grade'],name=c['name'],template=400152,quantity=quantity,enhancement=0,created_at=stamp,stage=transcendental_stage(c))
 wire.record(row)
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_bank_history_v1(operation TEXT PRIMARY KEY,guild_id INTEGER NOT NULL REFERENCES native_guilds(id),owner INTEGER NOT NULL,record_json TEXT NOT NULL,created_at INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1))''')
 db.execute('CREATE INDEX IF NOT EXISTS native_guild_bank_history_order_v1 ON native_guild_bank_history_v1(guild_id,created_at,operation)')
 value=(operation,saved['id'],owner,json.dumps(row,sort_keys=True,separators=(',',':')),stamp,1)
 old=db.execute('SELECT operation,guild_id,owner,record_json,created_at,version FROM native_guild_bank_history_v1 WHERE operation=?',(operation,)).fetchone()
 if old is None:db.execute('INSERT INTO native_guild_bank_history_v1 VALUES(?,?,?,?,?,?)',value)
 elif old!=value:raise ValueError('Guild coin history producer changed')
def record_transfer(db,saved,owner,account,template,quantity,direction,operation,stamp):
 if not db.in_transaction:raise ValueError('Guild transfer history writer required')
 from els_server.storage.seal_quests import load_character
 from els_server.domain.character_rules import transcendental_stage
 c=load_character(db,owner,account)
 row=dict(owner=owner,unit_class=c['unit_class'],level=c['level'],direction=direction,grade=saved['grade'],name=c['name'],template=template,quantity=quantity,enhancement=0,created_at=stamp,stage=transcendental_stage(c));wire.record(row)
 db.execute("CREATE TABLE IF NOT EXISTS native_guild_bank_history_v1(operation TEXT PRIMARY KEY,guild_id INTEGER NOT NULL REFERENCES native_guilds(id),owner INTEGER NOT NULL,record_json TEXT NOT NULL,created_at INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1))")
 db.execute('CREATE INDEX IF NOT EXISTS native_guild_bank_history_order_v1 ON native_guild_bank_history_v1(guild_id,created_at,operation)')
 db.execute('INSERT INTO native_guild_bank_history_v1 VALUES(?,?,?,?,?,1)',(operation,saved['id'],owner,json.dumps(row,sort_keys=True,separators=(',',':')),stamp))

def snapshot(db,guild_id):
 source={}
 if _exists(db,'native_guild_coin_donations_v1'):
  for op,owner,quantity,stamp in db.execute('SELECT operation,owner,quantity,created_at FROM native_guild_coin_donations_v1 WHERE guild_id=?',(guild_id,)):source[op]=(owner,400152,quantity,stamp,0)
 if _exists(db,'native_guild_bank_transfers_v1'):
  for op,owner,template,quantity,stamp,kind,version,digest in db.execute('SELECT operation,owner,template,quantity,created_at,kind,version,request_hash FROM native_guild_bank_transfers_v1 WHERE guild_id=?',(guild_id,)):
   receipt=db.execute('SELECT request_hash,owner,kind FROM inventory_action_receipts WHERE operation_id=?',(op,)).fetchone()
   if op in source or kind not in(0x50a,0x50c)or version!=1 or receipt!=(digest,owner,kind):raise ValueError('Guild transfer history producer changed')
   source[op]=(owner,template,quantity,stamp,0 if kind==0x50a else 1)
 if not _exists(db,'native_guild_bank_history_v1'):
  if source:raise ValueError('Guild actual producer lacks history')
  return[]
 rows=[]
 for operation,owner,raw,stamp,version in db.execute('SELECT operation,owner,record_json,created_at,version FROM native_guild_bank_history_v1 WHERE guild_id=? ORDER BY created_at DESC,operation DESC',(guild_id,)):
  row=json.loads(raw)
  if version!=1 or type(row)is not dict or row.get('owner')!=owner or row.get('created_at')!=stamp or source.pop(operation,None)!=(owner,row.get('template'),row.get('quantity'),stamp,row.get('direction')):raise ValueError('Guild bank history source changed')
  wire.record(row);rows.append(row)
 if source:raise ValueError('Guild bank producer missing history')
 return rows

def read(path,owner,account,payload,guard):
 page,tab=wire.request(payload)
 from els_server.storage.guild_coin_state import authority,snapshot as coin_balance
 with closing(sqlite3.connect(path,timeout=10))as db:
  db.execute('BEGIN');saved=authority(db,owner,account,guard);coin_balance(db,saved['id']);rows=snapshot(db,saved['id'])
  # Native constructor22FF15B initializes current filter2; record in/out0/1.
  rows=[r for r in rows if tab==2 or r['direction']==tab];pages=max(1,(len(rows)+9)//10)
  if page>pages:raise ValueError('Guild bank history page exceeds saved records')
  answer=wire.reply(page,pages,tab,rows[(page-1)*10:page*10]);encode_event(answer)
  if authority(db,owner,account,guard)!=saved:raise ValueError('Guild history late membership changed')
  return[answer]
