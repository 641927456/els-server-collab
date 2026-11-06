from pathlib import Path
import asyncio,gc,hashlib,json,sqlite3,struct,sys,tempfile
from contextlib import closing,ExitStack
W=Path(__file__).resolve().parent;binding=json.loads((W/'candidate-manifest.json').read_bytes());runtime=Path(binding['runtime']);fixed='--fixed' in sys.argv
sys.dont_write_bytecode=True;sys.path.insert(0,str(runtime))
if fixed:
 import els_server.domain
 els_server.domain.__path__.insert(0,str(W/'candidate/els_server/domain'))
from els_server.domain.local_session import LocalAccount,SessionOrderError
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.storage.quick_start import change_career
from els_server.domain.careers import PARENTS
from els_server.domain.character_rules import CLASSES
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.application import Application
from els_server.config import ServerConfig

def request(destination=20010,flag=1,performers=(0,)):
 return Event(0x202,kind=0x225,payload=struct.pack('>iB',destination,flag),performers=performers)
checks=[]
with tempfile.TemporaryDirectory(dir=W,prefix='owned-entry-') as temp,ExitStack() as cleanup:
 path=Path(temp)/'game.sqlite3';root=LocalAccount(LocalState(path));root.enable_characters()
 uid=root.characters.create('EntryProbe',8,'create',quick_start=True)['uid'];account=root.for_character(uid)
 q=QuestState(path,uid,account_id=1,account_source_guard=lambda db:None)
 for index,dungeon in enumerate((30000,30102,30252,33202)):
  qid=169600+index
  event=dict(kind='kill' if index==0 else 'clear',dungeon=dungeon,level=account.character()['level'],rank=None)
  if index==0:event['npc']=5
  q.record('clear-'+str(qid),event,b'owned-controlled-dungeon-proof')
  q.action('claim',dict(quest=qid,npc=0),'claim-'+str(qid),lambda result:[])
  if index in(0,1,3):
   current=account.character()['unit_class'];target=next(c for c,p in PARENTS.items() if p==current and c in CLASSES)
  else:target=0
  change_career(path,uid,1,target,'career-'+str(index),lambda db:None,lambda *args:[])
 assert account.character()['level']==99 and CLASSES[account.character()['unit_class']]['stage']==3
 assert 169604 in {r['id'] for r in q.snapshot()['active']}
 assert not any(i['template']==719707 for i in account.get_inventory_snapshot()['items'])
 app=Application(ServerConfig(state_file=path,log_dir=Path(temp)/'logs'));app.account=root
 loop=asyncio.new_event_loop();cleanup.callback(loop.close);cleanup.callback(app.close)
 s=loop.run_until_complete(app.session());cleanup.callback(lambda:loop.run_until_complete(app.release(s)))
 s.account=account;s.completed.add(0x28);s.role='game';s.phase='map_loading';s.active_map=s.pending_map=20000
 def dump():
  with closing(sqlite3.connect(path)) as db:return '\n'.join(db.iterdump())
 def enter(event,sequence):
  response=s.handle(event,sequence)
  for packet in response:encode_event(packet)
  return struct.unpack('>5i',next(e for e in response if e.kind==0x226).payload)
 from els_server.domain.town_travel import catalog
 assert enter(request(20000,0),8)[0]==0
 home=catalog()['towns']['20000']['xyz']
 initial=s.handle(Event(0x202,kind=0x227,payload=struct.pack('>fffBH',*home,0,0),performers=(0,)),9)
 assert next(e for e in initial if e.kind==0x228).payload==bytes(4) and s.phase=='town_ready'
 frozen=dump();ack=enter(request(),10)
 if not fixed:
  assert ack[0]==515 and s.phase=='town_ready' and dump()==frozen
  checks.append('qualified native activity225 rejected515 by installed parent, without58C')
 else:
  assert ack==(0,20010,0,0,0) and s.phase=='square_accepted' and s.pending_map==20010
  assert dump()==frozen
  checks.append('qualified native225 accepted without fee or save mutation before227')
  assert enter(request(),11)==ack and dump()==frozen
  checks.append('duplicate225 remains eligible and has no persistent increment')
  from els_server.domain.town_travel import catalog
  xyz=catalog()['towns']['20010']['xyz']
  replies=s.handle(Event(0x202,kind=0x227,payload=struct.pack('>fffBH',*xyz,0,0),performers=(0,)),12)
  for packet in replies:encode_event(packet)
  assert next(e for e in replies if e.kind==0x228).payload==bytes(4)
  assert s.phase=='town_ready' and account.get_location()['map']==20010
  cold=LocalAccount(LocalState(path,uid),1);assert cold.get_location()['map']==20010
  checks.append('227 completes original town persistence and cold reload')
  assert 169604 in {r['id'] for r in q.snapshot()['active']}
  assert not any(i['template']==719707 for i in account.get_inventory_snapshot()['items'])
  checks.append('entry does not complete final task or issue master ticket')
  # Isolated fixture only: denial cases do not change any persistent state.
  with closing(sqlite3.connect(path)) as db:db.execute('UPDATE location SET town=20000 WHERE uid=?',(uid,));db.commit()
  account.location=account.store.load();s.active_map=s.pending_map=20000
  for label,event in (('unrelated destination',request(20009)),('wrong performer',request(20010,1,(1,)))):
   frozen=dump()
   try:ack=enter(event,20)
   except SessionOrderError:
    assert label=='wrong performer'
   else:assert ack[0]!=0,(label,ack)
   assert dump()==frozen,label
   checks.append(label+' rejected without writes')
  for label,sql in (
   ('lower level','UPDATE characters SET level=98 WHERE uid=?'),
   ('missing transcendence','UPDATE characters SET transcendence=0 WHERE uid=?'),
   ('master already completed','UPDATE characters SET master=1 WHERE uid=?'),
   ('other enrolled identity','DELETE FROM quick_start_accounts WHERE uid=?'),
   ('missing final active quest','DELETE FROM character_quests WHERE owner=? AND quest=169604'),
   ('missing previous reward','DELETE FROM completed_quests WHERE owner=? AND quest=169603'),
  ):
   # Preserve this owned fixture using an explicit transaction and undo only the changed rows.
   with closing(sqlite3.connect(path)) as db:
    if sql.startswith('UPDATE characters'):
     old=db.execute('SELECT level,transcendence,master FROM characters WHERE uid=?',(uid,)).fetchone()
    elif 'quick_start_accounts' in sql:old=db.execute('SELECT * FROM quick_start_accounts WHERE uid=?',(uid,)).fetchone()
    elif 'character_quests' in sql:old=db.execute('SELECT * FROM character_quests WHERE owner=? AND quest=169604',(uid,)).fetchone()
    else:old=db.execute('SELECT * FROM completed_quests WHERE owner=? AND quest=169603',(uid,)).fetchone()
    db.execute(sql,(uid,));db.commit()
   from els_server.domain.quick_start_flow import authorize_town_entry
   frozen=dump();assert not authorize_town_entry(s,request(),30),label
   assert dump()==frozen,label
   with closing(sqlite3.connect(path)) as db:
    if sql.startswith('UPDATE characters'):db.execute('UPDATE characters SET level=?,transcendence=?,master=? WHERE uid=?',(*old,uid))
    else:
     table='quick_start_accounts' if 'quick_start_accounts' in sql else 'character_quests' if 'character_quests' in sql else 'completed_quests'
     db.execute('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in old)+')',old)
    db.commit()
   checks.append(label+' denied by admission predicate without writes')
  # Fifth task's existing reward remains the only source of719707.
  q.record('owned-final-clear',dict(kind='clear',dungeon=34060,level=99,rank=None),b'owned-final-controlled-proof')
  q.action('claim',dict(quest=169604,npc=0),'claim-final',lambda result:[])
  assert sum(i['count'] for i in account.get_inventory_snapshot()['items'] if i['template']==719707)==1
  frozen=dump();q.action('claim',dict(quest=169604,npc=0),'claim-final',lambda result:[]);assert dump()==frozen
  checks.append('existing final reward grants one719707 and replay does not duplicate it')
 result=dict(ok=True,fixed=fixed,checks=checks,layer='real Application lease + LocalSession225/227 + isolated SQLite + existing controlled quest/career transactions',natural_GUI=False,production_writes=False,client_changes=0)
 gc.collect()
(W/('candidate-tests.json' if fixed else 'baseline-tests.json')).write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result))
