"""Owned skill-spawn, consumable and elixir routes through actual TLS."""
import runtime_fixture as h
import asyncio,contextlib,sqlite3,struct,json,sys,traceback
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.quick_slots import save_request,encode,empty
from els_server.domain.quick_bindings import item_binding
from els_server.storage.world_elixirs import snapshot
from els_server.protocol.protocol_codec import Event
from els_server.domain.summon_rules import player_summon_templates
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,checks=[])
 try:
  Characters(c.config.state_file,c.alice['id']).create('OwnedEve',5,'owned-native-skill')
  p=await c.peer(c.alice);await p.roster();uid=c.app.accounts[c.alice['id']].uid;path=c.config.state_file
  with contextlib.closing(sqlite3.connect(path))as db,db:
   db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
   grant_items(db,[dict(template=130165,metadata=2,group=6,quantity=2),dict(template=710206,metadata=2,group=4,quantity=2)],uid)
   item=next(i for i in load_items(db,uid)if i['template']==710206)
  await p.enter_town(uid);s=c.app.playing[c.alice['id']];await c.app.call(lambda:h.room(s))
  save_request(path,struct.pack('>i',1)+encode({**empty(),0:item_binding(130165)}),uid)
  def counts():
   with contextlib.closing(sqlite3.connect(path))as db:return {i['template']:i['count']for i in load_items(db,uid)if i['template']in(130165,710206)}
  before=counts();await p.send(0x113,bytes(5));assert(await p.until(0x114)).payload[:4]==bytes(4);await p.until(0x115)
  assert counts()[130165]==before[130165]-1
  out['checks'].append('manual consumable original114/115 and one committed debit')
  raw=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0);sequence=p.outgoing
  await p.send(0x219,raw);assert(await p.until(0x21a)).payload[:4]==bytes(4);await p.until(0x3a3)
  assert counts()[710206]==before[710206]-1
  cold=snapshot(path,uid,s.account.account_id);rows=[r for r in cold['rows']if r['template']==710206];assert len(rows)==1
  replay=await c.app.call(s.handle,Event(0x202,kind=0x219,performers=(0,),payload=raw),request_sequence=sequence)
  assert any(e.kind==0x21a for e in replay) and counts()[710206]==before[710206]-1
  assert [r for r in snapshot(path,uid,s.account.account_id)['rows']if r['template']==710206]==rows
  out['checks'].append('right-click elixir original21A/3A3, one debit, immutable replay and cold state')
  fixture=json.loads((h.ROOT/'analysis/skills-clear-20261015/sentry-request.json').read_bytes())
  body=bytearray.fromhex(fixture['payload'])
  segment=next(row for row in fixture['segments']if row['offset']==0x6d);assert segment['length']==8
  position=segment['position'];captured=struct.unpack_from('<Q',bytes.fromhex(fixture['dto']),0x6d)[0]
  mask=int.from_bytes(body[position:position+8],'big')^captured
  body[position:position+8]=(uid^mask).to_bytes(8,'big');body=bytes(body)
  assert 384 in player_summon_templates(s.account.character())
  keys=set(s.summon_keys);sequence=p.outgoing;await p.send(0x2ce,body)
  assert(await p.until(0x2cf)).payload==bytes(4);await p.until(0x2d0)
  new=s.summon_keys-keys;assert len(new)==1;key=next(iter(new))
  replay=await c.app.call(s.handle,Event(0x202,kind=0x2ce,performers=(0,),payload=body),request_sequence=sequence)
  assert [e.kind for e in replay]==[0x2cf] and s.summon_keys-keys==new
  out['checks'].append('verified native skill384 spawn2CE/2CF/2D0; exact replay creates no second actor')
  expiry=(struct.pack('>iBQQ6fBI',key,255,2**64-1,2**64-1,*([0.]*6),1,0)
          +struct.pack('>IIQBQIQ',0,1,uid,0,0,0,0))
  before=s.account.get_reward_balances();defeated=dict(s.defeated_npcs)
  await p.send(0xad,expiry);assert(await p.until(0xae)).payload==bytes(4);await p.until(0xaf)
  await p.send(0xad,expiry);assert(await p.until(0xae)).payload==bytes(4)
  await p.send(0x48d);await p.until(0x48f)
  assert s.account.get_reward_balances()==before and s.defeated_npcs==defeated and not s.clear_notified
  out['checks'].append('owned native skill expiry retires actor, replay changes no rewards or dungeon progress')
  out['ok']=True
 except BaseException as e:out.update(error=repr(e),traceback=traceback.format_exc())
 finally:
  await c.asyncTearDown();out.update(connections=len(c.server.connections),own_runtime_removed=not c.root.exists(),server_errors=[r for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  if out['server_errors']:out['ok']=False
  path=h.H/'actions-tests.json'
  if path.exists():path=path.with_stem(path.stem+'-'+__import__('time').strftime('%H%M%S'))
  path.write_text(json.dumps(out,indent=2),encoding='utf8')
 print(json.dumps(out));return out['ok']
sys.exit(not asyncio.run(main()))
