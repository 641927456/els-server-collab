"""Original automatic Guild Expedition: native frozen CP and source-backed rewards."""
import hashlib,json,math,struct,secrets
from pathlib import Path
from els_server.domain import guild_rules as rules
from els_server.storage import guild_system_state as system
KINDS=frozenset((0xaba,0xabc,0xabe,0xac0))
def reply(*a,**kw):
 from els_server.protocol.guild_system_messages import reply as native
 return native(*a,**kw)
def text(value):
 from els_server.protocol.guild_system_messages import text as native
 return native(value)

def definitions():
 from els_server.game_data import client_data
 from els_server.domain.activity_2026_stack_policy import effective_stack
 raw=(Path(__file__).resolve().parents[1]/'data/guild_expedition_rewards.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='2011f77bdec69598049ec8bf6de1205c308799d83aad3ab7266e1ffc6e5135c8':raise ValueError('Guild expedition reward source')
 for row in json.loads(raw):
  if hashlib.sha256(client_data().item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Guild expedition reward differs from current client')
  yield dict(template=row['template'],metadata=row['metadata'],group=row['group'],max_stack=effective_stack(row['max_stack']))

def initial_smashes():
 value=json.loads((Path(__file__).resolve().parents[1]/'data/guild_expedition_policy.json').read_bytes())['initial_smashes']
 if value is None:return None
 if type(value)is not int or not 0<=value<=rules.expedition_rules()['HitMaxCount']:raise ValueError('Guild first-smash policy requires explicit decision')
 return value

def _new(now):
 return dict(week=rules.week(now),stage=1,stages={},charges={},charge_starts={},updated=now,revision=0)

def _stage(exp,n,now):
 return exp['stages'].setdefault(str(n),dict(number=n,hp=int(rules.expedition_rules()['StageInfo'][str(n)]['HP'])*500,
  updated=now,started=0,cleared=0,participants={}))

def _active(stage,when):
 return [p for p in stage['participants'].values()if not p.get('left')and p['until']>when]

def _award(db,saved,exp,stage,now,notices):
 n=stage['number'];operation=f"guild-expedition:{saved['id']}:{exp['week']}:{n}:clear"
 source=dict(week=exp['week'],stage=n,completed=now,participants=stage['participants'])
 digest=hashlib.sha256(json.dumps(source,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 system.record(db,operation,digest,saved['id'],0,0xac1,source,now)
 coins=banner=0
 from els_server.domain.guild_emblems import parts,acquire
 for sn,kind,template,count in rules.calls('AddGuildExpeditionClearGuildReward'):
  if sn!=n:continue
  if kind==1:
   if template!=400152:raise ValueError('Guild expedition coin source')
   coins+=count
  elif kind==2:
   if template!=400153:raise ValueError('Guild expedition banner point source')
   banner+=count
  elif kind==3:
   if count!=1:raise ValueError('Guild expedition emblem quantity')
   if str(template)not in parts(saved['system']):acquire(saved['system'],template,now)
  else:raise ValueError('Guild expedition reward category')
 system.change_currency(db,saved['id'],coins,banner,operation,'current expedition stage clear',now)
 ranking=sorted((p for p in stage['participants'].values()if not p.get('left')),key=lambda p:(-p['damage'],p['joined'],p['uid']))
 for place,p in enumerate(ranking,1):
  reward={}
  for sn,t,q in rules.calls('AddGuildExpeditionClearUserReward'):
   if sn==n:reward[t]=reward.get(t,0)+q
  for sn,rank,t,q in rules.calls('AddGuildExpeditionClearRankingReward'):
   if(sn,rank)==(n,place):reward[t]=reward.get(t,0)+q
  p.update(rank=place,rewards={str(t):q for t,q in reward.items()})
 stage['cleared']=now;exp['stage']=min(12,n+1)
 if notices is not None:
  from els_server.protocol.native_notice_messages import achievement
  notices.append(achievement(26,saved['name'],n))

def _advance(db,saved,exp,now,notices):
 if now<exp['updated']:raise ValueError('Guild expedition clock moved backwards')
 stage=exp['stages'].get(str(exp['stage']))
 if stage is not None and not stage['cleared']:
  clock=stage['updated']
  while clock<now and stage['hp']>0:
   active=_active(stage,clock);end=min([now]+[p['until']for p in active])
   if not active:clock=now;break
   cp=sum(p['combat']for p in active)
   if cp==0:clock=end;continue
   duration=min(end-clock,(stage['hp']+cp-1)//cp)
   proposed={p['uid']:p['combat']*duration for p in active};total=sum(proposed.values())
   used=min(stage['hp'],total)
   allocation={uid:amount*used//total for uid,amount in proposed.items()}
   remaining=used-sum(allocation.values())
   for uid in sorted(allocation,key=lambda uid:(-(proposed[uid]*used%total),uid))[:remaining]:allocation[uid]+=1
   for p in active:p['damage']+=allocation[p['uid']]
   stage['hp']-=used;clock+=duration
   if stage['hp']==0:_award(db,saved,exp,stage,clock,notices)
  stage['updated']=now
 exp['updated']=now

def _mail(db,saved,exp,stage,p,now,reason):
 if not stage['cleared']or p.get('claimed')or not p.get('rewards'):return
 from els_server.storage.guild_reward_mail import expedition
 expedition(db,saved,exp['week'],stage['number'],p,now,reason)
 p['claimed']=True

def advance(db,saved,now,*,notices=None):
 state=saved['system'];exp=state['expedition'];period=rules.week(now)
 if exp is None:state['expedition']=_new(now);return True
 before=json.dumps(exp,sort_keys=True)
 if exp['week']>period:raise ValueError('Guild expedition week clock moved backwards')
 boundary=rules.next_week(exp['updated'])if exp['week']<period else now
 _advance(db,saved,exp,min(now,boundary),notices)
 if exp['week']<period:
  if period-exp['week']==1:
   for stage in exp['stages'].values():
    for p in stage['participants'].values():_mail(db,saved,exp,stage,p,now,'weekly reset')
  db.execute('CREATE TABLE IF NOT EXISTS native_guild_expedition_history_v2(guild_id INTEGER NOT NULL,week INTEGER NOT NULL,document TEXT NOT NULL,PRIMARY KEY(guild_id,week))')
  db.execute('INSERT INTO native_guild_expedition_history_v2 VALUES(?,?,?)',(saved['id'],exp['week'],json.dumps(exp,sort_keys=True,separators=(',',':'))))
  state['expedition']=_new(now)
  return True
 changed=before!=json.dumps(exp,sort_keys=True)
 if changed:exp['revision']+=1
 return changed

def _charges(exp,owner,now,*,create=False):
 key=str(owner);r=exp['charges'].get(key);rule=rules.expedition_rules()
 if r is None:
  start=exp.get('charge_starts',{}).get(key)
  initial=initial_smashes() if start is not None else None
  if initial is None:
   if create:raise ValueError('Guild first-smash policy or original participation required')
   return dict(count=0,next=0,last=0)
  r=dict(count=initial,next=start+rule['HitChargingSec'],last=0)
  exp['charges'][key]=r
 if now>=r['next']:
  added=(now-r['next'])//rule['HitChargingSec']+1
  r['count']=min(rule['HitMaxCount'],r['count']+added);r['next']+=added*rule['HitChargingSec']
 return r

def _player(p,now):
 # 2C3C410: complete0x61 DTO. +10join, +22CP, +26damage, +58rank, +5Cclaimed.
 return(struct.pack('>QQbbQQiQQH',p['account'],p['uid'],1,0,p['joined'],p['until'],p['combat'],p['damage']//500,0,p['class_id'])
  +text(p['name'])+struct.pack('>i?i',p.get('rank',0),p.get('claimed',False),0))

def snapshot(saved,now,kind=0xabb,*,code=0):
 if saved is None:return reply(kind,struct.pack('>iIIIiQ',code,0,0,0,0,0)+text('')+struct.pack('>IiQ',0,0,0))
 exp=saved['system']['expedition']or _new(now)
 stages=[];own=[];ranks=[];owner=saved['owner'];current=exp['stage']
 for n in range(1,13):
  st=exp['stages'].get(str(n));maximum=int(rules.expedition_rules()['StageInfo'][str(n)]['HP'])
  hp=maximum if st is None else (st['hp']+499)//500
  players={}if st is None else st['participants'];done=bool(st and st['cleared'])
  active=[]if st is None or done else _active(st,now)
  stages.append(struct.pack('>bibQQQQiQQ??',n,saved['id'],n,0,maximum,hp,0,len(active),0,sum(p['combat']for p in active)//500,done,done))
  p=players.get(str(owner))
  if p is not None:own.append(struct.pack('>b',n)+_player(p,now))
  ordered=sorted(players.values(),key=lambda p:(-p['damage'],p['joined'],p['uid']))
  ranks.append(struct.pack('>bI',n,len(ordered))+b''.join(_player(dict(p,rank=p.get('rank',i)),now)for i,p in enumerate(ordered,1)))
 charge=_charges(exp,owner,now)
 return reply(kind,struct.pack('>iI',code,len(stages))+b''.join(stages)+struct.pack('>I',len(own))+b''.join(own)
  +struct.pack('>I',len(ranks))+b''.join(ranks)+struct.pack('>iQ',charge['count'],charge['next'])+text('')
  +struct.pack('>IiQ',0,0,(saved['id']<<32)|exp['week']))

def summary(saved,now):
 from els_server.protocol.guild_system_messages import expedition_summary
 exp=saved['system']['expedition']
 if exp is None or exp['week']!=rules.week(now):return expedition_summary(1,False,False,False)
 n=exp['stage'];st=exp['stages'].get(str(n));p=None if st is None else st['participants'].get(str(saved['owner']))
 return expedition_summary(n,bool(p and not p.get('left')and p['until']>now and not st['cleared']),
  bool(exp['stages'].get('12',{}).get('cleared')),any(bool(s['cleared']and s['participants'].get(str(saved['owner']),{}).get('rewards')and not s['participants'].get(str(saved['owner']),{}).get('claimed'))for s in exp['stages'].values()))

def command(db,s,event,saved,operation,now,*,notices=None):
 if s.phase!='guild_agit_ready':raise ValueError('Guild expedition requires actual GuildAgit')
 from els_server.protocol.social_messages import Reader
 r=Reader(event.payload);stage_number=r.scalar('b');kind=event.kind
 if kind==0xabc:
  if r.scalar('I')!=0x47505731 or r.scalar('Q')!=saved['owner']:raise ValueError('Guild signup requires current owned native CP support')
  cp=r.scalar('f')
  if not math.isfinite(cp)or not 0<=cp<2**31:raise ValueError('Guild signup native CP')
  cp=int(cp)
 r.end()
 if kind==0xaba and stage_number!=0 or kind!=0xaba and stage_number not in range(1,13):raise ValueError('Guild expedition original stage')
 advance(db,saved,now,notices=notices);exp=saved['system']['expedition'];notes=[];owner=saved['owner']
 if kind==0xaba:
  system.write(db,saved['id'],saved['system'])
  return [snapshot(saved,now)],notes
 st=_stage(exp,stage_number,now)
 if kind==0xabc:
  row=db.execute('SELECT m.account_id,m.joined_at,c.level,c.unit_class,c.name FROM native_guild_members m JOIN characters c ON c.uid=m.owner WHERE m.owner=?AND m.guild_id=?',(owner,saved['id'])).fetchone()
  if row is None or saved['grade']>5 or row[2]!=99 or now-row[1]<86400 or stage_number!=exp['stage']or st['cleared']:raise ValueError('Guild expedition signup qualification')
  old=st['participants'].get(str(owner))
  if old and(old.get('left')or old['until']>now):raise ValueError('Guild expedition participation already active or departed')
  if any(p['account']==row[0]and p['uid']!=owner for p in st['participants'].values()):raise ValueError('One character per account in this guild stage')
  if any(p['uid']==owner and not p.get('left')and p['until']>now and not stage['cleared']for stage in exp['stages'].values()for p in stage['participants'].values()):raise ValueError('Guild expedition actor already participating')
  duration=rules.expedition_rules()['LimitExpeditionSec']
  p=dict(uid=owner,account=row[0],joined=now,until=now+duration,combat=cp,class_id=row[3],name=row[4],damage=0,claimed=False,rank=0,rewards={},source=operation)
  if old:p['damage']=old['damage']
  st['participants'][str(owner)]=p;st['started']=st['started']or now;st['updated']=now
  exp.setdefault('charge_starts',{}).setdefault(str(owner),now)
  from els_server.storage.guild_quests import record
  earned=system.honor(saved['system'],owner,dict(rules.calls('SetGuildHonorPoint'))[4],now)
  notes=[e for e in record(db,owner,operation,[(99,1,0)]+([(100,earned,0)]if earned else []),now)]
  # Progress belongs only to this actor, not the guild-wide mailbox broadcast.
  answer=[snapshot(saved,now,0xabd)]+notes;notes=[]
 elif kind==0xabe:
  p=st['participants'].get(str(owner));charge=_charges(exp,owner,now,create=True)
  if(stage_number!=exp['stage']or st['cleared']or p is None or p.get('left')or p['until']<=now or not charge['count']or now-charge['last']<2):raise ValueError('Guild expedition Smash qualification/charges/cooldown')
  rule=rules.expedition_rules();draw=secrets.randbelow(100);selected=None
  for value in rule['HitFactor'].values():
   draw-=value['Probability']
   if draw<0:selected=value;break
  if selected is None:raise ValueError('Guild Smash probability source')
  from decimal import Decimal
  random=secrets.randbits(53);members=min(rule['HitMaxPlayer'],len(_active(st,now)))
  factor=Decimal(str(selected['Min']))+(Decimal(str(selected['Max']))-Decimal(str(selected['Min'])))*random/(2**53)
  damage=int(Decimal(p['combat'])*rule['HitCombatFactor']*factor*(1+members*Decimal(str(rule['HitMaxPlayerFactor'])))*Decimal(str(rule['HitFinalFactor'])))
  used=min(st['hp'],damage*500);p['damage']+=used;st['hp']-=used
  p.setdefault('smashes',[]).append(dict(operation=operation,at=now,tier=selected['ID'],random=random,members=members,damage_units=used))
  charge['count']-=1;charge['last']=now
  if st['hp']==0:_award(db,saved,exp,st,now,notices)
  answer=[reply(0xabf,struct.pack('>iQiQi',0,used//500,charge['count'],charge['next'],len(_active(st,now)))),snapshot(saved,now,0xabb)]
 else:
  p=st['participants'].get(str(owner))
  if p is None or not st['cleared']or p.get('left')or not p.get('rewards'):raise ValueError('Guild expedition actual earned reward required')
  from els_server.storage.inventory_state import grant_items,load_items
  answer=[]
  if not p.get('claimed'):
   from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
   before=load_items(db,owner)
   grants=grant_items(db,[dict(template=int(t),metadata=VERIFIED_TEMPLATES[int(t)],group=TEMPLATE_BAG_GROUPS[int(t)],quantity=q)for t,q in p['rewards'].items()],owner)
   positions=sorted({(i['group'],i['slot'])for i in grants});after=load_items(db,owner)
   digest=hashlib.sha256(str(owner).encode()+b':'+str(kind).encode()+b':'+event.payload).hexdigest()
   from els_server.storage.inventory_actions import _commit
   _commit(db,operation,digest,owner,kind,positions,before,after)
   from els_server.storage.inventory_management import _updates
   current={(i['group'],i['slot']):i for i in after}
   answer+=_updates([(pos,current.get(pos))for pos in positions])
   p['claimed']=True
  answer.insert(0,snapshot(saved,now,0xac1))
 exp['revision']+=1;system.write(db,saved['id'],saved['system'])
 return answer,[summary(saved,now)]

def failure(kind):
 return reply(0xabf,struct.pack('>iQiQi',1,0,0,0,0))if kind==0xabe else snapshot(None,0,kind+1,code=1)

def replay(db,saved,kind,operation,digest,now,old,*,stage_number,notices=None):
 advance(db,saved,now,notices=notices);answer=[]
 if kind==0xabe:
  raw=bytes.fromhex(old['events'][0][1]);damage=struct.unpack_from('>Q',raw,4)[0]
  charge=_charges(saved['system']['expedition'],saved['owner'],now)
  st=saved['system']['expedition']['stages'].get(str(stage_number))
  members=len(_active(st,now)) if st and not st['cleared'] else 0
  answer=[reply(0xabf,struct.pack('>iQiQi',0,damage,charge['count'],charge['next'],members)),snapshot(saved,now)]
 else:answer=[snapshot(saved,now,kind+1)]
 if kind==0xac0:
  from els_server.storage.inventory_actions import _previous
  positions=_previous(db,operation,digest)
  if positions is not None:
   from els_server.storage.inventory_state import load_items
   from els_server.storage.equipment_receipt_state import current_changes
   from els_server.storage.inventory_management import _updates
   answer+=_updates(current_changes(db,operation,saved['owner'],kind,positions,load_items(db,saved['owner'])))
 system.write(db,saved['id'],saved['system'])
 return answer

def depart(db,saved,owner,now):
 advance(db,saved,now);exp=saved['system']['expedition']
 for stage in exp['stages'].values():
  p=stage['participants'].get(str(owner))
  if p is None:continue
  _mail(db,saved,exp,stage,p,now,'membership departure')
  if not stage['cleared']:p['left']=now;p['until']=min(now,p['until'])
 exp['revision']+=1

def periodic(s):
 if s.phase not in('town_ready','guild_agit_ready'):return []
 import time,sqlite3
 from contextlib import closing
 now=int(time.time());binding=(s.account,s.account.uid,s.shop_session_id)
 timing=getattr(s,'_guild_expedition_clock',None)
 if timing is not None and timing[0]==binding and now<timing[1]:return []
 from els_server.domain.guild_system_flow import capture
 from els_server.storage.guild_membership_state import snapshot as membership
 from els_server.protocol.protocol_codec import encode_event
 same,guard=capture(s)
 from els_server.storage.read_scope import snapshot_connection
 with snapshot_connection(s.account.store.path)as db:
  db.execute('BEGIN');guard(db)
  saved=membership(db,s.account.uid,s.account.account_id)
  empty=saved is None or saved['system']['expedition']is None
  if empty:guard(db)
 if empty:
  s._guild_expedition_clock=(binding,min(now+60,rules.next_week(now)))
  s._guild_expedition_projection=None
  return[]
 notices=[]
 with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
  db.execute('PRAGMA foreign_keys=ON')
  with write_transaction(db):
   guard(db)
   saved=membership(db,s.account.uid,s.account.account_id);answer=[]
   if saved is not None and saved['system']['expedition']is not None:
    changed=advance(db,saved,now,notices=notices)
    if changed:system.write(db,saved['id'],saved['system'])
    exp=saved['system']['expedition'];after=(exp['week'],sum(bool(st['cleared'])for st in exp['stages'].values()))
    sent=getattr(s,'_guild_expedition_projection',None)
    projection=(saved['id'],after,system.currency(db,saved['id']))
    if sent!=projection:
     from els_server.domain.guild_initial_profile import profile
     from els_server.protocol.guild_membership_profile import full_notification
     answer=[full_notification(profile(saved,db=db,now=now)),reply(0x7ec,struct.pack('>i',projection[2][0]))]
    for e in answer:encode_event(e)
   else:projection=None
   guard(db)
 s._guild_expedition_clock=(binding,min(now+60,rules.next_week(now)))
 s._guild_expedition_projection=projection
 from els_server.domain.gameplay_announcements import publish
 publish(s,notices)
 return answer

from els_server.storage.sqlite_timing import write_transaction
