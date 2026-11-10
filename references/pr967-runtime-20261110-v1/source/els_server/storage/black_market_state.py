"""Durable real-participant auctions. Caller owns writer, lease and wire guard."""
import hashlib,json,time,uuid
from els_server.domain import black_market_rules as rules
clock=lambda:int(time.time())
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'))
def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='black_market_characters'").fetchone())
def ensure(db):
 if not db.in_transaction:raise ValueError('Market schema requires writer')
 db.execute('''CREATE TABLE IF NOT EXISTS black_market_characters(
 owner INTEGER PRIMARY KEY,account_id INTEGER NOT NULL,tickets INTEGER NOT NULL CHECK(tickets BETWEEN0 AND2),
 queue_json TEXT,round_id TEXT,last_moment INTEGER NOT NULL)'''.replace('BETWEEN0 AND2','BETWEEN 0 AND 2'))
 db.execute('''CREATE TABLE IF NOT EXISTS black_market_rounds(
 id TEXT PRIMARY KEY,state_json TEXT NOT NULL,revision INTEGER NOT NULL,complete INTEGER NOT NULL CHECK(complete IN(0,1)))''')
 db.execute('''CREATE TABLE IF NOT EXISTS black_market_operations(
 operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,account_id INTEGER NOT NULL,digest TEXT NOT NULL,result_json TEXT NOT NULL)''')
 db.execute('''CREATE TABLE IF NOT EXISTS black_market_weekly_sources(
 owner INTEGER NOT NULL,week TEXT NOT NULL,run TEXT NOT NULL,source_json TEXT NOT NULL,added INTEGER NOT NULL CHECK(added IN(0,1)),
 PRIMARY KEY(owner,week))''')
def owner(db,uid,account):
 from els_server.storage.game_mail import _active_owner
 _active_owner(db,account,uid)
def character(db,uid,account,now,create=False):
 if not exists(db):
  if not create:return dict(owner=uid,account_id=account,tickets=0,queue=None,round_id=None,last_moment=0)
  ensure(db)
 row=db.execute('SELECT account_id,tickets,queue_json,round_id,last_moment FROM black_market_characters WHERE owner=?',(uid,)).fetchone()
 if row is None:
  if create:db.execute('INSERT INTO black_market_characters VALUES(?,?,0,NULL,NULL,?)',(uid,account,now))
  return dict(owner=uid,account_id=account,tickets=0,queue=None,round_id=None,last_moment=now if create else 0)
 if row[0]!=account or row[4]>now or not 0<=row[1]<=2:raise ValueError('Market saved actor/clock')
 return dict(owner=uid,account_id=account,tickets=row[1],queue=json.loads(row[2])if row[2]else None,round_id=row[3],last_moment=row[4])
def save_character(db,c,now):
 if now<c['last_moment']:raise ValueError('Market clock regression')
 db.execute('UPDATE black_market_characters SET tickets=?,queue_json=?,round_id=?,last_moment=? WHERE owner=? AND account_id=?',
  (c['tickets'],canonical(c['queue'])if c['queue']is not None else None,c['round_id'],now,c['owner'],c['account_id']))
def weekly(db,context,definition,result,now):
 """Called in the original fresh Omega weekly phase settlement, never replay."""
 if(context['dungeon']!=35940 or definition['family']!='marcus'or definition['mode']!='normal'or definition['ordinal']!=5
    or context['stage']!=0 or not result['first']or result['replayed']):return None
 if not db.in_transaction:raise ValueError('Market weekly source writer')
 ensure(db);uid=context['owner'];account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
 if account is None:raise ValueError('Market weekly owner missing')
 owner(db,uid,account[0]);week=result['week'];proof=dict(context=context,raid_source=result['source'],policy=rules.POLICY)
 old=db.execute('SELECT run,source_json,added FROM black_market_weekly_sources WHERE owner=? AND week=?',(uid,week)).fetchone()
 if old is not None:
  if old[:2]!=(context['run'],canonical(proof)):raise ValueError('Market weekly source replay conflict')
  return dict(added=old[2],replayed=True)
 c=character(db,uid,account[0],now,True);added=int(c['tickets']<2);c['tickets']+=added
 save_character(db,c,now)
 db.execute('INSERT INTO black_market_weekly_sources VALUES(?,?,?,?,?)',(uid,week,context['run'],canonical(proof),added))
 return dict(added=added,replayed=False)
def balance(db,uid):
 row=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone()
 if row is None or not 0<=row[0]<2**63 or not 0<=row[1]<2**31:raise ValueError('Market native ED balance')
 return row
def change_ed(db,uid,delta):
 before,rev=balance(db,uid);after=before+delta
 if not 0<=after<=70000000000 or rev+1>=2**31:raise ValueError('Market ED capacity')
 if db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=? AND ed=? AND revision=?',(after,rev+1,uid,before,rev)).rowcount!=1:raise ValueError('Market ED writer changed')
 return after,rev+1
