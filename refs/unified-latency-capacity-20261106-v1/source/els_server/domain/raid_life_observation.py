"""Read original own-death facts for reward eligibility; no combat/revival replacement."""
import hashlib,struct

def observe(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in(0xa7,0xaa):return
 from els_server.domain.raid_economy_flow import managed,application
 if not managed(s):return
 from els_server.domain.dungeon_hp_c1 import _lease
 from els_server.domain.formal_raid_economy import check_run
 from els_server.protocol.known_resurrection import death_request
 from els_server.domain.known_resurrection_flow import _source
 try:
  r=s.dungeon_run;app=application(s);d=check_run(r)
  if (app is None or not _lease(s)or s.phase!='dungeon_active' or not s.dungeon_substage_synced
      or s.gate_stage_loading or s.clear_notified or s.dungeon_failed
      or s.dungeon_id!=r.identity or s.gate_stage!=r.stage
      or type(sequence)is not int or not 1<=sequence<2**32
      or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.performers not in((),(0,))or event.payload_mode!=0):return
  room=app.world.dungeons.room(s)
  if room is None:
   if r.run_id!=s.reward_run_id or getattr(s,'dungeon_participants',frozenset((s.account.uid,)))!=frozenset((s.account.uid,)):return
  else:
   dispatcher=app.world.dungeons
   if (room.identity!=r.identity or room.seed!=r.run_id or room.phase not in('active','part_end')
       or not dispatcher._current_transport_member(app,s,room)or not dispatcher._current_transport_roster(app,room)):return
  old=getattr(s,'_raid_life_witness',None)
  if old is None or old['epoch']!=r.run_id:old=dict(epoch=r.run_id,owner=s.account.uid,phase='alive',number=0,proof=None)
  if event.kind==0xa7:
   req=death_request(event.payload);_source(s,req)
   if old['phase']=='alive':old=dict(old,phase='dying',number=old['number']+1,proof=hashlib.sha256(event.payload).hexdigest())
  elif event.payload==b''and old['phase']=='dying':old=dict(old,phase='dead')
  else:return
  s._raid_life_witness=old
 except ValueError:return

def successful_native_revival(s,replies):
 """Only the existing authorized native revival consumer can restore alive.

 No client request, retry, stage change or time delay can erase a witnessed
 death. Modes without a qualified existing revival source remain conservative.
 """
 old=getattr(s,'_raid_life_witness',None);r=getattr(s,'dungeon_run',None)
 if old is None or r is None or old['epoch']!=r.run_id or old['phase']=='alive':return
 life=getattr(s,'known_resurrection_life',None)
 if not isinstance(life,dict)or life.get('epoch')!=r.run_id or life.get('phase')!='alive':return
 good_ack=any(e.kind==0x161 and len(e.payload)==25 and struct.unpack_from('>i',e.payload)[0]==0 and struct.unpack_from('>Q',e.payload,17)[0]==s.account.uid for e in replies)
 good_continue=any(e.kind==0x162 and len(e.payload)==24 and struct.unpack_from('>QQ',e.payload)==(s.account.uid,s.account.uid)for e in replies)
 if good_ack and good_continue:s._raid_life_witness=dict(old,phase='alive')
