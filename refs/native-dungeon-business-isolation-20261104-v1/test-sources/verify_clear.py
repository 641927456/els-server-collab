"""Normal owned El Tree full clear, original economic writer and replay."""
import runtime_fixture as h
import asyncio,contextlib,sqlite3,struct,json,traceback,sys
from els_server.storage.seal_quests import QuestState
from els_server.game_data import client_data
from els_server.domain.dungeon_population import population
probe=h.load('clear_dungeon_probe',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,checks=[])
 try:
  p=await c.peer(c.alice);await p.roster();uid=c.app.accounts[c.alice['id']].uid;path=c.config.state_file
  QuestState(path,uid,account_id=c.alice['id']).snapshot()
  with contextlib.closing(sqlite3.connect(path))as db,db:
   db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
   db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
   db.execute('DELETE FROM character_quests WHERE owner=?AND quest=26680',(uid,))
   db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26680,1,'{}'))
  await p.enter_town(uid,town=20000)
  await p.send(0x7d4,struct.pack('>ii',1,30000));assert(await p.until(0x7d5)).payload[:4]==bytes(4)
  await p.send(0x382,probe.ENTRY);assert(await p.until(0x383)).payload[:4]==bytes(4);await p.until(0x14a)
  s=c.app.playing[c.alice['id']];assert s.dungeon_run is None
  await p.send(0xb3,bytes(9));await p.send(0x48d);await p.until(0x48f)
  assert s.phase=='dungeon_loading'and not s.dungeon_substage_synced
  out['checks'].append('premature legacy B3 is rejected without entering loaded state')
  await p.send(0x91,struct.pack('>ii',100,0));await p.until(0xb2);await p.send(0xb3,bytes(9));await p.until(0xbd)
  out['checks'].append('normal30000 admission and original loaded barrier')
  for stage in range(3):
   assert s.gate_stage==stage and s.dungeon_substage_synced
   data=population(stage,hp_context=getattr(s,'_c1_hp_context',None))
   ordered=[n for n in data['npcs']if n['active']and n['key']!=data['clear_key']]
   ordered+=[next(n for n in data['npcs']if n['key']==data['clear_key'])]
   for n in ordered:
    if n['key']in s.defeated_npcs:continue
    await p.send(0xad,probe.accepted_combat(n,uid));assert(await p.until(0xae)).payload==bytes(4)
   await p.until(0xba)
   await p.send(0xbb,struct.pack('>b',data['part']));assert(await p.until(0xbc)).payload==bytes(4)
   if stage<2:
    await p.until(0xb2);await p.send(0xb3,bytes(9));await p.until(0xbd)
   else:await p.until(0xc1)
  assert s.clear_notified and s.reward_receipt
  before=s.account.get_reward_balances();receipt=s.reward_receipt['run_id']
  with contextlib.closing(sqlite3.connect(path))as db:
   stored=db.execute('SELECT proof_sha256,response,balance_json FROM reward_receipts WHERE run_id=?',(receipt,)).fetchone();assert stored
  await p.send(0xbb,struct.pack('>b',data['part']));await p.until(0xbc)
  await p.send(0x48d);await p.until(0x48f);assert s.account.get_reward_balances()==before
  with contextlib.closing(sqlite3.connect(path))as db:
   assert db.execute('SELECT proof_sha256,response,balance_json FROM reward_receipts WHERE run_id=?',(receipt,)).fetchone()==stored
  out['checks'].append('three original stages, combat receipts and C1 settlement commit; repeated BB changes neither balance nor original receipt')
  await p.send(0x67,struct.pack('>i',0x72)+bytes(96));await p.until(0x68)
  assert s.dungeon_return_pending and s.phase=='map_loading'
  out['checks'].append('original dungeon end request enters return lifecycle')
  out['ok']=True
 except BaseException as e:out.update(error=repr(e),traceback=traceback.format_exc(),state=dict(phase=s.phase,stage=s.gate_stage,defeated=len(s.defeated_npcs))if's'in locals()else None)
 finally:
  await c.asyncTearDown();out.update(connections=len(c.server.connections),own_runtime_removed=not c.root.exists(),server_errors=[r for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  if out['server_errors']:out['ok']=False
  p=h.H/'clear-tests.json'
  if p.exists():p=p.with_stem(p.stem+'-'+__import__('time').strftime('%H%M%S'))
  p.write_text(json.dumps(out,indent=2),encoding='utf8')
 print(json.dumps(out));return out['ok']
sys.exit(not asyncio.run(main()))
