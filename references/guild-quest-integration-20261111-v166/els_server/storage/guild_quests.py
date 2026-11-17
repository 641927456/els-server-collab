"""Guild task reset, immutable progress and honor in the producer's transaction."""
import hashlib,json,time
from els_server.domain import guild_quests as rules,guild_rules
from els_server.storage import guild_system_state as system

def _json(v):return json.dumps(v,sort_keys=True,separators=(',',':'))

def depart(db,owner):
 if not db.in_transaction:raise ValueError('Guild departure requires caller transaction')
 if system.exists(db,'character_quests'):
  for quest, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(owner,)).fetchall():
   if rules.contains(quest):db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?',(owner,quest))

def rollover(db,owner,now):
 if not db.in_transaction:raise ValueError('Guild task caller transaction required')
 db.execute('CREATE TABLE IF NOT EXISTS native_guild_quest_weeks_v2(owner INTEGER PRIMARY KEY REFERENCES characters(uid),week INTEGER NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS native_guild_quest_history_v2(owner INTEGER NOT NULL,week INTEGER NOT NULL,state_json TEXT NOT NULL,PRIMARY KEY(owner,week))')
 period=guild_rules.week(now);old=db.execute('SELECT week FROM native_guild_quest_weeks_v2 WHERE owner=?',(owner,)).fetchone()
 if old is not None and old[0]>period:raise ValueError('Guild task clock moved before saved week')
 if old is not None and old[0]==period:return False
 active=[];done=[]
 for row in db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=?',(owner,)):
  if rules.weekly(row[0]):active.append(row)
 for row in db.execute('SELECT quest,completed_at,reward_json FROM completed_quests WHERE owner=?',(owner,)):
  if rules.weekly(row[0]):done.append(row)
 archived={}
 for rows,table,key in((active,'character_quests','active'),(done,'completed_quests','completed')):
  for row in rows:
   source_period=old[0]if old is not None else guild_rules.week(row[1])
   if source_period==period:continue
   archived.setdefault(source_period,dict(active=[],completed=[]))[key].append(row)
   db.execute('DELETE FROM '+table+' WHERE owner=?AND quest=?',(owner,row[0]))
 for source_period,state in archived.items():
  db.execute('INSERT INTO native_guild_quest_history_v2 VALUES(?,?,?)',(owner,source_period,_json(state)))
 db.execute('INSERT INTO native_guild_quest_weeks_v2 VALUES(?,?)ON CONFLICT(owner)DO UPDATE SET week=excluded.week',(owner,period))
 return bool(archived)

def before_action(store,db,qid,operation,kind,now):
 if not callable(store.account_source_guard):raise ValueError('Guild task requires current actor')
 store.account_source_guard(db)
 from els_server.storage.guild_membership_state import snapshot
 if snapshot(db,store.uid,store.account_id)is None:raise ValueError('Guild task requires actual membership')
 rollover(db,store.uid,now)
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_quest_operations_v2(
  operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,quest INTEGER NOT NULL,kind TEXT NOT NULL,week INTEGER NOT NULL)''')
 old=db.execute('SELECT owner,quest,kind,week FROM native_guild_quest_operations_v2 WHERE operation=?',(operation,)).fetchone()
 if old is not None:
  if old[:3]!=(store.uid,qid,kind):raise ValueError('Guild task operation identity changed')
  if rules.weekly(qid)and old[3]!=guild_rules.week(now):raise ValueError('Guild task request belongs to a previous reset')

def after_action(store,db,qid,operation,kind,now):
 db.execute('INSERT OR IGNORE INTO native_guild_quest_operations_v2 VALUES(?,?,?,?,?)',(operation,store.uid,qid,kind,guild_rules.week(now)))
 store.account_source_guard(db)

def _active(db,owner,now):
 from els_server.storage.periodic_quest_scope import active_rows
 from els_server.storage.seal_quests import _state
 rows=active_rows(db,owner,quest_ids=frozenset(map(int,rules.catalog()['quests'])))
 return _state(db,owner,None,now=now,progress_only=True,active_rows=rows)['active']

def record(db,owner,operation,activities,now):
 if not db.in_transaction:raise ValueError('Guild progress requires actual producer writer')
 activities=tuple(tuple(row)for row in activities)
 if any(len(r)!=3 or any(type(n)is not int for n in r)or r[0]not in(1,10,65,66,67,68,69,99,100)or not 0<r[1]<2**31 or r[2]<0 for r in activities):raise ValueError('Guild progress activity')
 if not activities:return []
 from els_server.storage.seal_quests import ensure
 from els_server.storage.guild_membership_state import snapshot
 account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
 if account is None:raise ValueError('Guild progress owner')
 saved=snapshot(db,owner,account[0])
 if saved is None:return []
 ensure(db);rollover(db,owner,now)
 db.execute('CREATE TABLE IF NOT EXISTS native_guild_quest_facts_v2(operation TEXT NOT NULL,owner INTEGER NOT NULL,week INTEGER NOT NULL,facts_json TEXT NOT NULL,PRIMARY KEY(operation,owner))')
 raw=_json(dict(guild=saved['id'],activities=activities,at=now))
 old=db.execute('SELECT week,facts_json FROM native_guild_quest_facts_v2 WHERE operation=?AND owner=?',(operation,owner)).fetchone()
 if old is not None:
  if old!=(guild_rules.week(now),raw):raise ValueError('Guild progress producer changed')
  return []
 changed=[]
 for row in _active(db,owner,now):
  counts=dict(row['objectives'])
  for sid in counts:
   sub=rules.catalog()['subquests'][str(sid)]
   counts[sid]=min(rules.target(sub),counts[sid]+rules.increment(sub,activities))
  if counts!=row['objectives']:
   if db.execute('UPDATE character_quests SET objectives=?WHERE owner=?AND quest=?AND generation=?',(_json(counts),owner,row['id'],row['generation'])).rowcount!=1:raise ValueError('Guild objective generation changed')
   changed.append(dict(row,objectives=counts))
 db.execute('INSERT INTO native_guild_quest_facts_v2 VALUES(?,?,?,?)',(operation,owner,guild_rules.week(now),raw))
 from els_server.protocol.quest_messages import progress
 from els_server.protocol.protocol_codec import encode_event
 events=[progress(changed)]if changed else []
 for e in events:encode_event(e)
 return events

def honor(db,owner,amount,operation,kind,digest,now,*,dungeon=False):
 from els_server.storage.guild_membership_state import snapshot
 account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
 if account is None:raise ValueError('Guild honor owner')
 saved=snapshot(db,owner,account[0])
 if saved is None:return []
 if dungeon:
  from els_server.domain.guild_fountain import honor_rate
  amount=int(amount*(1+honor_rate(saved,now)))
 if amount==0:return []
 added=system.honor(saved['system'],owner,amount,now)
 system.record(db,operation,digest,saved['id'],owner,kind,dict(honor=added),now)
 system.write(db,saved['id'],saved['system'])
 return record(db,owner,operation,[(100,added,0)]if added else [],now)

def pvp(db,owner,operation,digest,played,win,now):
 if not played:return []
 events=honor(db,owner,dict(guild_rules.calls('SetGuildHonorPoint'))[1],operation+':honor',0xc2,digest,now)
 if win:events+=record(db,owner,operation,[(10,1,0)],now)
 if not events:return []
 return _active(db,owner,now)
