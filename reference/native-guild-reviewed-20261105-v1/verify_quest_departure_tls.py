"""Owned TLS friends observe actual guild creation, joining and departure."""
import bootstrap as env
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor,TimeoutError as FutureTimeout
from pathlib import Path
from threading import Event as ThreadEvent
from types import SimpleNamespace
from unittest.mock import patch
import ast,asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,Event,encode_event,encode_frame,decode_event,decode_frame,read_welcome
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from tools.create_friends_certificate import create
from els_server.protocol.social_messages import wstring,chat_notice
from tls_peer import Peer

async def main():
 report=dict(passed=False,baseline='--baseline'in sys.argv,authenticated_TLS=True,actual_SQL_commit=True,production_database_access=False,natural_battle=False)
 peers=[];app=server=None
 with tempfile.TemporaryDirectory(prefix='owned-guild-publication-',dir=env.HERE)as tmp:
  private=Path(tmp);cert=create(private,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'own.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  try:
   app=Application(cfg);await app.start();server=GameServer(cfg,app,lambda *a,**kw:None);_,port=await server.start()
   identities=[];uids=[]
   for i in range(2):
    identity=app.registry.create('ownpub'+str(i));identities.append(identity)
    uid=Characters(cfg.state_file,identity['id']).create('OwnPub'+str(i),1,'ownpub-create-'+str(i))['uid'];uids.append(uid)
    with closing(sqlite3.connect(cfg.state_file))as db,db:
     db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET ed=6000000 WHERE uid=?',(uid,))
    LocalState(cfg.state_file,uid).save(20001,0,0,(1.,2.,3.))
    p=Peer();p.bridge=Bridge(BridgeConfig('127.0.0.1',port,identity['name'],identity['token'],cert));p.reader,p.writer=await p.bridge.remote();p.keys=BOOTSTRAP_KEYS;p.incoming=1;p.received=[]
    welcome=await p.until(1);p.spi,p.keys=read_welcome(welcome);p.outgoing=1;peers.append(p)
    for kind,reply in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
     await p.send(kind);await p.until(reply)
    for kind,reply,body in((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uid)),(0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),(0x225,0x226,struct.pack('>iB',20001,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
     await p.send(kind,body);await p.until(reply)
    await p.query(0x48d,b'',0x48f)
   master,guest=peers;actor=app.playing[identities[0]['id']];peer=app.playing[identities[1]['id']]
   assert(await master.query(0x248,wstring('OwnPub1')+wstring('Own guild presence'),0x249)).payload[:4]==bytes(4)
   await guest.until(0x24a)
   assert(await guest.query(0x24b,struct.pack('>Q',uids[0]),0x24c)).payload[:4]==bytes(4)
   for p in peers:await p.query(0x48d,b'',0x48f)
   marks=[len(p.received)for p in peers]
   assert(await master.query(0xea,struct.pack('>BHIiii',0,0,1,110845,1,10018),0xeb)).payload[:4]==bytes(4)
   license=next(i for i in actor.account.get_inventory_snapshot()['items']if i['template']==110845)
   assert(await master.query(0x276,struct.pack('>Q',license['uid'])+wstring('OwnPubGuild')+wstring(''),0x277)).payload[:4]==bytes(4)
   from els_server.storage.guild_membership_state import cold
   guild=cold(cfg.state_file,uids[0],identities[0]['id'])['id']
   assert(await master.query(0x285,wstring('OwnPub1')+struct.pack('>Q',uids[1]),0x286)).payload[:4]==bytes(4)
   await guest.until(0x287)
   assert(await guest.query(0x288,struct.pack('>i',guild)+wstring('OwnPub0')+bytes(4),0x289)).payload==bytes(4)
   for p in peers:await p.query(0x48d,b'',0x48f)
   from els_server.protocol import friend_messages as wire
   from els_server.storage import friend_state as storage
   def expected(receiver,target):
    with closing(sqlite3.connect(cfg.state_file))as db:
     state=storage.snapshot(db,uids[receiver],identities[receiver]['id'],{uid:app.playing[identity['id']]for uid,identity in zip(uids,identities)})
    return wire.positions([next(row for row in state['friends']if row['uid']==uids[target])]).payload
   joined=[]
   for index in range(2):
    payload=expected(index,1-index)
    assert wstring('OwnPubGuild')in payload
    joined.append(sum(e.kind==0x262 and e.payload==payload for e in peers[index].received[marks[index]:]))
   report['guild_join_presence_counts']=joined
   assert all(count==1 for count in joined)
   from els_server.storage.seal_quests import QuestState
   def state(index):return QuestState(cfg.state_file,uids[index],account_id=identities[index]['id']).snapshot()
   for p in peers:
    assert(await p.query(0xee,struct.pack('>ii',46400,10045),0xef)).payload==bytes(4)
   before=[state(i)for i in range(2)]
   assert all(any(q['id']==46400 for q in value['active'])for value in before)
   own_marks=[len(p.received)for p in peers]
   mark=len(master.received)
   assert(await guest.query(0x290,struct.pack('>QB',uids[1],0),0x291)).payload[:4]==bytes(4)
   for p in peers:await p.query(0x48d,b'',0x48f)
   assert cold(cfg.state_file,uids[1],identities[1]['id'])is None
   payload=expected(0,1)
   assert wstring('OwnPubGuild')not in payload
   left=sum(e.kind==0x262 and e.payload==payload for e in master.received[mark:])
   report['guild_leave_presence_count']=left
   assert left==1
   remaining=sum(q['id']==46400 for q in state(1)['active'])
   report['active_guild_tasks_after_leave']=remaining
   assert remaining==int(report['baseline'])
   guest_reset=[e for e in guest.received[own_marks[1]:]if e.kind==0x2b]
   assert bool(guest_reset)!=report['baseline']
   if not report['baseline']:
    assert(await master.query(0x285,wstring('OwnPub1')+struct.pack('>Q',uids[1]),0x286)).payload[:4]==bytes(4)
    await guest.until(0x287)
    assert(await guest.query(0x288,struct.pack('>i',guild)+wstring('OwnPub0')+bytes(4),0x289)).payload==bytes(4)
    assert(await guest.query(0xee,struct.pack('>ii',46400,10045),0xef)).payload==bytes(4)
    assert next(q for q in state(1)['active']if q['id']==46400)['objectives']=={46213:0}
    kick_mark=len(guest.received)
    assert(await master.query(0x290,struct.pack('>QB',uids[1],1),0x291)).payload[:4]==bytes(4)
    await guest.query(0x48d,b'',0x48f)
    assert cold(cfg.state_file,uids[1],identities[1]['id'])is None
    assert not any(q['id']==46400 for q in state(1)['active'])
    assert any(e.kind==0x2b for e in guest.received[kick_mark:])
    report['rejoin_fresh_objectives_and_kick_reset']=True
   disband_mark=len(guest.received)
   assert(await master.query(0x294,b'',0x295)).payload==bytes(4)
   await guest.query(0x48d,b'',0x48f)
   if not report['baseline']:
    final_friend=expected(1,0)
    assert wstring('OwnPubGuild')not in final_friend
    assert any(e.kind==0x262 and e.payload==final_friend for e in guest.received[disband_mark:])
    report['friend_guild_cleared_after_disband']=True
   assert cold(cfg.state_file,uids[0],identities[0]['id'])is None
   remaining=sum(q['id']==46400 for q in state(0)['active'])
   report['active_guild_tasks_after_disband']=remaining
   assert remaining==int(report['baseline'])
   for i,p in enumerate(peers):
    after=state(i)
    assert [q for q in after['active']if q['id']!=46400]==[q for q in before[i]['active']if q['id']!=46400]
    assert after['completed']==before[i]['completed']
    resets=[e for e in p.received[own_marks[i]:]if e.kind==0x2b]
    if not report['baseline']:
     from els_server.protocol.quest_messages import initialization
     session=app.playing[identities[i]['id']]
     expected_reset=next(e.payload for e in session.activity2026_awards.finalize(session,[initialization(after)])if e.kind==0x2b)
     def active_ids(raw):
      count=struct.unpack_from('>I',raw,4)[0];offset=8;ids=[]
      for _ in range(count):
       qid,owner,unused,n=struct.unpack_from('>iQQI',raw,offset);ids.append(qid);offset+=24+7*n
      return ids
     report.setdefault('quest_reset_checks',[]).append(dict(index=i,count=len(resets),actual_size=len(resets[-1].payload),expected_size=len(expected_reset),first_different=next((j for j,(a,b)in enumerate(zip(resets[-1].payload,expected_reset))if a!=b),None)))
     report['quest_reset_checks'][-1].update(actual_quest_ids=active_ids(resets[-1].payload),expected_quest_ids=active_ids(expected_reset))
     assert resets[-1].payload==expected_reset
   report.update(passed=True,actual_guild_accept_leave_disband=True,unrelated_quests_preserved=True)
  except BaseException:report['error']=traceback.format_exc()
  finally:
   for p in peers:await p.close()
   if server is not None:await server.close()
   if app is not None:app.close()
   from els_server.domain import friend_flow
   report['friend_flow_sha256']=hashlib.sha256(Path(friend_flow.__file__).read_bytes()).hexdigest()
 report['temporary_directory_removed']=not private.exists()
 path=env.HERE/('quest-departure-'+str(time.time_ns())+'.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(report,evidence=str(path))));return report['passed']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
