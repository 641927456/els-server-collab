from common import *
import sys,time
sys.path.insert(0,str(R/'tools/pylibs'))
action=sys.argv[1];held();D=Path(read(P/'final-build.json')['path']).parent;build=read(D/'build.json')
if action=='install':
 assert read(R/'releases/local/current.json')==held()['parents']['local']
 assert read(P/'online-public-acceptance.json')['ok']
 args=[str(C/'python/python.exe'),'-B','-X','utf8',str(C/'tools/install_unified_runtime.py'),'--workspace',str(R),'--manifest',str(D/'runtime-files.json'),'--result',str(P/'local-installation.json'),'--publication',str(P/'reservation.json')]
 q=subprocess.run(args,cwd=C,capture_output=True,timeout=240,creationflags=0x08000000);(P/'local-install.log').write_bytes(q.stdout+q.stderr);assert q.returncode==0,(q.stdout+q.stderr).decode('utf8','replace')[-2000:];print(json.dumps(read(P/'local-installation.json')))
elif action=='start':
 compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe';exe=P/'local_actual_reader.exe'
 q=subprocess.run([str(compiler),'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll',str(P/'local_actual_reader.cs')],capture_output=True,timeout=60);assert q.returncode==0,q.stdout.decode(errors='replace')
 with(P/'local-actual-reader.log').open('xb')as log:
  p=subprocess.Popen([str(exe),build['exe'],str(R),str(P/'local-actual-loaded.json'),str(P/'stop-local-actual-reader')],cwd=R,stdout=log,stderr=log,creationflags=0x08000000)
  save(P/'local-actual-reader-process.json',dict(pid=p.pid,owner_thread=OWNER,executable=str(exe)))
  deadline=time.monotonic()+90
  while not(P/'local-actual-loaded.json').exists():
   assert p.poll()is None and time.monotonic()<deadline,'Actual final launcher did not start the selected local server';time.sleep(.25)
 print(json.dumps(read(P/'local-actual-loaded.json')))
elif action=='finish':
 loaded=read(P/'local-actual-loaded.json');assert read(P/'local-public-acceptance.json')['ok']
 import datetime
 began=datetime.datetime.fromisoformat(loaded['observation_started_utc'].replace('Z','+00:00')).timestamp()
 assert time.time()-began>=120,'Wait for the ongoing owned local observation before stopping it'
 (P/'stop-local-actual-reader').write_text('own local acceptance complete','utf8')
 import psutil
 reader=read(P/'local-actual-reader-process.json')
 if psutil.pid_exists(reader['pid']):
  process=psutil.Process(reader['pid']);assert Path(process.exe()).resolve()==Path(reader['executable']).resolve();process.wait(timeout=40)
 else:assert read(P/'local-actual-loaded.json.observation.json')['normal_stop']
 observation=read(P/'local-actual-loaded.json.observation.json');assert observation['observation_seconds']>=120
 assert not psutil.pid_exists(loaded['pid']),'Own backend did not exit normally'
 import sqlite3,collections
 from contextlib import closing
 def snapshot(path):
  with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True))as db:
   db.execute('BEGIN');result={}
   for name,sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'AND name NOT LIKE 'sqlite_%'"):
    table='"'+name.replace('"','""')+'"';result[name]=(sql,collections.Counter(hashlib.sha256(repr(row).encode()).hexdigest()for row in db.execute('SELECT *FROM '+table)))
   return result
 before=snapshot(Path(read(P/'local-installation.json')['backup'])/'game-before.sqlite3');after=snapshot(Path(read(P/'local-parent-stores.private.json')['game']))
 allocator_advances=[]
 for table,(schema,rows)in before.items():
  assert after[table][0]==schema,'Unexpected original local table schema change: '+table
  if table=='inventory_sequence':
   values=[]
   for path in(Path(read(P/'local-installation.json')['backup'])/'game-before.sqlite3',Path(read(P/'local-parent-stores.private.json')['game'])):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))as db:values.append(db.execute('SELECT id,next_uid FROM inventory_sequence').fetchall())
   assert len(values[0])==len(values[1])==1 and values[0][0][0]==values[1][0][0]==1
   assert 0<values[0][0][1]<=values[1][0][1]
   allocator_advances.append(dict(table=table,before=values[0][0][1],after=values[1][0][1],never_decreased=True))
  else:assert not(rows-after[table][1]),'Original local player data changed: '+table
 preservation=dict(ok=True,original_tables=len(before),all_original_player_typed_rows_retained=True,global_allocator_advances=allocator_advances,player_database_restore=False);save(P/'local-store-preservation.json',preservation)
 save(P/'local-runtime-acceptance.json',dict(ok=True,loaded=loaded,observation=observation,local_IP='127.0.0.1',same_signed_runtime=True,preservation=preservation));print(json.dumps(dict(ok=True,observation_seconds=observation['observation_seconds'],own_backend_normally_stopped=True,all_original_player_rows_retained=True,allocator_advances=allocator_advances)))
else:raise ValueError(action)