def save_round(db,r):
 r['revision']+=1
 db.execute('UPDATE black_market_rounds SET state_json=?,revision=?,complete=? WHERE id=?',(canonical(r),r['revision'],int(r['phase']=='complete'),r['id']))
def round_for(db,rid):
 row=db.execute('SELECT state_json,revision,complete FROM black_market_rounds WHERE id=?',(rid,)).fetchone()
 if row is None:raise ValueError('Market original round missing')
 r=json.loads(row[0])
 if r['id']!=rid or r['revision']!=row[1]or (r['phase']=='complete')!=bool(row[2])or r['policy']!=rules.POLICY:raise ValueError('Market round identity')
 return r
def require_deletion_unlocked(db,uid):
 if not exists(db):return
 row=db.execute('SELECT queue_json,round_id FROM black_market_characters WHERE owner=?',(uid,)).fetchone()
 if row is not None and(row[0]is not None or row[1]is not None):
  from els_server.storage.character_lifecycle import LifecycleError
  raise LifecycleError('Character has an original queued or active black-market round')
def _member(r,uid,nonce):
 found=[p for p in r['people']if p['uid']==uid and p['nonce']==nonce]
 if len(found)!=1 or found[0]['closed']:raise ValueError('Market original participant unavailable')
 return found[0]
def begin(db,people,now,local):
 if len(people)not in rules.partition(len(people),local)or (local and len(people)!=1):raise ValueError('Market exact real room')
 if len({p['uid']for p in people})!=len(people)or len({p['account']for p in people})!=len(people):raise ValueError('Market duplicate actor/account')
 rid=str(uuid.uuid4());total=3 if local or len(people)<9 else 4
 for p in people:
  owner(db,p['uid'],p['account']);c=character(db,p['uid'],p['account'],now)
  if not c['queue']or c['queue']['nonce']!=p['nonce']or c['tickets']<1 or c['round_id']:raise ValueError('Market queued source changed')
  c['tickets']-=1;c['queue']=None;c['round_id']=rid;save_character(db,c,now)
 r=dict(id=rid,policy=rules.POLICY,people=[dict(p,closed=False)for p in people],local=local,lots=rules.draw(total),phase='ready',index=0,
  deadline=now+rules.catalog()['local']['ready_seconds'],created=now,last_moment=now,revision=0,sink=0,history=[])
 db.execute('INSERT INTO black_market_rounds VALUES(?,?,0,0)',(rid,canonical(r)));return r
def bid(db,r,uid,nonce,ed,now,live,issue_mail):
 p=_member(r,uid,nonce)
 if r['phase']!='bid'or now>=r['deadline']or now<r['last_moment']:raise ValueError('Market current original lot/deadline')
 lot=r['lots'][r['index']]
 if lot['winner']==uid or type(ed)is not int or not rules.minimum(lot)<=ed<=balance(db,uid)[0]:raise ValueError('Market native bid minimum/owner/ED')
 change_ed(db,uid,-ed)
 if lot['winner']:
  previous=next(p for p in r['people']if p['uid']==lot['winner'])
  if live(previous)and balance(db,previous['uid'])[0]+lot['price']<=70000000000:change_ed(db,previous['uid'],lot['price'])
  else:issue_mail(db,r,previous,lot,'refund',lot['price'],now)
 lot.update(winner=uid,price=ed);r['deadline']=now+10;r['last_moment']=now;save_round(db,r);return r
def advance(db,r,now,issue_mail):
 if now<r['last_moment']:raise ValueError('Market round clock regression')
 if r['phase']=='complete'or now<r['deadline']:return False
 if r['phase']in('ready','between'):
  if r['phase']=='between':r['index']+=1
  r['phase']='bid';r['deadline']=now+10
 elif r['phase']=='bid':
  lot=r['lots'][r['index']]
  if lot['settled']:raise ValueError('Market duplicate lot settlement')
  if lot['winner']:
   winner=next(p for p in r['people']if p['uid']==lot['winner']);issue_mail(db,r,winner,lot,'winning',0,now)
   others=[p for p in r['people']if p['uid']!=lot['winner']];share=0 if r['local']else (lot['price']*90)//(100*len(others))
   if share:
    for p in others:issue_mail(db,r,p,lot,'distribution',share,now)
   r['sink']+=lot['price']-share*len(others)
  lot['settled']=True;r['history'].append(dict(lot));r['phase']='complete'if r['index']+1==len(r['lots'])else 'between'
  r['deadline']=now+rules.catalog()['local']['final_seconds'if r['phase']=='complete'else 'between_seconds']
  if r['phase']=='complete':
   for p in r['people']:
    c=character(db,p['uid'],p['account'],now)
    if c['round_id']!=r['id']:raise ValueError('Market original participant round changed')
    c['round_id']=None;save_character(db,c,now)
 r['last_moment']=now;save_round(db,r);return True
