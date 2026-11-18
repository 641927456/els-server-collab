"""Run precisely the future publication QA on an isolated real App/TLS."""
from pathlib import Path
import asyncio,ctypes,hashlib,json,sqlite3,ssl,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;R=Path('G:/els');D=W.parent/'duel-wire-v2';full=D/'full-source'
sys.dont_write_bytecode=True;sys.path[:0]=[str(full),str(R/'tools'),str(R/'tools/pylibs'),str(W)]
_sqlite=ctypes.WinDLL(str(full/'python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from create_friends_certificate import create
import combined_fixture
from combined_qa_client import scenario
from combined_lifecycle_client import scenario as lifecycle

async def main():
    report=dict(ok=False,private_authenticated_TLS=True,native_game=False,natural_GUI=False,production_database_access=False,checks=[],source_manifest_sha256=hashlib.sha256((D/'candidate-manifest.json').read_bytes()).hexdigest())
    app=server=None;events=[]
    with tempfile.TemporaryDirectory(prefix='owned-duel-publication-',dir=W)as name:
        own=Path(name);create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'game.sqlite3',accounts_file=own/'accounts.sqlite3',tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for index,letter in enumerate('ABC'):
                identity=app.registry.create('ownduelpub'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('DuelPub'+letter,index+1,'duel-pub-'+letter)['uid']
                values.append(dict(account_id=identity['id'],uid=uid,character_name='DuelPub'+letter,identity=identity))
            combined_fixture.seed(cfg.state_file,values)
            server=GameServer(cfg,app,lambda event,**kw:events.append(dict(event=event,**kw)));_,port=await server.start()
            for value in values:
                a=value.pop('identity');value['bridge']=dict(host='127.0.0.1',port=port,name=a['name'],token=a['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
            snapshot=lambda:combined_fixture.snapshot(cfg.state_file,values)
            await scenario(values,snapshot,report,b'');assert report['ok']
            report['ok']=False;await lifecycle(values,snapshot,report)
        except BaseException:report.update(ok=False,error=traceback.format_exc())
        finally:
            if server is not None:await server.close()
            if app is not None:app.close()
    report['worker_errors']=[r for r in events if r['event']in('worker_error','notification_error','connection_task_error')]
    report['ok']=report['ok']and not report['worker_errors'];report['owned_directory_removed']=not own.exists()
    out=W/('combined-private-'+str(time.time_ns())+'.json');out.write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],error=report.get('error'),worker_errors=report['worker_errors'],evidence=str(out))))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
