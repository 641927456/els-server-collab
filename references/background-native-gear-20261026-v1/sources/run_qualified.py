"""Create one fresh owned QA run from the qualified, hash-bound background scripts."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,uuid
T=Path(__file__).resolve().parent;R=T.parents[1]
assert R==Path('G:/els')
assert not (R/'analysis/coordination-20261015/active-publication.lock').exists(),'Formal publication holds the shared window; no background launch'
proof=json.loads((T/'background-native-qualified-v1.json').read_bytes())
assert proof['passed']and proof['complete_native_actions']==16 and proof['cold_client_verified']
for rel,digest in proof['source_files'].items():
 assert hashlib.sha256((R/rel).read_bytes()).hexdigest()==digest,'Qualified source changed: '+rel
sys.path.insert(0,str(R/'tools/pylibs'));import psutil
assert not any((p.info['name']or'').lower()in('x2.exe','x2_dx11.exe')for p in psutil.process_iter(['name'])),'An existing game is open; no launch or attachment'
name='native-background-run-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
out=T/name;out.mkdir()
for leaf in ('controller.py','probe_isolated.py'):
 (out/leaf).write_bytes((T/proof['qualified_templates']/leaf).read_bytes())
env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
with(out/'controller-console.log').open('wb')as log:
 process=subprocess.run([sys.executable,'-B','-X','utf8',str(out/'controller.py')],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=700)
result=json.loads((out/'result.json').read_bytes())
print(json.dumps(dict(output=str(out),passed=result['ok'],own_QA_cleaned=result['own_QA_cleaned'],capacity_verified=result['capacity_verified']),ensure_ascii=False))
assert process.returncode==0 and result['ok']and result['own_QA_cleaned']and result['capacity_verified']
