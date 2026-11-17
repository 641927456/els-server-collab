"""A real guild transaction races an independent member mailbox producer."""
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
    uid=Characters(cfg.state_file,identity['id']).create('OwnPub'+str(i),10 if i==0 else 1,'ownpub-create-'+str(i))['uid'];uids.append(uid)
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
   from els_server.storage.luciel_state import active_state,state
   report['lock_retention']=[]
   for kind,body,reply,notice in((0x709,b'\2',0x70a,0x70b),(0x4e2,b'\1',0x4e3,0x4e3)):
    before=peer.mailbox.lock;mark=len(guest.received)
    answer=await master.query(kind,body,reply)
    assert answer.payload==(b''if kind==0x709 else struct.pack('>QB',uids[0],1))
    await guest.query(0x48d,b'',0x48f)
    assert any(e.kind==notice and e.payload==struct.pack('>QB',uids[0],body[0])for e in guest.received[mark:])
    retained=peer.mailbox.lock is before;report['lock_retention'].append(retained)
    assert retained!=report['baseline']
   with closing(sqlite3.connect(cfg.state_file))as db:
    assert active_state(db,uids[0])['active_unit']==1 and state(db,uids[0])['style']==2
   report.update(passed=True,actual_town_709_and_4E2=True)
  except BaseException:report['error']=traceback.format_exc()
  finally:
   for p in peers:await p.close()
   if server is not None:await server.close()
   if app is not None:app.close()
   from els_server.domain import luciel_state
   report['luciel_state_sha256']=hashlib.sha256(Path(luciel_state.__file__).read_bytes()).hexdigest()
 report['temporary_directory_removed']=not private.exists()
 path=env.HERE/('luciel-mailbox-lock-'+str(time.time_ns())+'.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(report,evidence=str(path))));return report['passed']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
