"""Qualify the exact delivery fixture and scenario before publishing any version."""
from pathlib import Path
import sys
F=Path(__file__).resolve().parent;sys.path.insert(0,str(F))
from qa_environment import R,B
sys.path[:0]=[str(F/'delivery-qa')]
import asyncio,hashlib,json,ssl,tempfile,time,traceback
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from create_friends_certificate import create
import achievement_fixture
from achievement_notebook_client import scenario
assert Path(achievement_fixture.__file__).resolve()==F/'delivery-qa/achievement_fixture.py'


async def run():
    report=dict(ok=False,private_delivery_scenario=True,production_database_access=False,native_Game=False)
    app=server=None;errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-social-delivery-',dir=F)as directory:
        path=Path(directory);create(path,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,state_file=path/'game.sqlite3',
            accounts_file=path/'accounts.sqlite3',tls_cert=path/'server-cert.pem',tls_key=path/'server-key.pem',log_dir=path/'logs')
        try:
            app=Application(cfg);await app.start();actors=[]
            for i,letter in enumerate('ABC'):
                account=app.registry.create('ownedsocialdelivery'+letter.lower());name='ASoc'+letter
                actors.append(dict(account_id=account['id'],uid=Characters(cfg.state_file,account['id']).create(name,(14,14,1)[i],'owned-notebook-delivery-'+letter)['uid'],
                    character_name=name,bridge=dict(host='127.0.0.1',port=0,name=account['name'],token=account['token'],certificate_sha256='')))
            achievement_fixture.seed(cfg.state_file,actors)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for actor in actors:actor['bridge'].update(port=port,certificate_sha256=pin)
            await scenario(actors,lambda:achievement_fixture.snapshot(cfg.state_file,actors),report)
            assert not errors,errors
        except BaseException:report.update(ok=False,error=traceback.format_exc())
        finally:
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['actual_parent_release']=B.name
    report['actual_parent_manifest_sha256']=hashlib.sha256((B/'rollup-manifest.json').read_bytes()).hexdigest()
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    report['scenario_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'delivery-qa').glob('achievement_*.py')}
    (F/('delivery-scenario-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(report));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
