"""Original F-camp auction requests, real leases and precommitted projections."""
from contextlib import closing
from pathlib import Path
import hashlib,sqlite3
from els_server.domain import black_market_rules as rules
from els_server.storage import black_market_state as store
from els_server.storage.black_market_mail import issue as issue_mail
from els_server.protocol import black_market_messages as wire
from els_server.protocol.protocol_codec import encode_event
KINDS=(0xd3b,0xd3d,0xd43,0xd47)
def _actor(s):
 from els_server.domain.equipment_chip_flow import reset_authority
 from els_server.domain.dungeon_hp_c1 import _lease
 from els_server.domain.raid_economy_flow import application
 app=application(s)
 if(app is None or getattr(s,'released',False)or s.role!='game'or s.client_build!='dx11_260923'or not s.item_test
    or s.account.store is None or s.phase!='town_ready'or not {0x28,0x225,0x227}<=s.completed
    or getattr(s,'coop_error',None)or getattr(s,'social_overflow',False)):raise ValueError('Market current original loaded actor')
 reset_authority(s)
 if not _lease(s):raise ValueError('Market current original lease')
 return (s.account,s.account.store,s.account.uid,s.account.account_id,s.shop_session_id,app)
def _guard(s,binding,db,now,camp=False):
 if _actor(s)!=binding or not db.in_transaction:raise ValueError('Market actor generation changed')
 main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
 if(len(main)!=1 or Path(main[0][2]).resolve()!=Path(binding[1].path).resolve()or any(r[1]not in('main','temp')for r in db.execute('PRAGMA database_list'))or db.execute('PRAGMA foreign_keys').fetchone()!=(1,)):raise ValueError('Market exact native writer')
 store.owner(db,binding[2],binding[3])
 if camp:
  from els_server.domain.assembly_flow import _actor as assembly_actor,_guard as assembly_guard
  assembly_guard(s,assembly_actor(s),town=True)(db,now)
  if s.active_map!=1012 or s.dungeon_return_pending or getattr(s,'town_warp_transition',None)is not None:raise ValueError('Market exact original F scene')
 return True
def _member(s,db):
 from els_server.storage.seal_quests import load_character
 c=load_character(db,s.account.uid,s.account.account_id);loc=db.execute('SELECT town,board FROM location WHERE uid=?',(s.account.uid,)).fetchone()
 return dict(uid=s.account.uid,account=s.account.account_id,nonce=s.shop_session_id,name=c['name'],level=c['level'],unit_type=c['unit_type'],unit_class=c['unit_class'],line=loc[1])
def _register(s,b):
 app=b[-1]
 if not hasattr(app,'_black_market_sessions'):app._black_market_sessions={}
 # Replacement invalidates this character's older generation. Other actors
 # are checked in their actual request, notification or active-round path.
 for key in list(app._black_market_sessions):
  if key[0]==b[2]and key!=(b[2],b[4]):app._black_market_sessions.pop(key,None)
 app._black_market_sessions[(b[2],b[4])]=s
 pending=getattr(s,'_black_market_local_pending',None)
 if pending is not None and pending[:2]!=(b[2],b[4]):s._black_market_local_pending=None
 return app
def _live(app,p,db,now):
 s=getattr(app,'_black_market_sessions',{}).get((p['uid'],p['nonce']))
 if s is None:return False
 try:
  b=_actor(s)
  if b[-1]is not app or b[3]!=p['account']or s.active_map!=1012:return False
  _guard(s,b,db,now,True)
  return db.execute('SELECT board FROM location WHERE uid=?',(p['uid'],)).fetchone()==(p['line'],)
 except(ValueError,AttributeError):return False
def _round_events(r,uid):
 p=next(p for p in r['people']if p['uid']==uid);total=len(r['lots']);index=r['index']+1
 if p['closed']:return []
 if r['phase']=='ready':return [wire.lot(dict(template=0,quantity=0,opening=0,tier=0),1,total,r['deadline'])]
 lot=r['lots'][r['index']]
 if r['phase']=='bid':return [wire.lot(lot,index,total,r['deadline'])]
 share=0 if r['local']or not lot['winner']else (lot['price']*90)//(100*(len(r['people'])-1))
 return [wire.finished(lot,index,total,share,r['deadline'],r['history'],r['people'])]
