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
   assert(await master.query(0xea,struct.pack('>BHIiii',0,0,1,110845,1,10018),0xeb)).payload[:4]==bytes(4)
   license=next(i for i in actor.account.get_inventory_snapshot()['items']if i['template']==110845)
   assert(await master.query(0x276,struct.pack('>Q',license['uid'])+wstring('OwnPubGuild')+wstring(''),0x277)).payload[:4]==bytes(4)
   from els_server.storage.guild_membership_state import cold
   guild=cold(cfg.state_file,uids[0],identities[0]['id'])['id']
   assert(await master.query(0x285,wstring('OwnPub1')+struct.pack('>Q',uids[1]),0x286)).payload[:4]==bytes(4)
   await guest.until(0x287)
   assert(await guest.query(0x288,struct.pack('>i',guild)+wstring('OwnPub0')+bytes(4),0x289)).payload==bytes(4)
   for kind,body,reply in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),(0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
    assert(await guest.query(kind,body,reply)).payload[:4]==bytes(4)
   from els_server.domain import guild_services as service
   from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
   from els_server.storage.inventory_state import grant_items
   from els_server.storage import guild_system_state as system
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    db.execute('BEGIN IMMEDIATE')
    item=grant_items(db,[dict(template=135862,metadata=VERIFIED_TEMPLATES[135862],group=TEMPLATE_BAG_GROUPS[135862],quantity=1)],uids[0])[0]
   assert(await master.query(0x219,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0),0x21a)).payload[:4]==bytes(4)
   with closing(sqlite3.connect(cfg.state_file))as db:
    end=system.read(db,guild)['services']['1034']['end']
   real_connect=sqlite3.connect
   class Waiting(sqlite3.Connection):
    def execute(self,sql,*a,**kw):
     if sql=='BEGIN IMMEDIATE':entered.set()
     return super().execute(sql,*a,**kw)
   def connect(*a,**kw):return real_connect(*a,**kw,factory=Waiting)
   def synchronize():
    with app.dungeon_workers.scope(peer),app.world_lock:return service.synchronize(peer)
   report['cases']=[]
   for expire in(True,False):
    with closing(real_connect(cfg.state_file))as db,db:
     db.execute('BEGIN IMMEDIATE');saved=system.read(db,guild)
     # Owned fixture is an otherwise unchanged member who has not visited
     # since the actual native219 contract activation above.
     system.member(saved,uids[1])['services']={};system.write(db,guild,saved)
    with closing(real_connect(cfg.state_file))as db:before=list(db.iterdump())
    entered=ThreadEvent();clock=[end-2]
    with closing(real_connect(cfg.state_file))as holder:
     holder.execute('BEGIN IMMEDIATE')
     with ThreadPoolExecutor(max_workers=1)as pool,patch.object(service,'sqlite3',SimpleNamespace(connect=connect,Error=sqlite3.Error)),patch.object(service,'time',SimpleNamespace(time=lambda:clock[0])):
      future=pool.submit(synchronize);assert entered.wait(3)
      clock[0]=end if expire else end-1;holder.commit();events=future.result(timeout=4)
    with closing(real_connect(cfg.state_file))as db:
     after=list(db.iterdump());granted=bool(system.member(system.read(db,guild),uids[1]).get('services',{}))
    expected=not expire or report['baseline']
    assert granted==expected
    if expire and not report['baseline']:assert before==after
    report['cases'].append(dict(expired_while_waiting=expire,service_granted=granted,SQL_unchanged=before==after,response_kinds=[hex(e.kind)for e in events]))
   report.update(passed=True,actual_contract_item_consumed=True,actual_504_member=True,controlled_clock=True)
  except BaseException:report['error']=traceback.format_exc()
  finally:
   for p in peers:await p.close()
   if server is not None:await server.close()
   if app is not None:app.close()
   report['service_sha256']=hashlib.sha256(Path(service.__file__).read_bytes()).hexdigest()if'service'in locals()else None
 report['temporary_directory_removed']=not private.exists()
 path=env.HERE/('service-clock-'+str(time.time_ns())+'.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(report,evidence=str(path))));return report['passed']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
