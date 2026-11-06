"""Original296 preview/298 confirmation, consuming the actual owned name card."""
import struct,hashlib
KINDS=frozenset((0x296,0x298))
CARD=248400

def definitions():
 from els_server.game_data import client_data
 r=client_data().item(CARD)
 if hashlib.sha256(r['record']).hexdigest()!='f2ee26ab43d7c2aca2276ec27a15e5f3bbb735db58a2dfa65b3fb0de76f5ec39'or(r['metadata'],r['item_type'],r['flags8'])!=(0,7,56):raise ValueError('Guild name card source changed')
 return (dict(template=CARD,metadata=0,group=4,max_stack=1),)

def _schema(db):
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_name_requests_v2(
  owner INTEGER PRIMARY KEY REFERENCES characters(uid),guild_id INTEGER NOT NULL REFERENCES native_guilds(id),
  lease TEXT NOT NULL,old_name TEXT NOT NULL,new_name TEXT NOT NULL,operation TEXT NOT NULL)''')

def _card(item,now):
 if item is None or(item['template'],item['metadata'],item['group'],item['count'])!=(CARD,0,4,1):raise ValueError('Guild rename requires its actual owned singleton card')
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 require_current(item,now=now);require_unlocked(item,now=now)
 return item

def confirmed(db,saved,now,code=0):
 from els_server.storage import guild_membership_state as members
 from els_server.protocol.guild_system_messages import reply
 from els_server.protocol.guild_membership_profile import basic
 from els_server.domain.guild_initial_profile import profile
 account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(saved['owner'],)).fetchone()[0]
 current=members.snapshot(db,saved['owner'],account)
 return reply(0x299,struct.pack('>i',code)+basic(profile(current,db=db,now=now)['basic']))

def command(db,s,event,saved,operation,now):
 from els_server.storage import guild_membership_state as members
 from els_server.storage.inventory_state import load_items
 from els_server.protocol.social_messages import Reader
 from els_server.protocol.guild_system_messages import reply,text
 from els_server.protocol.guild_membership_profile import full_notification
 from els_server.domain.guild_initial_profile import profile
 if saved['grade']!=1:raise ValueError('Only current master can rename guild')
 owner=saved['owner'];before=load_items(db,owner);_schema(db)
 if event.kind==0x296:
  r=Reader(event.payload);name=r.text();r.end();key=members.name_key(name)
  if key==saved['name'].casefold()or db.execute('SELECT 1 FROM native_guilds WHERE name_key=?',(key,)).fetchone():raise ValueError('Guild name already exists')
  if not any(i['template']==CARD for i in before):raise ValueError('Guild rename preview lacks owned card')
  _card(next(i for i in before if i['template']==CARD),now)
  db.execute('INSERT INTO native_guild_name_requests_v2 VALUES(?,?,?,?,?,?)ON CONFLICT(owner)DO UPDATE SET guild_id=excluded.guild_id,lease=excluded.lease,old_name=excluded.old_name,new_name=excluded.new_name,operation=excluded.operation',
   (owner,saved['id'],s.shop_session_id,saved['name'],name,operation))
  return [reply(0x297,bytes(4)+text(saved['name'])+text(name))],[]
 if len(event.payload)!=24:raise ValueError('Original guild rename confirmation size')
 code,group,slot,mode,uid=struct.unpack('>iIIiQ',event.payload)
 pending=db.execute('SELECT guild_id,lease,old_name,new_name,operation FROM native_guild_name_requests_v2 WHERE owner=?',(owner,)).fetchone()
 if pending is None or pending[:3]!=(saved['id'],s.shop_session_id,saved['name']):raise ValueError('Guild rename confirmation lost actual preview/lease')
 source=db.execute('SELECT owner,guild_id,kind FROM native_guild_operations_v2 WHERE operation=?',(pending[4],)).fetchone()
 if source!=(owner,saved['id'],0x296):raise ValueError('Guild rename preview source changed')
 if code==1004:
  db.execute('DELETE FROM native_guild_name_requests_v2 WHERE owner=?',(owner,))
  return [confirmed(db,saved,now,code)],[]
 if code!=0 or mode not in(0,1):raise ValueError('Guild rename original confirmation mode')
 if mode==0:
  if(group,slot)!=(0,0):raise ValueError('UID guild card confirmation has no position selector')
  item=next((i for i in before if i['uid']==uid),None)
 else:
  if uid:raise ValueError('Position guild card confirmation has no UID selector')
  item=next((i for i in before if(i['group'],i['slot'])==(group,slot)),None)
 item=_card(item,now);name=pending[3];key=members.name_key(name)
 if db.execute('SELECT 1 FROM native_guilds WHERE name_key=?',(key,)).fetchone():raise ValueError('Guild name was taken after preview')
 if db.execute('UPDATE native_guilds SET name=?,name_key=?,revision=revision+1 WHERE id=?AND name=?AND master_uid=?',(name,key,saved['id'],pending[2],owner)).rowcount!=1:raise ValueError('Guild rename identity changed')
 from els_server.storage.item_instances import remove
 from els_server.storage.inventory_actions import _commit
 remove(db,owner,item);after=load_items(db,owner);position=(item['group'],item['slot'])
 digest=hashlib.sha256(str(owner).encode()+b':'+str(event.kind).encode()+b':'+event.payload).hexdigest()
 _commit(db,operation,digest,owner,event.kind,[position],before,after)
 db.execute('DELETE FROM native_guild_name_requests_v2 WHERE owner=?',(owner,))
 from els_server.storage.inventory_management import _updates
 current=members.snapshot(db,owner,s.account.account_id)
 return [confirmed(db,saved,now)]+_updates([(position,None)]),[full_notification(profile(current,db=db,now=now))]

def replay(db,s,saved,kind,operation,digest,now,old):
 from els_server.storage import guild_system_state as system
 from els_server.storage.inventory_state import load_items
 from els_server.protocol.guild_system_messages import reply,text
 if kind==0x296:
  row=db.execute('SELECT old_name,new_name FROM native_guild_name_requests_v2 WHERE owner=?AND guild_id=?AND lease=?',(saved['owner'],saved['id'],s.shop_session_id)).fetchone()if system.exists(db,'native_guild_name_requests_v2')else None
  if row is None:raise ValueError('Guild rename preview has already ended')
  return [reply(0x297,bytes(4)+text(row[0])+text(row[1]))]
 code=struct.unpack('>i',bytes.fromhex(old['events'][0][1])[:4])[0]
 answer=[confirmed(db,saved,now,code)]
 if code==0:
  from els_server.storage.inventory_actions import _previous
  from els_server.storage.equipment_receipt_state import current_changes
  from els_server.storage.inventory_management import _updates
  positions=_previous(db,operation,digest)
  if positions is None:raise ValueError('Guild rename lost its inventory producer')
  answer+=_updates(current_changes(db,operation,saved['owner'],kind,positions,load_items(db,saved['owner'])))
 return answer

def failure(kind):
 from els_server.protocol.guild_system_messages import reply
 if kind==0x296:return reply(0x297,struct.pack('>iII',1,0,0))
 from els_server.protocol.guild_membership_profile import failed
 # The original299 reads the same complete basic DTO as277, without deltas.
 raw=failed(0x276).payload[4:-4]
 return reply(0x299,struct.pack('>i',1)+raw)
