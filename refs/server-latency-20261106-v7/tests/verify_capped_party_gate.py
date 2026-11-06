"""Native party curtain with a dead guest, preserving original barriers."""
import runtime_fixture as h
import asyncio,json,sqlite3,struct
from contextlib import closing
from dataclasses import replace
from contextlib import ExitStack
from unittest.mock import patch
from profile_town import seed
probe=h.load('c3_native_party_gate',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False)
 try:
  c.config=replace(c.config,friends_coop_enabled=True);c.app.config=c.config;c.server.config=c.config
  identities=[c.alice,c.bob];uids=[seed(c,v,'OwnGP'+str(i),False)for i,v in enumerate(identities)]
  from els_server.storage.inventory_state import grant_items,load_items
  from els_server.storage.known_resurrection import open_box
  for identity,uid in zip(identities,uids):
   with closing(sqlite3.connect(c.config.state_file))as db,db:
    grant_items(db,[dict(template=190556,metadata=2,group=4,quantity=1)],uid)
    item=next(v for v in load_items(db,uid)if v['template']==190556)
   open_box(c.config.state_file,uid,struct.pack('>QBBBIi',item['uid'],0,0,0,0,1),'owned-c3-party-credit-'+str(uid),account_id=identity['id'],guard=lambda:None)
  peers=[await c.peer(v)for v in identities]
  for p in peers:await p.roster()
  await asyncio.gather(*(p.enter_town(uid,town=20000)for p,uid in zip(peers,uids)))
  await probe.party_load(*peers,*uids,'OwnGP1')
  sessions=[c.app.playing[v['id']]for v in identities]
  await probe.clear_first(peers[0],uids[0],sessions[0].dungeon_run)
  await probe.death(peers[1],uids[1]);await peers[0].until(0xac)
  assert all(s.dungeon_run.next['kind']==0 for s in sessions)
  calls=[]
  with ExitStack()as stack:
   for s in sessions:
    original=s.activity2026_awards.online.observe
    def counted(*args,_observe=original,**kwargs):calls.append(True);return _observe(*args,**kwargs)
    stack.enter_context(patch.object(s.activity2026_awards.online,'observe',counted))
   await peers[0].send(0xb8,b'\1');assert(await peers[0].until(0xb9)).payload==bytes(4)
   for p in peers:assert(await p.until(0xba)).payload==b'\1'
   for p in peers:
    await p.send(0xbb,b'\1');assert(await p.until(0xbc)).payload==bytes(4)
   for p in peers:assert(await p.until(0xbd)).payload[:1]==b'\1'
  assert not calls
  notice=await probe.revive(peers[1],uids[1]);assert notice.payload==(await peers[0].until(0x162)).payload
  out.update(passed=True,native_two_member_party=True,dead_guest_original_barrier_and_revive_preserved=True,capped_same_stage_curtain_foreground_clock_observations=0)
 finally:
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),errors=[v['event']for v in c.events if v['event']in('worker_error','notification_error','connection_task_error')]);(h.H/'capped-party-gate-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out));assert out['passed']and not out['errors']
asyncio.run(main())
