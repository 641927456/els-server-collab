"""Additional affected lifecycle: participant authority and late-part retirements."""
import asyncio,copy,json,sqlite3,struct,traceback
from contextlib import closing
from test_mines import r,H,economy
from els_server.domain import friends_spawns
from els_server.game_data import client_data
from els_server.storage.seal_quests import ensure

def death(npc,owners):
 return(struct.pack('>iBQQ6fBf',npc['key'],255,2**64-1,2**64-1,*([0.]*6),1,npc['hp'])
  +bytes(4)+struct.pack('>I',len(owners))+b''.join(struct.pack('>QB',uid,0)for uid in sorted(owners))+bytes(20))

async def main():
 f=r.f.FriendsTests();await f.asyncSetUp()
 try:
  uids=[]
  for account in(f.alice,f.bob):
   uid=r.f.Characters(f.config.state_file,account['id']).create('Player'+str(account['id']),1,'mine-shared:'+str(account['id']))['uid'];uids.append(uid)
   with closing(sqlite3.connect(f.config.state_file))as db,db:
    db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid));ensure(db);db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26650,1,'{}'))
  # The old generic helper invites for map30000. Invite for the actual map;
  # 7D4 is admission, and cannot silently change a waiting party's map.
  from dataclasses import replace
  from els_server.protocol.local_messages import wstring
  f.config=replace(f.config,friends_coop_enabled=True);f.app.config=f.config;f.server.config=f.config
  alice,bob=await asyncio.gather(f.peer(f.alice),f.peer(f.bob));await asyncio.gather(alice.roster(),bob.roster());a,b=uids
  await alice.enter_town(a);await bob.enter_town(b)
  invitation=struct.pack('>Q',b)+wstring('Player'+str(f.bob['id']))+struct.pack('>iBi',0,1,30252)+bytes(6)+wstring('')+bytes(15)
  await alice.send(0x136,invitation);await alice.until(0x137);await bob.until(0x138)
  await bob.send(0x139,struct.pack('>QQBiBQ',a,b,1,0,0,0));await bob.until(0x13a);await asyncio.gather(alice.until(0x13b),bob.until(0x13b))
  await f.coop_start(alice,bob,30252);await f.coop_load(alice,bob)
  sessions=list(f.app.playing.values());leader=f.app.playing[f.alice['id']];room=f.app.world.dungeons.room(leader)
  def scene(part):
   for s in sessions:
    run=s.dungeon_run;run._load_stage(1);run.part=part;run.next=None;run.ready_at=None;run.loaded()
    s.gate_stage=1;s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.part_end_notified=False;s.defeated_npcs=run.defeated
   room.phase='active';friends_spawns.capture_static_origin(room)
  await f.app.call(scene,0);before={uid:economy(f.config.state_file,uid)for uid in uids}
  npc=next(n for n in leader.dungeon_run.current['npcs']if n['template']==241);body=death(npc,uids);key=npc['key']
  # Guest authority and incomplete participant readiness must not retire it.
  await bob.send(0xad,body);await alice.send(0xad,death(npc,[a]))
  await alice.send(0x48d);await alice.until(0x48f)
  assert all(key not in s.dungeon_run.defeated for s in sessions)
  await alice.send(0xad,body);assert(await alice.until(0xae)).payload==bytes(4);await alice.until(0xaf);await bob.until(0xaf)
  assert all(s.dungeon_run.defeated[key]==body for s in sessions)
  # Move the explicit fixture to the next part without rebuilding the old part.
  def next_part():
   for s in sessions:s.dungeon_run.part=1;s.dungeon_run.loaded()
   friends_spawns.capture_static_origin(room)
  await f.app.call(next_part)
  await alice.send(0xad,body);assert(await alice.until(0xae)).payload==bytes(4)
  old=next(n for n in leader.dungeon_run.parts[0]['npcs']if n['template']==241 and n['key']!=key);late=death(old,uids)
  await alice.send(0xad,late);assert(await alice.until(0xae)).payload==bytes(4);await alice.until(0xaf);await bob.until(0xaf)
  for s in sessions:
   assert s.dungeon_run.defeated[old['key']]==late and s.dungeon_run.part==1
   assert economy(f.config.state_file,s.account.uid)==before[s.account.uid]
  assert not any(e['event']in('worker_error','notification_error','protocol_error')for e in f.events)
  return dict(ok=True,actual_authenticated_TLS=True,shared_participants=2,guest_and_missing_readiness_refused=True,
   first_and_late_part_AE_AF=True,duplicate_AE_only=True,economy_unchanged=True,natural_route=False,natural_game=False,production_modified=False)
 finally:await f.asyncTearDown()

if __name__=='__main__':
 result={'ok':False}
 try:result=asyncio.run(main())
 except BaseException:result={'ok':False,'error':traceback.format_exc()};raise
 finally:(H/'mine-shared-TLS.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
