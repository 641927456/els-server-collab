"""Actual Application/TLS entry errors against owned temporary saves."""
import source
from source import HERE,BASE
import asyncio,contextlib,hashlib,importlib.util,json,os,sqlite3,struct,time
from unittest.mock import patch
from types import SimpleNamespace

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
fixture=load('entry_tls_fixture',HERE/'friends_fixture.py')
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.domain import normal_fatigue_flow as fatigue
from els_server.domain import normal_fatigue_rules
from els_server.domain.region_quests import region_catalog
from els_server.storage.seal_quests import QuestState
from els_server.protocol.dungeon_errors import INSUFFICIENT_DUNGEON_FATIGUE
from dataclasses import replace
async def send(self,kind,payload=b'',event_id=0x202):
 if kind==0x5bf and not payload:payload=bytes(8)
 self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
fixture.Peer.send=send
load('entry_native_fixture_reader',HERE/'native_fixture_reader.py').install(fixture)
OPAQUE=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

async def main():
 case=fixture.FriendsTests();await case.asyncSetUp();root=case.root.resolve();checks=[];passed=False
 try:
  case.config=replace(case.config,friends_coop_enabled=True);case.app.config=case.config;case.server.config=case.config
  people=[];actors=[];uids=[]
  def sql(query,args=()):
   with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:return db.execute(query,args).fetchall()
  for identity in(case.alice,case.bob):
   peer=await case.peer(identity);await peer.roster();uid=case.app.accounts[identity['id']].uid
   QuestState(case.config.state_file,uid,account_id=identity['id']).snapshot()
   sql('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
   for q in (26640,26650,26660,26670):sql('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,q,1,'{}'))
   await peer.enter_town(uid);people.append(peer);uids.append(uid);actors.append(case.app.playing[identity['id']])
  alice,bob=people;a,b=actors
  def set_fatigue(actor,value):
   assert sql('SELECT current FROM normal_fatigue_state WHERE owner=?',(actor.account.uid,))
   sql('UPDATE normal_fatigue_state SET current=?,revision=revision+1 WHERE owner=?',(value,actor.account.uid))
  def state():
   return dict(fatigue=sql('SELECT * FROM normal_fatigue_state ORDER BY owner'),operations=sql('SELECT * FROM normal_fatigue_operations ORDER BY operation'),balances=sql('SELECT * FROM reward_balances ORDER BY uid'))
  async def response(peer,kind,payload,expected_kind,code):
   before=state();await peer.send(kind,payload);reply=await peer.until(expected_kind)
   assert struct.unpack_from('>i',reply.payload)[0]==code,(hex(kind),reply.payload.hex(),code)
   assert state()==before,('entry_changed_economy',kind)
   return reply
  assert INSUFFICIENT_DUNGEON_FATIGUE==77
  messages=json.loads((BASE/'els_server/data/client/result_messages.json').read_bytes())['messages']
  assert next(x['text']for x in messages if x['code']==77)=='疲劳值不足，无法进行副本冒险。'
  checks.append('existing_native77_text_identity')
  for mid,mode in((30000,1),(30000,2),(35600,2)):
   set_fatigue(a,0)
   await response(alice,0x7d4,struct.pack('>ii',mode,mid),0x7d5,77)
   assert not a.dungeon_requested and a.phase=='town_ready' and a.dungeon_run is None
  checks.append('solo_7D4_normal_matching_and_single_raid_zero_fatigue77')
  for mid,mode,continuation in((30000,1,0x382),(35600,2,0x37f)):
   set_fatigue(a,1)
   await response(alice,0x7d4,struct.pack('>ii',mode,mid),0x7d5,0)
   set_fatigue(a,0)
   ack=await response(alice,continuation,OPAQUE,continuation+1,77)
   from els_server.protocol.local_messages import wstring
   assert ack.payload==struct.pack('>i',77)+(bytes(8)if continuation==0x37f else b'')+wstring('')*2
   assert a.phase=='town_ready' and a.dungeon_run is None
   await response(alice,continuation,b'bad',continuation+1,2)
  checks+=['solo_382_and_37F_recheck_fatigue_after_valid_preflight','malformed_continuation_remains_generic_failure']
  await response(alice,0x7d4,struct.pack('>ii',9,30000),0x7d5,1406)
  sql('DELETE FROM completed_quests WHERE owner=? AND quest=26650',(uids[0],))
  await response(alice,0x7d4,struct.pack('>ii',1,34340),0x7d5,2224)
  sql('INSERT INTO completed_quests VALUES(?,?,?,?)',(uids[0],26650,1,'{}'))
  checks.append('mode_and_region_rejections_keep_their_original_precedence')
  exempt=next(int(mid)for mid,r in normal_fatigue_rules.policy()['routes'].items()if r['cost']==0)
  assert await case.app.call(fatigue.admission_result,a,exempt)==0
  assert not await case.app.call(fatigue.admission,a,30000)
  def fail_game_read(*args,**kwargs):raise sqlite3.OperationalError('owned injected read failure')
  with patch.object(fatigue,'sqlite3',SimpleNamespace(connect=fail_game_read,Error=sqlite3.Error)):
   assert await case.app.call(fatigue.admission_result,a,30000)==2224
  old_phase=a.phase;a.phase='map_loading'
  try:assert await case.app.call(fatigue.admission_result,a,30000)==2224
  finally:a.phase=old_phase
  checks+=['zero_cost_exemption_and_boolean_consumers_preserved','database_and_actor_failure_are_never_mislabeled_as_fatigue']
  await alice.invite(bob,uids[1],'Player'+str(case.bob['id']),uids[0])
  await bob.send(0x14c,b'\1'+bytes(4));await bob.until(0x14d);await alice.until(0x14d)
  party=case.app.world.party_of[a]
  for empty in(a,b):
   set_fatigue(a,1);set_fatigue(b,1);set_fatigue(empty,0)
   await response(alice,0x7d4,struct.pack('>ii',1,30000),0x7d5,77)
   assert not case.app.world.dungeons.admissible(party,a,30000)
   await response(alice,0x382,OPAQUE,0x383,77)
   assert party['run']is None and all(s.phase=='town_ready'for s in actors)
  checks.append('group_preflight_and_direct382_identify_exhausted_leader_or_member')
  await response(bob,0x7d4,struct.pack('>ii',1,30000),0x7d5,2224)
  await response(alice,0x382,b'bad',0x383,-1)
  party['ready'].clear()
  await response(alice,0x7d4,struct.pack('>ii',1,30000),0x7d5,2224)
  party['ready'].add(b)
  checks.append('group_leader_ready_and_malformed_requests_still_reject')
  set_fatigue(a,1);set_fatigue(b,1)
  await response(alice,0x7d4,struct.pack('>ii',1,30000),0x7d5,0)
  set_fatigue(b,0)
  await response(alice,0x382,OPAQUE,0x383,77)
  assert party['run']is None
  set_fatigue(b,1)
  # A denied continuation consumes no fatigue or stale authorization; the same
  # current ready roster can naturally retry after its private fatigue fixture changes.
  await alice.send(0x382,OPAQUE);reply=await alice.until(0x383)
  assert reply.payload[:4]==bytes(4),reply.payload.hex()
  await alice.until(0x14a);await bob.until(0x14a)
  assert case.app.world.dungeons.room(a)is case.app.world.dungeons.room(b)
  assert all(s.phase=='dungeon_loading'for s in actors)
  checks+=['group382_rechecks_after_successful_preflight_without_debit','positive_one_fatigue_original_group_start_and_shared_room']
  assert not[e for e in case.events if e['event']in('worker_error','protocol_error','connection_task_error')]
  passed=True
 finally:
  await case.asyncTearDown()
  (HERE/'entry-tests.json').write_text(json.dumps(dict(passed=passed,checks=checks,actual_Application_TLS=True,temporary_owned_database=True,natural_GUI=False,online_installed=False,cleanup=dict(owned_runtime_removed=not root.exists(),active_connections=len(case.server.connections))),indent=2),encoding='utf8')
 print(json.dumps(dict(passed=passed,checks=checks)))
if __name__=='__main__':asyncio.run(main())
