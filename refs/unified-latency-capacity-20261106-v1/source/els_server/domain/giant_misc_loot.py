"""Shared accepted-death writer for the original two giant-map lifecycles."""
import copy,math,sqlite3
from pathlib import Path
from contextlib import closing
from els_server.domain.ordinary_misc_loot import source,append_to_shadow
from els_server.domain.regional_drop_materials import catalog

FIELDS=('defeated_npcs','part_end_notified','world_drops','world_drop_sequence','world_drop_issued')
def adopt(s,shadow):
 for name in('defeated','next','ready_at'):setattr(s.dungeon_run,name,getattr(shadow.dungeon_run,name))
 for name in FIELDS:setattr(s,name,getattr(shadow,name))
 s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started

def prepare(db,s,event,npc,death,expired,finish):
 from els_server.domain.dungeon_lifecycle import empty_reward_death_notice
 value=source(s,npc)
 if value is None:return None
 shadow=copy.copy(s);shadow.dungeon_run=copy.copy(s.dungeon_run);shadow.dungeon_run.defeated=dict(s.dungeon_run.defeated)
 shadow.dungeon_clock=copy.copy(s.dungeon_clock);shadow.world_drops=dict(s.world_drops)
 reply=finish(shadow,event,npc,death,expired,empty_reward_death_notice(npc['key'],death['killer']))
 reply+=append_to_shadow(db,value,shadow,event.payload,death['xyz'][3:]);return shadow,reply,value

def accepted_death(s,event,npc,death,expired,finish):
 if str(s.dungeon_run.identity)not in catalog()['giant_maps']or expired:return None
 if source(s,npc)is None:return None
 from els_server.protocol.protocol_codec import encode_event
 with closing(sqlite3.connect(s.account.store.path))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');shadow,reply,value=prepare(db,s,event,npc,death,expired,finish)
  for e in reply:encode_event(e)
  value.validate(db)
 adopt(s,shadow);return reply

def group_death(dispatcher,room,s,event):
 if str(room.identity)not in catalog()['giant_maps']:return None
 from els_server.domain.friends_spawns import _checked_static_generation
 from els_server.domain.dungeon_lifecycle import death_report,death_ack
 from els_server.domain.dungeon_flow import finish_death
 from els_server.domain.party_commands import _prepared_boxes
 if s is not room.leader or event.performers!=(0,)or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0:return[]
 try:
  d=death_report(event.payload);bound=_checked_static_generation(dispatcher,room)
 except(ValueError,KeyError):return[]
 npc=next((n for n in s.dungeon_run.current['npcs']if n['key']==d['index']),None)
 if npc is None or npc.get('dynamic')or not npc['active']or npc['no_drop']or npc.get('ally')or npc.get('team',1)==0:return None
 owners=frozenset(m.account.uid for m in room.members)
 import struct
 hp=struct.unpack('>f',struct.pack('>I',d['hp_bits']))[0]
 if(d['flag']not in(0,1)or not math.isfinite(hp)or hp<=0 or any(d[k]not in owners for k in('source','killer','last_uid'))or any(uid not in owners for k in('contribution','readiness','counters')for uid in d[k])or any(npc['key']in m.summon_keys for m in room.members)):return[]
 old=s.defeated_npcs.get(npc['key'])
 if old is not None:return[death_ack()]if old==event.payload else[]
 if room.phase!='active':return[]
 paths={Path(m.account.store.path).resolve()for m in room.members}
 if len(paths)!=1:return[]
 prepared=[]
 with closing(sqlite3.connect(next(iter(paths))))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  for member in room.members:
   actor=next((n for n in member.dungeon_run.current['npcs']if n['key']==npc['key']),None)
   if actor!=npc:raise ValueError('Giant misc original peer actor')
   row=prepare(db,member,event,actor,d,False,finish_death)
   if row is None:raise ValueError('Giant misc original member source')
   shadow,reply,value=row
   from els_server.domain.quest_flow import store as quest_store
   from els_server.storage.seal_quests import load_character
   key=member.dungeon_run.run_id+':'+str(member.dungeon_run.stage)+':'+str(member.dungeon_run.part)+':kill:'+str(npc['key'])
   def guard(writer):
    if _checked_static_generation(dispatcher,room)!=bound:raise ValueError('Giant misc quest generation changed')
    return value.validate(writer)
   character=load_character(db,member.account.uid,member.account.account_id)
   reply+=quest_store(member).record(key,dict(kind='kill',dungeon=room.identity,npc=npc['template'],level=character['level']),event.payload,validate=guard,transaction=db)
   seen=set(getattr(member,'_quest_seen_events',None)or())|{key}
   if member is not s:reply=[e for e in reply if e.kind!=0xae]
   prepared.append((member,shadow,reply,value,seen))
  response=next(r for member,_,r,_,_ in prepared if member is s);boxes=_prepared_boxes([(member,r)for member,_,r,_,_ in prepared if member is not s],response)
  if _checked_static_generation(dispatcher,room)!=bound:raise ValueError('Giant misc shared generation changed')
  for _,_,_,value,_ in prepared:value.validate(db)
 for member,shadow,_,_,seen in prepared:adopt(member,shadow);member._quest_seen_events=seen
 for member,box in boxes.items():member.mailbox=box
 dispatcher.part_wait(room);return response
