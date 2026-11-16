"""Run the delivery client against three owned isolated native TLS actors."""
from pathlib import Path
import asyncio,hashlib,json,os,ssl,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;ROOT=W.parent;SOURCE=Path(os.environ.get('ELS_FULL_SOURCE',str(ROOT/'performance-integration-v1/test-full-source')))
CANDIDATE=Path(os.environ.get('ELS_CANDIDATE_SOURCE',str(ROOT/'performance-integration-v1/candidate')))
if '--source' in sys.argv:
 SOURCE=Path(sys.argv[sys.argv.index('--source')+1]).resolve();CANDIDATE=SOURCE.parent/'candidate'
sys.dont_write_bytecode=True;sys.path[:0]=[str(SOURCE),str(SOURCE/'vendor'),'G:/els/tools/pylibs','G:/els/tools','G:/els']
import ctypes
_sqlite_runtime=ctypes.WinDLL(str(SOURCE/'python/sqlite3.dll'))
import els_server,els_server.domain,els_server.protocol,els_server.storage
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from tools.create_friends_certificate import create
from combined_qa_client import scenario
import combined_fixture

async def main():
 report=dict(ok=False,private_authenticated_TLS=True,production_database_access=False,natural_GUI=False,
             checks=[],source_view=str(SOURCE),source_files={p.relative_to(CANDIDATE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(CANDIDATE.rglob('*'))if p.is_file()})
 app=server=None
 with tempfile.TemporaryDirectory(prefix='owned-combined-delivery-',dir=W)as name:
  own=Path(name);create(own,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'own.sqlite3',accounts_file=own/'accounts.sqlite3',
       tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
  try:
   app=Application(cfg);await app.start();values=[]
   for letter in 'ABC':
    actor=app.registry.create('ownedclose'+letter.lower())
    uid=Characters(cfg.state_file,actor['id']).create('OwnClose'+letter,1,'owned-close-create-'+letter)['uid']
    values.append(dict(account_id=actor['id'],uid=uid,character_name='OwnClose'+letter,identity=actor))
   combined_fixture.seed(cfg.state_file,values)
   server=GameServer(cfg,app,lambda *args,**kw:None);_,port=await server.start()
   for value in values:
    actor=value.pop('identity');value['bridge']=dict(host='127.0.0.1',port=port,name=actor['name'],token=actor['token'],
        certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
   capture=json.loads((Path('G:/els')/'analysis/unified-continuation-20261028-v1/agent-c/v7/photo-packet-attempts.jsonl').read_text('utf8').splitlines()[-1])
   leave=bytes.fromhex(capture['native_empty_stat_leave_request']['wire_hex'])
   await scenario(values,lambda:combined_fixture.snapshot(cfg.state_file,values),report,leave)
  except BaseException:report.update(ok=False,error=traceback.format_exc())
  finally:
   if server is not None:await server.close()
   if app is not None:app.close()
 report['owned_temporary_directory_removed']=not own.exists()
 p=W/('combined-private-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2),'utf8')
 print(json.dumps({k:report[k]for k in('ok','checks','owned_temporary_directory_removed','error')if k in report}|dict(evidence=str(p))))
 return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
