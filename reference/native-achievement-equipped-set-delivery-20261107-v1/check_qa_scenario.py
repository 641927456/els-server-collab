"""Run the exact forthcoming public requests against the selected signed runtime."""
from pathlib import Path
import asyncio,ctypes,hashlib,json,ssl,sys,tempfile,traceback
H=Path(__file__).resolve().parent
runtime=Path(json.loads((H/'launcher-preview-v101/built-selection-verification.json').read_bytes())['selected_root'])
sys.dont_write_bytecode=True
sys.path[:0]=[str(H),str(runtime),str(runtime/'vendor'),str(runtime/'tools'),str(Path('G:/els/tools/pylibs'))]
ctypes.WinDLL(str(runtime/'python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from create_friends_certificate import create
from achievement_equipment_client import scenario
import achievement_fixture


async def main():
    report=dict(ok=False,production_database_access=False,actual_selected_runtime=str(runtime),checks=[])
    errors=[];app=server=None
    try:
        with tempfile.TemporaryDirectory(prefix='own-qa-scenario-',dir=H)as folder:
            private=Path(folder);create(private,'127.0.0.1')
            cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,normal_equipment_moves_enabled=True,
                state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
                tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
            try:
                app=Application(cfg);await app.start()
                actors=[]
                for i in range(3):
                    identity=app.registry.create('ownedachqa'+str(i))
                    name='OwnAchQA'+str(i)
                    actors.append(dict(account_id=identity['id'],uid=Characters(cfg.state_file,identity['id']).create(name,i+1,'owned-scenario-'+str(i))['uid'],character_name=name,identity=identity))
                server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
                _,port=await server.start()
                pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
                for actor in actors:
                    identity=actor.pop('identity')
                    actor['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=pin)
                achievement_fixture.seed(cfg.state_file,actors)
                await scenario(actors,lambda:achievement_fixture.snapshot(cfg.state_file,actors),report)
                assert not errors,errors
            finally:
                if server is not None:await server.close()
                if app is not None:app.close()
    except BaseException:report.update(ok=False,error=traceback.format_exc())
    report['errors']=errors
    (H/'qa-scenario-qualification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False))
    return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
