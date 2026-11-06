"""First genuine pet coin claims on the deployed code, in an owned TLS runtime."""
import runtime_fixture as h
import asyncio,contextlib,json,sqlite3,struct,time,cProfile,pstats,traceback,sys
from els_server.storage.characters import Characters
from els_server.storage.seal_quests import QuestState
from els_server.game_data import client_data
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.companion_state import handle as companion,snapshot as companions
from els_server.storage.pet_support import handle as support
from els_server.protocol.local_messages import wstring
probe=h.load('cold_pickup_gate',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
ground=h.load('cold_pickup_ground',h.ROOT/'tests/test_ground_loot.py')

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,claims=[],natural_battle=False,online_mutation=False)
 try:
  if '--candidate'in sys.argv:
   from els_server.domain.el_search_effects import catalog
   info=catalog.cache_info();assert info.currsize==1 and info.misses==1
   out['catalog_ready_before_admission']=info._asdict()
  manager=c.app.activity2026_manager
  await c.app.call(manager.update,dict(operation_id=str(h.uuid.uuid4()),reason='owned first-pickup profile',expected_revision=manager.state['revision'],enabled=dict(attendance=True,online=True,growth=True)))
  Characters(c.config.state_file,c.alice['id']).create('ColdOwnedLu',10,'cold-owned-role')
  peer=await c.peer(c.alice);await peer.roster();uid=c.app.accounts[c.alice['id']].uid
  QuestState(c.config.state_file,uid,account_id=c.alice['id']).snapshot()
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
   db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
   db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
   db.execute('DELETE FROM character_quests WHERE owner=?AND quest=26680',(uid,));db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26680,1,'{}'))
  await probe.solo_load(peer,uid);s=c.app.playing[c.alice['id']]
  def own_pet():
   path=s.account.store.path
   with contextlib.closing(sqlite3.connect(path))as db,db:
    items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)for t in(550427,500720)],owner=uid)
   petitem=next(i for i in items if i['template']==550427);coupon=next(i for i in items if i['template']==500720)
   companion(path,uid,0x2e8,struct.pack('>Q',petitem['uid'])+wstring('Collector'),'cold-own-activate',account_id=s.account.account_id)
   pet=companions(path,uid)['companions'][0]['uid']
   support(path,uid,0x219,struct.pack('>QQiiIB',coupon['uid'],pet,0,0,0,0),'cold-own-support',account_id=s.account.account_id)
   companion(path,uid,0x2ec,struct.pack('>Q',pet),'cold-own-summon',account_id=s.account.account_id)
  await c.app.call(own_pet)
  await probe.clear_first(peer,uid,s.dungeon_run)
  drops=[dict(d)for d in s.world_drops.values()if d['ed']and not d.get('pickup_committed')];assert len(drops)>=3
  original=c.app._worker_call
  def measured(function,args,kwargs,*rest,**options):
   selected=getattr(function,'__self__',None)is s and function.__name__=='handle'and len(args)==1 and args[0].kind==0xd0
   if not selected:return original(function,args,kwargs,*rest,**options)
   profile=cProfile.Profile();start=time.perf_counter();profile.enable()
   try:return original(function,args,kwargs,*rest,**options)
   finally:
    profile.disable();elapsed=(time.perf_counter()-start)*1000
    rows=[dict(file=f,line=l,function=n,calls=v[1],self_ms=v[2]*1000,cumulative_ms=v[3]*1000)for(f,l,n),v in pstats.Stats(profile).stats.items()]
    out['claims'].append(dict(elapsed_ms=elapsed,top=sorted(rows,key=lambda r:r['cumulative_ms'],reverse=True)[:65],self=sorted(rows,key=lambda r:r['self_ms'],reverse=True)[:30]))
  c.app._worker_call=measured
  if '--prewarm' in sys.argv:
   start=time.perf_counter()
   from els_server.domain.el_search_effects import catalog
   imported=time.perf_counter();catalog();finished=time.perf_counter()
   out['prewarm_ms']=(finished-start)*1000
   out['prewarm_import_ms']=(imported-start)*1000
   out['prewarm_catalog_ms']=(finished-imported)*1000
  balance=s.account.get_reward_balances()['ed']
  for drop in drops[:3]:
   request=ground.request(drop['template'],drop['drop_id'],player_xyz=(5000,0,0),drop_xyz=(5005,-10,8))
   await peer.send(0xd0,request.payload);assert(await peer.until(0xd1)).payload==bytes(4);await peer.until(0xd2)
   balance+=drop['ed'];assert s.account.get_reward_balances()['ed']==balance
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db:assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]==balance
  out.update(ok=True,normal_admission=True,real_source_drops=True,cold_balance_verified=True)
 except BaseException as e:out.update(error=repr(e),traceback=traceback.format_exc())
 finally:
  await c.asyncTearDown();out.update(own_runtime_removed=not c.root.exists(),connections=len(c.server.connections),server_errors=[r for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  if out['server_errors']:out['ok']=False
  dest=h.H/('profile-fixed.json'if'--candidate'in sys.argv else'profile-prewarm.json'if'--prewarm'in sys.argv else'profile-cold.json');assert not dest.exists();dest.write_text(json.dumps(out,indent=2),encoding='utf8')
 print(json.dumps(dict(ok=out['ok'],milliseconds=[p['elapsed_ms']for p in out['claims']],first_top=out['claims'][0]['top'][:20]if out['claims']else[],error=out.get('error'),own_runtime_removed=out['own_runtime_removed'])));return out['ok']
sys.exit(not asyncio.run(main()))