def _projection(s,db,now,rounds):
 b=_actor(s);c=store.character(db,b[2],b[3],now);out=[];updates={};start,end=rules.window(now)
 snap=(b[2],b[4],c['tickets'],start,end,start<=now<end)
 if snap!=getattr(s,'_black_market_snapshot',None):
  out+=[wire.tickets(c['tickets'],start,end),wire.availability(snap[-1],end if snap[-1]else start)];updates['snapshot']=snap
 seen=getattr(s,'_black_market_seen',{});wanted={r['id']:r for r in rounds}
 rid=c['round_id']or getattr(s,'_black_market_round',None)
 if rid and store.exists(db):wanted.setdefault(rid,store.round_for(db,rid))
 for r in wanted.values():
  p=next((p for p in r['people']if p['uid']==b[2]and p['nonce']==b[4]),None)
  if p is None or p['closed']or seen.get(r['id'])==r['revision']:continue
  if r['id']not in seen:out+=[wire.result(0xd3f),wire.roster(r['people'])]
  out+=_round_events(r,b[2]);updates.setdefault('seen',{})[r['id']]=r['revision'];updates['round']=r['id']
 return out,updates
def _publish(s,updates):
 if 'snapshot'in updates:s._black_market_snapshot=updates['snapshot']
 if 'seen'in updates:s._black_market_seen={**getattr(s,'_black_market_seen',{}),**updates['seen']}
 if 'round'in updates:s._black_market_round=updates['round']
def _tick(app,db,now):
 changed=[];extra={};observed={}
 def live(p):
  key=(p['uid'],p['nonce'])
  if key not in observed:observed[key]=_live(app,p,db,now)
  return observed[key]
 if not store.exists(db):return changed,extra
 rows=db.execute('SELECT owner,account_id,queue_json,round_id FROM black_market_characters WHERE queue_json IS NOT NULL OR round_id IS NOT NULL').fetchall()
 queued=[]
 for uid,aid,queue,rid in rows:
  c=store.character(db,uid,aid,now)
  if queue:
   p=c['queue']
   if not live(p):c['queue']=None;store.save_character(db,c,now)
   elif now>=p['end']:queued.append((p['end'],p['order'],p,c))
 for cutoff in sorted({x[0]for x in queued}):
  batch=sorted((x for x in queued if x[0]==cutoff),key=lambda x:x[1]);sizes=rules.partition(len(batch),app.config.mode=='local')if rules.catalog()['admissions_enabled']else []
  if not sizes:
   for _,_,p,c in batch:
    c['queue']=None;store.save_character(db,c,now);extra[(p['uid'],p['nonce'])]=[wire.result(0xd3f,-1)]
  else:
   at=0
   for size in sizes:
    people=[v[2]for v in batch[at:at+size]];at+=size
    changed.append(store.begin(db,people,now,app.config.mode=='local'))
 for(rid,)in db.execute('SELECT id FROM black_market_rounds WHERE complete=0').fetchall():
  r=store.round_for(db,rid);closed=False
  for p in r['people']:
   if not p['closed']and not live(p):p['closed']=True;closed=True
  if closed:store.save_round(db,r)
  if store.advance(db,r,now,issue_mail)or closed:changed.append(r)
 return changed,extra
