"""Normal authenticated shop listing, 50 ED purchase, cold storage and denial."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent;H=W.parents[1]/'housing-pets-v1';B=H.parent/'transport-routing-variants-v1/full-source-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(H.parent/'delivery-duel-v1')]
ctypes.WinDLL(str(H.parent/'duel-wire-v2/full-source/python/sqlite3.dll'))
import els_server.domain,els_server.storage,els_server.protocol
for pkg,name in((els_server.domain,'domain'),(els_server.storage,'storage'),(els_server.protocol,'protocol')):
 pkg.__path__.insert(0,str(H/'candidate-v4/els_server'/name))
els_server.domain.__path__.insert(0,str(W/'candidate/els_server/domain'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.town_travel import catalog
from els_server.domain import shop_additions
from create_friends_certificate import create
from native_peer import connect

async def main():
 report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,
  production_database_access=False,template=277150,ED_each=50,checks=[])
 app=server=None;peers=[];errors=[];stage='setup'
 with tempfile.TemporaryDirectory(prefix='owned-invitation-shop-',dir=W)as name:
  private=Path(name).resolve();assert private.parent==W.resolve();create(private,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  try:
   assert Path(shop_additions.__file__).resolve()==(W/'candidate/els_server/domain/shop_additions.py').resolve()
   offers=[r for r in shop_additions.offers(1)if r['template']==277150]
   assert len(offers)==1 and(offers[0]['price'],offers[0]['quantity'])==(50,1)
   app=Application(cfg);await app.start();identity=app.registry.create('ownedinviteshop')
   uid=Characters(cfg.state_file,identity['id']).create('InviteShop',1,'owned-invitation-shop')['uid']
   LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
   with closing(sqlite3.connect(cfg.state_file))as db,db:db.execute('UPDATE reward_balances SET ed=200 WHERE uid=?',(uid,))
   def read(sql,args=()):
    with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
   def saved():return read('SELECT template,count FROM inventory_items WHERE owner=?AND template=277150 ORDER BY uid',(uid,))
   server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
   _,port=await server.start();bridge=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
   actor=dict(uid=uid,bridge=bridge);peer=await connect(actor,peers);sku=1200277150
   stage='normal listing and two-ticket purchase'
   listing=await peer.query(0x80d,struct.pack('>i',1));assert struct.pack('>I',sku)in listing.payload
   answer=await peer.query(0x80f,struct.pack('>IIH',1,sku,2));assert answer.payload[:4]==bytes(4)
   assert read('SELECT ed FROM reward_balances WHERE uid=?',(uid,))==[(100,)]and sum(n for _,n in saved())==2
   report['checks'].append('Normal80D lists the SKU; original80F buys two for exactly100 ED')
   await peer.close();peers.remove(peer)
   async with asyncio.timeout(8):
    while identity['id']in app.playing:await asyncio.sleep(.01)
   peer=await connect(actor,peers);assert sum(n for _,n in saved())==2
   stage='cold purchase and insufficient balance'
   await peer.query(0x80d,struct.pack('>i',1))
   answer=await peer.query(0x80f,struct.pack('>IIH',1,sku,1));assert answer.payload[:4]==bytes(4)
   before=saved();assert sum(n for _,n in before)==3 and read('SELECT ed FROM reward_balances WHERE uid=?',(uid,))==[(50,)]
   answer=await peer.query(0x80f,struct.pack('>IIH',1,sku,2));assert answer.payload[:4]!=bytes(4)
   assert saved()==before and read('SELECT ed FROM reward_balances WHERE uid=?',(uid,))==[(50,)]and not errors
   report['checks'].append('Cold reauthentication preserves tickets; one costs50 ED; insufficient ED preserves items and balance')
   report.update(ok=True,source_sha256=hashlib.sha256(Path(shop_additions.__file__).read_bytes()).hexdigest(),source_manifest_sha256=hashlib.sha256((H/'candidate-v4.manifest.json').read_bytes()).hexdigest())
  except BaseException:report.update(stage=stage,error=traceback.format_exc())
  finally:
   for peer in reversed(peers):await peer.close()
   if server is not None:await server.close()
   if app is not None:app.close()
 report.update(owned_private_directory_removed=not private.exists(),owned_listeners_closed=True)
 out=W/('blank-invitation-shop-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(main()))
