"""Owned TLS pickup/clock/status/gate regression on the candidate overlay."""
import runtime_fixture as h
import asyncio,contextlib,json,sqlite3,struct,time,traceback,statistics,sys
from unittest.mock import patch
from dataclasses import replace
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.dungeon_drops import ground_drop_notice
from els_server.storage.companion_state import handle as companion,snapshot as companions
from els_server.storage.pet_support import handle as support
from els_server.storage.luciel_state import active_state
from els_server.protocol.local_messages import wstring
from els_server.domain import session_auxiliary as aux
probe=h.load('latency_gate_probe',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
ground=h.load('latency_existing_ground',h.ROOT/'tests/test_ground_loot.py')

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,candidate='--candidate'in sys.argv,checks=[])
 def passed(label):out['checks'].append(label);print(label,flush=True)
 try:
  manager=c.app.activity2026_manager
  await c.app.call(manager.update,dict(operation_id=str(h.uuid.uuid4()),reason='owned pickup timing regression',expected_revision=manager.state['revision'],enabled=dict(attendance=True,online=True,growth=True)))
  # Create the actual Lu/Ciel family through the existing owned character API.
  Characters(c.config.state_file,c.alice['id']).create('OwnedPickup',10,'owned-pickup-character')
  p=await c.peer(c.alice);await p.roster();uid=c.app.accounts[c.alice['id']].uid
  from els_server.storage.seal_quests import QuestState
  from els_server.game_data import client_data
  QuestState(c.config.state_file,uid,account_id=c.alice['id']).snapshot()
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
   db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
   db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
   db.execute('DELETE FROM character_quests WHERE owner=?AND quest=26680',(uid,))
   db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26680,1,'{}'))
  await probe.solo_load(p,uid);s=c.app.playing[c.alice['id']]
  assert s.dungeon_run.identity==34710 and s.dungeon_substage_synced
  passed('normal TLS admission and actual loaded room')
  # Pure live reports still perform their original mutations/validation.
  for active in (1,1,0):
   payload=bytes(54)+bytes((active,))+bytes(7)
   await p.send(0x38e,payload);await p.send(0x48d);await p.until(0x48f)
   with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
    assert active_state(db,uid)['active_unit']==active
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
   assert active_state(db,uid)['revision']==2
  await p.send(0xff20,bytes(9));await p.send(0x48d);await p.until(0x48f)
  assert s.group_wear_support==(s.account,uid,s.shop_session_id)
  await p.send(0xff21,bytes(9));await p.send(0x48d);await p.until(0x48f)
  assert s.group_wear_support is None
  passed('native38E active selector commits; unchanged selector does not increment; capability enable/revoke retained')
  # Ordinary early B8 must still fail to advance, regardless of queued reports.
  start=s.dungeon_run.part
  await p.send(0xb8,b'\1');await p.until(0xb9)
  assert s.dungeon_run.part==start and not s.part_end_notified
  # Mix current high-frequency shapes in the real socket; time the server work.
  marker=len(c.events)
  for _ in range(12):
   await p.send(0x640,bytes(1));await p.send(0x3e6,bytes(9));await p.send(0xff20,bytes(9))
  await p.send(0x48d);await p.until(0x48f)
  timing=[r for r in c.events[marker:]if r['event']=='request_timing'and r.get('kind')in(0x640,0x3e6,0xff20)]
  assert len(timing)==36
  vals=[r['total_ms']for r in timing];out['mixed_reports_ms']=dict(count=len(vals),median=statistics.median(vals),max=max(vals))
  if out['candidate']:
   assert all(all(call['clock_before_ms']==call['clock_after_ms']==0 for call in r['calls'])for r in timing)
  passed('36 actual TLS live reports drained; no extra activity clock observation on candidate')
  # Real combat generates actual source-qualified drops; no issued-drop fixture.
  await probe.clear_first(p,uid,s.dungeon_run)
  assert not s.part_end_notified and s.dungeon_run.part==0
  drops=[dict(d)for d in s.world_drops.values()if not d.get('pickup_committed')]
  assert drops and all(d['template']in ground.GROUND_TEMPLATES for d in drops)
  before=s.account.get_reward_balances()['ed'];coin=next(d for d in drops if d['ed'])
  request=ground.request(coin['template'],coin['drop_id'],player_xyz=(5000,0,0),drop_xyz=(5005,-10,8))
  replies=await c.app.call(s.handle,request,request_sequence=800001)
  assert not any(e.kind in(0xd1,0xd2)for e in replies) and s.account.get_reward_balances()['ed']==before
  passed('remote pet pickup denied without current entitlement; no money awarded')
  def own_pet():
   path=s.account.store.path
   with contextlib.closing(sqlite3.connect(path))as db,db:
    items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)for t in(550427,500720)],owner=uid)
   petitem=next(i for i in items if i['template']==550427);coupon=next(i for i in items if i['template']==500720)
   companion(path,uid,0x2e8,struct.pack('>Q',petitem['uid'])+wstring('Collector'),'own-activate',account_id=s.account.account_id)
   pet=companions(path,uid)['companions'][0]['uid']
   support(path,uid,0x219,struct.pack('>QQiiIB',coupon['uid'],pet,0,0,0,0),'own-unlock',account_id=s.account.account_id)
   companion(path,uid,0x2ec,struct.pack('>Q',pet),'own-summon',account_id=s.account.account_id)
  await c.app.call(own_pet)
  marker=len(c.events);await p.send(0xd0,request.payload)
  assert(await p.until(0xd1)).payload==bytes(4);await p.until(0xd2)
  after=s.account.get_reward_balances()['ed'];assert after==before+coin['ed']
  # Replayed receipt is ACK-only and neither SQL nor native effect duplicates.
  count=sum(x['received']==0xd2 for x in p.observed)
  await p.send(0xd0,request.payload);assert(await p.until(0xd1)).payload==bytes(4)
  await p.send(0x48d);await p.until(0x48f)
  assert s.account.get_reward_balances()['ed']==after and sum(x['received']==0xd2 for x in p.observed)==count
  passed('source-qualified remote pet D0/D1/D2, real credit, repeated D0 no duplicate money/effect')
  # Failure in the original response encoder must roll back actual economic TX.
  other=next(d for d in drops if d['ed']and d['drop_id']!=coin['drop_id'])
  other_req=ground.request(other['template'],other['drop_id'],player_xyz=other['xyz'],drop_xyz=other['xyz'])
  def fault():
   with patch('els_server.domain.dungeon_drops.ground_pickup_notice',side_effect=ValueError('owned encoder fault')):
    try:s.handle(other_req,800002)
    except ValueError:pass
    else:raise AssertionError('encoder fault swallowed')
  await c.app.call(fault)
  assert s.account.get_reward_balances()['ed']==after and not s.world_drops[other['drop_id']]['pickup_committed']
  await p.send(0xd0,other_req.payload);await p.until(0xd1);await p.until(0xd2)
  assert s.account.get_reward_balances()['ed']==after+other['ed']
  passed('actual coin encoder failure rolls back; same issued drop remains claimable once')
  # Inventory-bearing replies must retain the complete post-commit observers.
  event=await c.app.call(h.drop,s,910900)
  d=s.world_drops[910900];d.update(template=77000,quantity=1,ed=0,payload_hex=ground_drop_notice(910900,(0.,0.,0.),uid=uid,template=77000).payload.hex())
  item_req=ground.request(77000,910900,player_xyz=(0,0,0),drop_xyz=(0,0,0))
  await p.send(0xd0,item_req.payload);await p.until(0xd1);await p.until(0xd3)
  assert any(i['template']==77000 for i in s.account.get_inventory_snapshot()['items'])
  passed('inventory D3 pickup remains on full synchronization path and persists')
  # Opened glass door must cross even with unclaimed source-qualified drops.
  pending=sum(not d.get('pickup_committed')for d in s.world_drops.values());assert pending>0
  await probe.finish_solo(p)
  assert s.dungeon_run.part==1 and s.dungeon_substage_synced
  passed('glass B8/B9/BA/BB/BC/BD, repeated requests and load succeed with unclaimed drops')
  # Upkeep still executes independently, including activity notifications.
  await c.app.call(lambda:setattr(s,'next_periodic',0))
  await asyncio.sleep(1.2)
  messages=await c.app.call(s.periodic_notifications)
  for e in messages:encode_event(e)
  balance=s.account.get_reward_balances()['ed']
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
   assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]==balance
   attendance=db.execute('SELECT coalesce(sum(online_seconds),0) FROM activity518_progress WHERE account=?',(str(s.account.account_id),)).fetchone()[0]
   title=db.execute('SELECT coalesce(sum(ends-starts),0) FROM online2026_spans WHERE character=?',(uid,)).fetchone()[0]
   assert attendance>0 and title>0,(attendance,title)
   out['persisted_online_seconds']=dict(attendance=attendance,title=title)
  passed('independent periodic maintenance still runs; final currency cold read matches')
  out['ok']=True
 except BaseException as error:out.update(error=repr(error),traceback=traceback.format_exc())
 finally:
  await c.asyncTearDown();out.update(own_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
  out['server_errors']=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')]
  if out['server_errors']:out['ok']=False
  output=h.H/('runtime-candidate.json'if out['candidate']else'runtime-before.json')
  if output.exists():output=output.with_stem(output.stem+'-'+time.strftime('%H%M%S'))
  output.write_text(json.dumps(out,indent=2),encoding='utf8')
 print(json.dumps(out));return out['ok']
sys.exit(not asyncio.run(main()))