def transact(s,event=None,sequence=None):
 b=_actor(s);app=_register(s,b);kind=event.kind if event is not None else None
 pending=getattr(s,'_black_market_local_pending',None)
 pending_messages=list(pending[2])if pending is not None else []
 with closing(sqlite3.connect(b[1].path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=store.clock();_guard(s,b,db,now)
  # The application worker reconciles deadlines even with zero sessions.
  # Periodic projections must not repeat its full roster scan per observer.
  changed,extra=_tick(app,db,now)if event is not None else([],{});answer=[]
  if event is not None:
   _guard(s,b,db,now,True)
   if(type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Market native request envelope')
   value=wire.request(kind,event.payload,b[2]);ensure=rules.catalog()['admissions_enabled']
   if not ensure and kind not in(0xd3d,0xd47):raise ValueError('Market new admissions closed')
   store.ensure(db);operation=b[4]+':black-market:'+str(b[2])+':'+str(sequence);digest=hashlib.sha256(str(kind).encode()+event.payload).hexdigest()
   previous=db.execute('SELECT owner,account_id,digest FROM black_market_operations WHERE operation=?',(operation,)).fetchone()
   if previous is not None and previous!=(b[2],b[3],digest):raise ValueError('Market native request replay conflict')
   c=store.character(db,b[2],b[3],now,True)
   if previous is None:
    cur=db.execute('INSERT INTO black_market_operations VALUES(?,?,?,?,?)',(operation,b[2],b[3],digest,'{}'))
    if kind==0xd3b:
     start,end=rules.window(now)
     if not start<=now<end or c['tickets']<1 or c['round_id']or c['queue']:raise ValueError('Market time/ticket/queue admission')
     other=db.execute('SELECT owner FROM black_market_characters WHERE account_id=? AND(queue_json IS NOT NULL OR round_id IS NOT NULL)',(b[3],)).fetchall()
     if other:raise ValueError('Market original account already participating')
     c['queue']=dict(_member(s,db),start=start,end=end,order=cur.lastrowid);store.save_character(db,c,now)
    elif kind==0xd3d:
     if c['round_id']:raise ValueError('Market matching cancellation after start')
     c['queue']=None;store.save_character(db,c,now)
    elif kind==0xd43:
     if c['round_id']is None:raise ValueError('Market actual round unavailable')
     r=store.round_for(db,c['round_id'])
     if r['id']in {x['id']for x in changed}:raise ValueError('Market old boundary bid')
     r=store.bid(db,r,b[2],b[4],value,now,lambda p:_live(app,p,db,now),issue_mail);changed.append(r)
    elif kind==0xd47:
     rid=c['round_id']or getattr(s,'_black_market_round',None)
     if rid:
      r=store.round_for(db,rid);p=store._member(r,b[2],b[4]);p['closed']=True;store.save_round(db,r);changed.append(r)
     c['queue']=None;store.save_character(db,c,now)
    db.execute('UPDATE black_market_operations SET result_json=? WHERE operation=?',(store.canonical(dict(kind=kind,round=c['round_id'],at=now)),operation))
   answer+=[wire.balance(*store.balance(db,b[2]),code=0)]if kind==0xd43 else[wire.result({0xd3b:0xd3c,0xd3d:0xd3e,0xd47:0xd48}[kind])]
  plans=[]
  for key,peer in list(getattr(app,'_black_market_sessions',{}).items()):
   if peer is not s and not changed and key not in extra:continue
   try:peer_bound=_actor(peer)
   except(ValueError,AttributeError):continue
   if peer_bound[-1]is not app or key!=(peer_bound[2],peer_bound[4]):continue
   try:_guard(peer,peer_bound,db,now)
   except(ValueError,AttributeError):continue
   messages,updates=_projection(peer,db,now,changed);messages=extra.get(key,[])+messages
   if peer is s:messages=pending_messages+answer+messages
   # D44 handles the winning bidder; D45 updates prior and watching balances.
   if peer is not s and any(any(p['uid']==peer_bound[2]for p in r['people'])for r in changed):messages+=[wire.balance(*store.balance(db,peer_bound[2]))]
   for e in messages:encode_event(e)
   if peer is not s:
    box=peer.mailbox
    if len(box.messages)+len(box.moves)+len(messages)>256 or box.bytes+sum(len(e.payload)for e in messages)>256*1024:raise ValueError('Market bounded native outbox')
   plans.append((peer,peer_bound,messages,updates))
  for peer,pb,messages,updates in plans:_guard(peer,pb,db,now)
  _guard(s,b,db,now)
 # Publish only after the original SQLite writer commits all escrow and bytes.
 own=[]
 for peer,pb,messages,updates in plans:
  _publish(peer,updates)
  if peer is s:own=messages
  else:
   for message in messages:app.world.send(peer,message)
 if pending is not None:s._black_market_local_pending=None
 return own
def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in KINDS:return None
 try:return transact(s,event,sequence)
 except(ValueError,sqlite3.Error,OverflowError):
  try:
   b=_actor(s)
   with closing(sqlite3.connect(b[1].path))as db:
    reply=wire.balance(*store.balance(db,b[2]),code=-1)if event.kind==0xd43 else wire.result({0xd3b:0xd3c,0xd3d:0xd3e,0xd47:0xd48}[event.kind],-1)
    encode_event(reply);return[reply]
  except(ValueError,AttributeError,sqlite3.Error):return []
def periodic(s):
 try:
  # No-authority fast path emits nothing and writes nothing. Every changed
  # notice still passes the complete original actor/writer guards in transact.
  # Read the current SQL state each time: no time-based or cross-write cache.
  if s.phase!='town_ready'or not {0x28,0x225,0x227}<=s.completed:return []
  pending=getattr(s,'_black_market_local_pending',None)
  if pending is None:
   uid=s.account.uid;aid=s.account.account_id;nonce=s.shop_session_id
   with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
    db.execute('BEGIN');now=store.clock();c=store.character(db,uid,aid,now);start,end=rules.window(now)
    snapshot=(uid,nonce,c['tickets'],start,end,start<=now<end)
    rid=c['round_id']or getattr(s,'_black_market_round',None)
    revision=db.execute('SELECT revision FROM black_market_rounds WHERE id=?',(rid,)).fetchone()if rid and store.exists(db)else None
    if snapshot==getattr(s,'_black_market_snapshot',None)and(revision is None or getattr(s,'_black_market_seen',{}).get(rid)==revision[0]):return []
  return transact(s)
 except(ValueError,AttributeError,sqlite3.Error,OverflowError):return []
def synchronize(s,events):return events+periodic(s)

def tick_application(app):
 """Paid rounds settle even when every original participant disconnected."""
 from els_server.application import Application
 if type(app)is not Application or app.config.profile!='integrated_dx11':return
 with closing(sqlite3.connect(app.config.state_file,timeout=10))as db,db:
  if not store.exists(db):return
  if db.execute('SELECT 1 FROM black_market_characters WHERE queue_json IS NOT NULL OR round_id IS NOT NULL LIMIT 1').fetchone()is None:return
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=store.clock();changed,extra=_tick(app,db,now);plans=[]
  if not changed and not extra:return
  for key,s in list(getattr(app,'_black_market_sessions',{}).items()):
   try:b=_actor(s);_guard(s,b,db,now)
   except(ValueError,AttributeError):continue
   if b[-1]is not app or key!=(b[2],b[4]):continue
   messages,updates=_projection(s,db,now,changed);messages=extra.get(key,[])+messages
   if any(any(p['uid']==b[2]for p in r['people'])for r in changed):messages+=[wire.balance(*store.balance(db,b[2]))]
   for e in messages:encode_event(e)
   box=getattr(s,'mailbox',None)
   # The independent local transport consumes its own original Event list on
   # its next periodic cycle; preserve committed notices across that handoff.
   if box is None:
    pending=getattr(s,'_black_market_local_pending',None)
    old=list(pending[2])if pending is not None and pending[:2]==(b[2],b[4])else []
    if len(old)+len(messages)>256 or sum(len(e.payload)for e in old+messages)>256*1024:raise ValueError('Market local outbox capacity')
   elif len(box.messages)+len(box.moves)+len(messages)>256 or box.bytes+sum(len(e.payload)for e in messages)>256*1024:raise ValueError('Market application outbox capacity')
   plans.append((s,b,messages,updates))
  for s,b,messages,updates in plans:_guard(s,b,db,now)
 for s,b,messages,updates in plans:
  _publish(s,updates)
  if getattr(s,'mailbox',None)is None:
   pending=getattr(s,'_black_market_local_pending',None);old=list(pending[2])if pending is not None and pending[:2]==(b[2],b[4])else []
   s._black_market_local_pending=(b[2],b[4],old+messages)
  else:
   for e in messages:app.world.send(s,e)

async def run_application(app):
 import asyncio,logging
 last_error=None
 while getattr(app,'_black_market_alive',False):
  await asyncio.sleep(.5)
  try:
   await app.call(tick_application,app);app._black_market_error=None;last_error=None
  except asyncio.CancelledError:raise
  except Exception as error:
   value=type(error).__name__+': '+str(error);app._black_market_error=value
   if value!=last_error:logging.getLogger('els.black_market').exception('Black market transaction refused; durable escrow retained')
   last_error=value
