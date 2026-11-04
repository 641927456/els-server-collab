"""Native town reward box previews/use, accessory claim and Barkat upgrade."""
import sqlite3,struct,time
from contextlib import closing
from els_server.domain.raid_reward_items import boxes,entry_outputs
from els_server.storage import raid_reward_actions as actions,raid_economy_state as state
from els_server.protocol.raid_economy_protocol import point_snapshot,weapon_point,claim_ack,level_ack

def town(s,sequence=None):
 from els_server.domain.dungeon_hp_c1 import _lease as current_lease
 if (s.role!='game' or s.client_build!='dx11_260923' or s.phase!='town_ready' or not s.item_test
     or s.account.store is None or s.account.characters is None or not current_lease(s)
     or s.account.store.uid!=s.account.uid or (sequence is not None and(type(sequence)is not int or not 1<=sequence<2**32))):raise ValueError('Raid reward current town actor')
 from els_server.domain.raid_economy_flow import application
 app=application(s)
 if app is not None and app.config.mode=='friends'and (not app.registry.enabled(s.account.account_id)or s.coop_error or s.social_overflow):raise ValueError('Raid reward current account disabled')
 return (s.account,s.account.store,s.account.characters,s.account.account_id,s.account.uid,s.shop_session_id,s.phase)

def snapshot(db,owner):
 from els_server.domain import formal_raid_economy as rules
 values=[(n,state.progress(db,owner,'accessory:'+str(n))[0],t)for n,t in((1,136175),(2,136179),(3,30876))]
 return values,[(rules.adjust(f)['Index'],state.progress(db,owner,f)[0])for f in('rosso','berthe','abyss','barkat')]

def weekly_events(db,owner,now):
 from els_server.protocol.raid_economy_protocol import weekly_snapshot
 week=state.week_at(now);out=[]
 for family,category in(('rosso',1),('berthe',2),('abyss',3),('conductor',6),('barkat',7),('marcus',8)):
  normal=state.weekly_steps(db,owner,family,week)
  story=state.weekly_steps(db,owner,family,week,True)if family in('rosso','berthe','abyss')else 0
  out.append(weekly_snapshot(category,normal,story))
 return out

def synchronize(s,events):
 try:bound=town(s)
 except ValueError:return events
 now=int(time.time());marker=(s.account.uid,s.shop_session_id,state.week_at(now))
 if getattr(s,'_raid_progress_initialized',None)==marker:return events
 with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
  db.execute('BEGIN')
  values,weapons=snapshot(db,s.account.uid);extra=weekly_events(db,s.account.uid,now)
  extra+=[point_snapshot(values,db=db,owner=s.account.uid)]+[weapon_point(i,p)for i,p in weapons if p]
 if town(s)!=bound:raise ValueError('Raid cold progress actor changed')
 s._raid_progress_initialized=marker
 return events+extra

def handle(s,event,sequence):
 from els_server.domain.raid_life_observation import observe as observe_raid_life
 observe_raid_life(s,event,sequence)
 if event.event_id!=0x202 or event.kind not in(0x559,0x196,0xc04,0xc06,0xc0b):return None
 from els_server.protocol.ice_messages import preview_request,preview_ack,use_request
 from els_server.protocol.cube_messages import result as box_error
 kind=event.kind;template=None;operation=None
 if kind==0x559:
  try:req=preview_request(event.payload)
  except ValueError:return None
  if str(req.template)not in boxes():return None
  template=req.template
 elif kind==0x196:
  try:req=use_request(event.payload)
  except ValueError:return None
  if getattr(s.account,'store',None)is None:return None
  item=next((i for i in s.account.get_inventory_snapshot()['items']if i['uid']==req.uid),None)
  if item is not None and str(item['template'])in boxes():template=item['template']
  elif type(sequence)is int:
   operation=s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence)
   template=actions.historical_box(s.account.store.path,s.account.uid,event.payload,operation)
  if template is None:return None
 try:
  bound=town(s,sequence)
  if (event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.performers not in((),(0,))or event.payload_mode!=0):raise ValueError('Raid reward native envelope')
  def guard():
   if town(s,sequence)!=bound:raise ValueError('Raid reward actor/epoch changed')
   return True
  operation=operation or s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence)
  if kind==0xc04:
   if event.payload!=struct.pack('>i',1):raise ValueError('Raid point query original group')
   with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
    db.execute('BEGIN');values,weapons=snapshot(db,s.account.uid)
    events=[point_snapshot(values,db=db,owner=s.account.uid)]+[weapon_point(i,p)for i,p in weapons if p]
   guard();return events
  if kind==0xc06:return actions.claim(s.account.store.path,s.account.uid,event.payload,operation,s.account.account_id,guard)
  if kind==0xc0b:return actions.level_up(s.account.store.path,s.account.uid,event.payload,operation,s.account.account_id,guard)
  if kind==0x559:
   if req.keys not in((),(0,))or req.flag1 not in(0,1)or req.flag2 not in(0,1):raise ValueError('Raid native preview mode')
   owned=next((i for i in s.account.get_inventory_snapshot()['items']if i['template']==template and i['group']==4),None)
   if owned is None:raise ValueError('Raid preview requires a real owned box')
   from els_server.domain.item_expiration import require_current
   from els_server.domain.item_locks import require_unlocked
   require_current(owned);require_unlocked(owned);row,outputs=entry_outputs(template,s.account.character())
   guard();return [preview_ack(0,template,selection_count=row['selection_count'],entries=[(r['template'],0,r['quantity'])for r in row['entries']])]
  return actions.open_box(s.account.store.path,s.account.uid,template,event.payload,operation,s.account.account_id,guard)
 except (ValueError,sqlite3.Error):
  if kind==0xc06:return [claim_ack(code=-1)]
  if kind==0xc0b:return [level_ack(code=-1)]
  if kind==0xc04:return []
  return [preview_ack(-1,template)]if kind==0x559 else box_error(0,code=-1)
