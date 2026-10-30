"""Trusted launcher-owned local deployment control. No database restore operation."""
from pathlib import Path, PurePosixPath
from contextlib import contextmanager, ExitStack, closing
import argparse, ast, base64, hashlib, json, os, shutil, socket, sqlite3, subprocess, sys, tempfile, time, tomllib, uuid

SCHEMA='els-local-oneclick-v1'
FLAGS=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def hashed(raw):return hashlib.sha256(raw).hexdigest()
def atomic(p,doc):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
 with t.open('xb')as f:f.write(json.dumps(doc,ensure_ascii=False,indent=2).encode());f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def progress(percent,message):print('ELS_UPDATE_PROGRESS:'+json.dumps(dict(percent=percent,message=message),ensure_ascii=True),flush=True)
def need(condition,message):
 if not condition:raise RuntimeError(message)
def under(root,name):
 root=Path(root).resolve();rel=PurePosixPath(name)
 need(not rel.is_absolute()and ':'not in name and '\\'not in name and all(s not in ('..','')for s in rel.parts),'更新路径无效')
 p=root.joinpath(*rel.parts)
 need(p.resolve().is_relative_to(root)and p.resolve()!=root,'更新路径越界')
 for a in [p,*p.parents]:
  if a==root:break
  need(not a.is_symlink()and not (hasattr(a,'is_junction')and a.is_junction()),'更新目录含链接，已停止')
 return p
def command(args,cwd,timeout=120,accepted=(0,)):
 q=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,timeout=timeout,creationflags=FLAGS,env=dict({k:v for k,v in os.environ.items()if not k.upper().startswith('GIT_')},PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never'))
 need(q.returncode in accepted,'自动检查失败；当前运行版已保留，请查看更新记录')
 return q
def toml_document(doc):
 def value(v):return str(v).lower()if type(v)is bool else json.dumps(v,ensure_ascii=True)
 return '[server]\n'+'\n'.join(key+'='+value(v)for key,v in doc.items())+'\n'
def git(repo,*args,accepted=(0,)):
 return command(['git','-c','core.hooksPath='+str(Path(tempfile.gettempdir())/('els-no-hooks-'+str(os.getpid()))),*args],repo,accepted=accepted)
def gtext(repo,*args):return git(repo,*args).stdout.decode('utf8').strip()
def blob(repo,commit,name):
 q=git(repo,'cat-file','-p',commit+':'+name,accepted=(0,128))
 return q.stdout if q.returncode==0 else None
def sources(repo,commit):
 raw=git(repo,'ls-tree','-rz','--full-tree',commit).stdout;result={}
 for entry in raw.split(b'\0'):
  if not entry:continue
  meta,name=entry.split(b'\t',1);name=name.decode('utf8');mode,kind,oid=meta.decode().split()
  if allowed(name):
   need(mode in ('100644','100755')and kind=='blob','服务端源码含不支持的链接或子模块')
   result[name]=oid
 return result
def allowed(name):
 p=PurePosixPath(name)
 # Runtime-only overlay. Native/client scripts, secrets, config/server.toml,
 # Python and static SQLite resources stay exactly on the installed local branch.
 return (name.startswith('els_server/')and p.suffix in ('.py','.json'))or('/'not in name and p.suffix=='.py')or(name.startswith('config/')and p.suffix=='.json')
def local(workspace):
 p=read(workspace/'releases/local/current.json');need(p.get('channel')=='local','本地发布指针无效')
 root=under(workspace,p['path']);need(root.is_relative_to(workspace/'releases/local'),'本地发布目录无效')
 need(sha(root/'local-business-manifest.json')==p['manifest_sha256'],'当前本地清单摘要不匹配')
 rows=read(root/'client-bundle-manifest.json')['files'];seen=set()
 for row in rows:
  need((not row['path'].startswith('state/')or row['path']=='state/friends-client.example.json')and row['path']not in seen,'本地运行清单含存档或重复路径');seen.add(row['path']);file=under(root,row['path'])
  need(file.is_file()and file.stat().st_size==row['size']and sha(file)==row['sha256'],'当前本地运行文件已变化：'+row['path'])
 return p,root,rows
def dbdigest(path):
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:
  db.execute('BEGIN');h=hashlib.sha256()
  for name,sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
   h.update(json.dumps([name,sql],ensure_ascii=True).encode());quoted='"'+name.replace('"','""')+'"';items=[]
   for row in db.execute('SELECT * FROM '+quoted):
    raw=json.dumps([(type(v).__name__,v.hex()if isinstance(v,bytes)else v)for v in row],ensure_ascii=True,separators=(',',':')).encode();items.append(hashed(raw))
   for item in sorted(items):h.update(item.encode())
  return h.hexdigest()
def database_floor(path):
 from collections import Counter
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:
  db.execute('BEGIN');result={}
  for name,sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
   quoted='"'+name.replace('"','""')+'"'
   values=Counter(hashed(json.dumps([(type(v).__name__,v.hex()if isinstance(v,bytes)else v)for v in row],ensure_ascii=True,separators=(',',':')).encode())for row in db.execute('SELECT * FROM '+quoted))
   result[name]=(sql,values)
  return result
def preserve_floor(before,after):
 for name,(sql,rows)in before.items():
  need(name in after and after[name][0]==sql and not(rows-after[name][1]),'候选启动会更改已有存档结构或数据，已停止自动安装：'+name)
def api_backup(source,dest):
 dest.parent.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+45
 def bounded(*args):need(time.monotonic()<deadline,'数据库备份超时')
 with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True))as src,closing(sqlite3.connect(dest))as dst:
  src.backup(dst,pages=128,progress=bounded);need(dst.execute('PRAGMA quick_check').fetchall()==[('ok',)],'数据库备份检查失败')
 need(dbdigest(source)==dbdigest(dest),'数据库备份内容不一致')
def config_paths(root,workspace):
 doc=tomllib.loads((root/'config/server.toml').read_text('utf8'))['server']
 need(doc.get('mode','local')=='local'and doc.get('host')=='127.0.0.1','只允许更新本地服务端')
 def path(value):return(root/'config'/value).resolve()
 save=path(doc.get('state_file','../state/integrated.sqlite3'))
 need(save.is_relative_to(workspace/'state'),'本地存档必须保留在工作目录 state 内')
 accounts=path(doc['accounts_file'])if doc.get('accounts_file')else workspace/'state/friends/accounts.sqlite3'
 need(accounts.is_relative_to(workspace/'state')and accounts!=save,'账号库路径无效')
 return doc,[p for p in (save,accounts)if p.exists()],save
def psutil_for(root):
 sys.path.insert(0,str(root/'tools/pylibs'));import psutil
 return psutil
def idle(psutil):
 for p in psutil.process_iter(['name']):
  try:need((p.info['name']or'').lower()not in ('x2.exe','x2_dx11.exe'),'请先正常退出游戏，再一键更新本地服务端')
  except psutil.Error:pass
def port_idle(port):
 with socket.socket()as s:
  try:s.bind(('127.0.0.1',port))
  except OSError:raise RuntimeError('本地服务监听尚未排空，已停止安装')
def leases(root,dbs,stack):
 # Load the already installed SaveLease without importing candidate code.
 ns={};exec(compile((root/'els_server/storage/lifecycle.py').read_bytes(),'<installed SaveLease>','exec'),ns)
 for db in dbs:
  stack.enter_context(ns['SaveLease'](db));connection=stack.enter_context(closing(sqlite3.connect(db,timeout=3)));connection.execute('BEGIN IMMEDIATE');stack.callback(connection.rollback)
def stop_owned(root,workspace,psutil,operation):
 idle(psutil);running=[]
 for p in psutil.process_iter(['name','cmdline','cwd','create_time']):
  try:
   args=p.info['cmdline']or[]
   if '-m'not in args or 'els_server'not in args or Path(p.info['cwd']or'').resolve()!=root:continue
   need('--check'not in args,'本地预检仍在运行')
   need('--stop-file'in args and '--config'in args,'本地服务没有正常停服接口，已保留现状')
   accepted={'--config','--stop-file','--log-dir'};i=args.index('els_server')+1
   while i<len(args):need(args[i]in accepted and i+1<len(args),'当前本地服务启动参数不支持自动重启');i+=2
   stop=Path(args[args.index('--stop-file')+1]).resolve();need(stop.is_relative_to(workspace/'state')or stop.is_relative_to(workspace/'logs'),'正常停服文件不在本地工作目录')
   need(not stop.exists(),'正常停服标记已存在，请等待服务结束')
   running.append(dict(pid=p.pid,created=p.info['create_time'],args=args,stop=str(stop)))
  except psutil.NoSuchProcess:pass
 need(len(running)<=1,'存在多个本地服务，已保留现状')
 if running:
  atomic(operation/'stopped-service.json',running[0]);stop=Path(running[0]['stop']);stop.parent.mkdir(parents=True,exist_ok=True)
  with stop.open('x',encoding='utf8')as f:f.write(SCHEMA)
  try:psutil.Process(running[0]['pid']).wait(timeout=35)
  except psutil.NoSuchProcess:pass
  except psutil.TimeoutExpired:raise RuntimeError('本地服务未能正常退出；未强制终止进程')
 return running[0]if running else None
def restart(root,workspace,old,operation):
 if old is None:return None
 args=old['args'];tail=args[args.index('els_server')+1:];tail[tail.index('--config')+1]=str(root/'config/server.toml');tail[tail.index('--stop-file')+1]=str(workspace/'state/local-updater'/('server-'+uuid.uuid4().hex+'.stop'))
 out=(operation/'service-restart.log').open('ab')
 try:p=subprocess.Popen([str(root/'python/python.exe'),'-B','-X','utf8','-m','els_server',*tail],cwd=root,stdout=out,stderr=subprocess.STDOUT,creationflags=FLAGS)
 finally:out.close()
 return dict(pid=p.pid,stop=tail[tail.index('--stop-file')+1],args=tail)
def initial_base(repo,target):
 active=json.loads(blob(repo,target,'channels/active.json')or b'{}');name=active.get('accepted_local_snapshot')or active.get('formal_local_snapshot');branch=active.get('formal_local_branch')
 need(isinstance(name,str)and name.startswith('channels/')and isinstance(branch,str)and branch.startswith('snapshot/'),'Git 仓库缺少本地共同基线，不能安全覆盖单机版')
 snapshot=json.loads(blob(repo,target,name)or b'{}');need(snapshot.get('channel')=='local'and snapshot.get('status')=='historical-formally-installed-and-accepted','Git 本地基线未经核定')
 ref='refs/remotes/origin/'+branch;q=git(repo,'rev-parse','--verify',ref,accepted=(0,128))
 if q.returncode:
  git(repo,'fetch','--no-tags','origin','refs/heads/'+branch);ref='FETCH_HEAD'
 base=gtext(repo,'rev-parse',ref+'^{commit}')
 rows={row['path']:row for row in snapshot['source_files']}
 for name in sources(repo,base):
  if name in rows:need(hashed(blob(repo,base,name))==rows[name]['sha256'],'Git 共同基线与核定清单不匹配：'+name)
 return base
def merge_changes(repo,base,target,parent,operation):
 old=sources(repo,base);new=sources(repo,target);changes={};conflicts=[]
 for name in sorted(old.keys()|new.keys()):
  if old.get(name)==new.get(name):continue
  before=blob(repo,base,name)if name in old else None;incoming=blob(repo,target,name)if name in new else None;p=under(parent,name);current=p.read_bytes()if p.is_file()else None
  if current==incoming:continue
  if current==before:merged=incoming
  elif before is not None and incoming is not None and current is not None:
   folder=operation/'merge';folder.mkdir(exist_ok=True);files=[]
   for label,raw in [('local',current),('base',before),('git',incoming)]:
    f=folder/label;f.write_bytes(raw);files.append(f)
   q=git(repo,'merge-file','-p',*map(str,files),accepted=tuple(range(256)))
   if q.returncode:conflicts.append(name);continue
   merged=q.stdout
  else:conflicts.append(name);continue
  if merged!=current:changes[name]=merged
 need(not conflicts,'代码存在合并冲突，运行版未切换：'+', '.join(conflicts[:8]))
 return changes
def checks(candidate,client,operation):
 for p in candidate.rglob('*.py'):
  if allowed(p.relative_to(candidate).as_posix())and '__pycache__'not in p.parts:compile(p.read_bytes(),str(p),'exec')
 py=candidate/'python/python.exe';config=candidate/'config/server.toml';original=config.read_bytes();doc=tomllib.loads(original.decode('utf8'))['server'];home=operation/('check-copy-'+uuid.uuid4().hex[:8]);home.mkdir()
 floors={}
 # Even --check is candidate code. Give every candidate consumer a copy of
 # state, including the native wrapper, before executing a single import.
 for field,leaf in [('state_file','game.sqlite3'),('accounts_file','accounts.sqlite3')]:
  if field not in doc and field=='accounts_file':continue
  source=(config.parent/doc.get(field,'../state/integrated.sqlite3')).resolve();dest=home/leaf
  if source.exists():api_backup(source,dest)
  else:
   with sqlite3.connect(dest):pass
  floors[dest]=database_floor(dest);doc[field]=str(dest)
 for field in ('selected2026_pair_file','tls_cert','tls_key'):
  if field in doc:doc[field]=str((config.parent/doc[field]).resolve())
 doc['log_dir']=str(home/'logs')
 try:
  config.write_text(toml_document(doc),'utf8')
  for name,args in [('server',['-m','els_server','--config',config,'--check']),('client',[candidate/'tools/launch_integrated_local.py','--client',client,'--check'])]:
   q=command([py,'-B','-X','utf8',*args],candidate,timeout=120);(operation/(name+'-check.log')).write_bytes(q.stdout+q.stderr)
  for path,floor in floors.items():preserve_floor(floor,database_floor(path))
 finally:config.write_bytes(original)
def smoke(candidate,source_save,operation,seconds,tick=None):
 home=operation/'smoke';home.mkdir();save=home/'game.sqlite3'
 if source_save.exists():api_backup(source_save,save)
 else:
  with sqlite3.connect(save):pass
 floor=database_floor(save)
 config=candidate/'config/server.toml';doc=tomllib.loads(config.read_text('utf8'))['server'];doc.update(port=0,state_file=str(save),log_dir=str(home/'logs'))
 for field in ('selected2026_pair_file','tls_cert','tls_key'):
  if field in doc:doc[field]=str((config.parent/doc[field]).resolve())
 if 'accounts_file'in doc:
  account_source=(config.parent/doc['accounts_file']).resolve();account_copy=home/'accounts.sqlite3'
  if account_source.exists():api_backup(account_source,account_copy)
  doc['accounts_file']=str(account_copy)
 (home/'isolated-server.toml').write_text(toml_document(doc),'utf8')
 ready=home/'ready.json';stop=home/'server.stop'
 log=(home/'process.log').open('ab')
 p=subprocess.Popen([str(candidate/'python/python.exe'),'-B','-X','utf8',str(Path(__file__).resolve()),'--smoke',str(candidate),str(save),str(home),str(ready),str(stop)],cwd=candidate,stdout=log,stderr=subprocess.STDOUT,creationflags=FLAGS)
 try:
  deadline=time.monotonic()+75
  while not ready.exists():need(p.poll()is None and time.monotonic()<deadline,'备份副本启动检查失败');time.sleep(.2)
  info=read(ready);start=time.monotonic();last=-1
  while time.monotonic()-start<seconds:
   need(p.poll()is None,'备份副本启动后异常退出')
   with socket.create_connection(('127.0.0.1',info['port']),timeout=2)as s:need(bool(s.recv(64)),'备份副本服务未就绪')
   elapsed=int(time.monotonic()-start)
   if tick and elapsed//15!=last:last=elapsed//15;tick(elapsed)
   time.sleep(min(2,max(.1,seconds-(time.monotonic()-start))))
  elapsed=time.monotonic()-start;stop.write_text(SCHEMA,'utf8');p.wait(timeout=35);need(p.returncode==0,'候选未能正常保存退出');preserve_floor(floor,database_floor(save))
  return dict(ok=True,seconds=elapsed,isolated_database=True,original_rows_and_schema_preserved=True,port=info['port'])
 finally:
  stop.write_text(SCHEMA,'utf8')
  try:p.wait(timeout=35)
  except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
  log.close()
def smoke_main(args):
 import asyncio
 root,save,home,ready,stop=map(Path,args);sys.path.insert(0,str(root));os.chdir(root)
 from els_server.config import ServerConfig
 from els_server.__main__ import serve
 from els_server.game_data import client_data
 client_data()
 config=ServerConfig.load(home/'isolated-server.toml')
 async def run():
  task=asyncio.create_task(serve(config,stop));deadline=time.monotonic()+65
  try:
   while not task.done():
    # EventLog announces the actual ephemeral listener after initialization.
    logs=list((home/'logs').glob('*'))if(home/'logs').exists()else[]
    for p in logs:
     if not p.is_file():continue
     for line in p.read_text('utf8',errors='replace').splitlines():
      try:row=json.loads(line)
      except ValueError:continue
      if row.get('event')=='listening'and isinstance(row.get('address'),list):atomic(ready,dict(port=row['address'][1]));await task;return
    need(time.monotonic()<deadline,'隔离服务未报告监听就绪');await asyncio.sleep(.15)
   await task
  finally:
   stop.write_text(SCHEMA,'utf8')
   if not task.done():await task
 asyncio.run(run())
def manifests(candidate,parent,pointer,changes,base,target,repo):
 rows=[]
 for p in sorted(candidate.rglob('*')):
  if p.is_file()and p.relative_to(candidate).as_posix()not in ('local-business-manifest.json','client-bundle-manifest.json','release-snapshot.json','local-verification.json')and '__pycache__'not in p.parts:
   rows.append(dict(path=p.relative_to(candidate).as_posix(),size=p.stat().st_size,sha256=sha(p)))
 prior=read(parent/'local-business-manifest.json');business={r['path']:r for r in prior['files']};by={r['path']:r for r in rows}
 for name in changes:
  if name in by:business[name]=by[name]
  else:business.pop(name,None)
 atomic(candidate/'client-bundle-manifest.json',dict(release=candidate.name,channel='local',files=rows,file_count=len(rows)))
 atomic(candidate/'local-business-manifest.json',dict(release=candidate.name,channel='local',parent_release=pointer['release'],parent_manifest_sha256=pointer['manifest_sha256'],files=list(business.values()),changed_runtime_files=sorted(changes),source_git_base=base,source_git_commit=target,source_repository=str(repo),local_branch_preserved=True,client_delta=0))
 atomic(candidate/'release-snapshot.json',dict(release=candidate.name,channel='local',status='automatic-local-candidate',local_business_manifest_sha256=sha(candidate/'local-business-manifest.json')))
 return rows
@contextmanager
def locks(workspace,journal):
 paths=[workspace/'analysis/coordination-20261015'/n for n in ('active-publication.lock','publication-record.lock')];held={};identity=dict(schema=SCHEMA,token=journal['token'],pid=os.getpid(),created=journal['created'],operation='local-oneclick-updater',journal=journal['journal'])
 try:
  for p in paths:
   p.parent.mkdir(parents=True,exist_ok=True)
   with p.open('x',encoding='utf8')as f:json.dump(identity,f);f.flush();os.fsync(f.fileno())
   held[p]=p.stat().st_ino
  yield
 finally:
  if journal.get('nine_recovery_schema')!=1 or read(journal['journal']).get('nine_safe_to_release')is True:
   for p,inode in held.items():need(p.stat().st_ino==inode and read(p)==identity,'发布锁所有权发生变化');p.unlink()
# This helper is embedded in the new raw updater only. It uses its existing
# installed lifecycle lease, exact owned stop, API backup smoke, and DB digests.
# No new data reader is discarded after writer admission or uncertain state.
NINE_GUARD_PAYLOADS = {'els_server/storage/relationships.py': {'base64': 'IiIiQXRvbWljIG9yaWdpbmFsIGNvdXBsZSBwcm9wb3NhbC9hbnN3ZXIsIGltbXV0YWJsZSBkZWJpdCBzb3VyY2UgYW5kIGNvbGQgdmlldy4iIiINCmltcG9ydCBoYXNobGliLGpzb24sc3FsaXRlMyx0aW1lDQpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJlbGF0aW9uc2hpcF9ydWxlcyBpbXBvcnQgUklORyxlbGlnaWJsZQ0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcyBpbXBvcnQgcHJvcG9zZV9yZXF1ZXN0LGFuc3dlcl9yZXF1ZXN0DQpmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wucHJvdG9jb2xfY29kZWMgaW1wb3J0IGVuY29kZV9ldmVudA0KZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaXRlbV9hY3RvciBpbXBvcnQgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyDQpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5wcm9mZXNzaW9uX3N0YXRlIGltcG9ydCByZXF1aXJlX293bmVyDQpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfc3RhdGUgaW1wb3J0IGxvYWRfaXRlbXMNCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1faW5zdGFuY2VzIGltcG9ydCByZW1vdmUNClRBQkxFUz0oJ25hdGl2ZV9jb3VwbGVfcGFpcnNfdjEnLCduYXRpdmVfY291cGxlX21lbWJlcnNfdjEnLCduYXRpdmVfY291cGxlX3BlbmRpbmdfdjEnLCduYXRpdmVfY291cGxlX2FjdGlvbnNfdjEnKQ0KU0NIRU1BUz17J25hdGl2ZV9jb3VwbGVfcGFpcnNfdjEnOiAnQ1JFQVRFIFRBQkxFIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEoaWQgVEVYVCBQUklNQVJZIEtFWSxhIElOVEVHRVIgTk9UIE5VTEwsYiBJTlRFR0VSIE5PVCBOVUxMLGFfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLGJfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLGNyZWF0ZWRfYXQgSU5URUdFUiBOT1QgTlVMTCxwcm9wb3NhbCBURVhUIE5PVCBOVUxMLGFjY2VwdGFuY2UgVEVYVCBOT1QgTlVMTCxpdGVtX3VpZCBJTlRFR0VSIE5PVCBOVUxMLHZlcnNpb24gSU5URUdFUiBOT1QgTlVMTCBDSEVDSyh2ZXJzaW9uPTEpKScsICduYXRpdmVfY291cGxlX21lbWJlcnNfdjEnOiAnQ1JFQVRFIFRBQkxFIG5hdGl2ZV9jb3VwbGVfbWVtYmVyc192MShvd25lciBJTlRFR0VSIFBSSU1BUlkgS0VZIFJFRkVSRU5DRVMgY2hhcmFjdGVycyh1aWQpLGFjY291bnRfaWQgSU5URUdFUiBOT1QgTlVMTCxwYWlyX2lkIFRFWFQgTk9UIE5VTEwgUkVGRVJFTkNFUyBuYXRpdmVfY291cGxlX3BhaXJzX3YxKGlkKSknLCAnbmF0aXZlX2NvdXBsZV9wZW5kaW5nX3YxJzogJ0NSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEob3BlcmF0aW9uIFRFWFQgUFJJTUFSWSBLRVkscHJvcG9zZXIgSU5URUdFUiBOT1QgTlVMTCBVTklRVUUscmVjaXBpZW50IElOVEVHRVIgTk9UIE5VTEwgVU5JUVVFLHByb3Bvc2VyX2FjY291bnQgSU5URUdFUiBOT1QgTlVMTCxyZWNpcGllbnRfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLHByb3Bvc2VyX3Nlc3Npb24gVEVYVCBOT1QgTlVMTCxyZWNpcGllbnRfc2Vzc2lvbiBURVhUIE5PVCBOVUxMLGl0ZW1fdWlkIElOVEVHRVIgTk9UIE5VTEwsaXRlbV9qc29uIFRFWFQgTk9UIE5VTEwsY3JlYXRlZF9hdCBJTlRFR0VSIE5PVCBOVUxMLGRlc2NyaXB0b3IgQkxPQiBOT1QgTlVMTCknLCAnbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxJzogJ0NSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX2FjdGlvbnNfdjEob3BlcmF0aW9uIFRFWFQgUFJJTUFSWSBLRVkscmVxdWVzdF9oYXNoIFRFWFQgTk9UIE5VTEwsa2luZCBJTlRFR0VSIE5PVCBOVUxMLG93bmVyIElOVEVHRVIgTk9UIE5VTEwscGVlciBJTlRFR0VSIE5PVCBOVUxMLHBheWxvYWQgQkxPQiBOT1QgTlVMTCxwcm9wb3NhbCBURVhUIE5PVCBOVUxMLHN0YXR1cyBURVhUIE5PVCBOVUxMLGNyZWF0ZWRfYXQgSU5URUdFUiBOT1QgTlVMTCxiZWZvcmVfanNvbiBURVhUIE5PVCBOVUxMLGFmdGVyX2pzb24gVEVYVCBOT1QgTlVMTCknfQ0KZGVmIF9wcmVzZW50KGRiKToNCiBmb3VuZD1kaWN0KGRiLmV4ZWN1dGUoIlNFTEVDVCBuYW1lLHNxbCBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIobmFtZSkgSU4gKD8sPyw/LD8pIixUQUJMRVMpKQ0KIGlmIGZvdW5kIGFuZCBmb3VuZCE9U0NIRU1BUzpyYWlzZSBWYWx1ZUVycm9yKCdVbmtub3duIG9yIHBhcnRpYWwgY3VycmVudCBjb3VwbGUgc2NoZW1hJykNCiBpZiBkYi5leGVjdXRlKCJTRUxFQ1QgMSBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIodGJsX25hbWUpIElOICg/LD8sPyw/KSBBTkQodHlwZT0ndHJpZ2dlcidPUih0eXBlPSdpbmRleCdBTkQgc3FsIElTIE5PVCBOVUxMKSkgTElNSVQgMSIsVEFCTEVTKS5mZXRjaG9uZSgpOnJhaXNlIFZhbHVlRXJyb3IoJ1VucmV2aWV3ZWQgY291cGxlIHNjaGVtYSBleHRlbnNpb24nKQ0KIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmNvdXBsZV9jbG9zdXJlcyBpbXBvcnQgcHJlc2VudA0KIHByZXNlbnQoZGIsYmFzZT1ib29sKGZvdW5kKSkNCiByZXR1cm4gYm9vbChmb3VuZCkNCmRlZiBfc2NoZW1hKGRiKToNCiBpZiBfcHJlc2VudChkYik6cmV0dXJuDQogaWYgbm90IGRiLmluX3RyYW5zYWN0aW9uOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBzY2hlbWEgb3V0c2lkZSB3cml0ZXIgdHJhbnNhY3Rpb24nKQ0KIGZvciBzcWwgaW4gU0NIRU1BUy52YWx1ZXMoKTpkYi5leGVjdXRlKHNxbCkNCiBfcHJlc2VudChkYikNCmRlZiBfd3JpdGVfZ3VhcmQoZGIpOg0KICMgRXhhY3RseSB0aGUgaW52ZW50b3J5IGFuZCBtZXRhZGF0YSB0YWJsZXMgdG91Y2hlZCBieSBvcmlnaW5hbCByZW1vdmUoKS4NCiAjIEN1cnJlbnQgbmF0aXZlIHN0b3JhZ2UgZGVmaW5lcyBubyB0cmlnZ2VycyBvbiB0aGVzZSB3cml0ZXIgZGVwZW5kZW5jaWVzLg0KIHRhYmxlcz0oJ2ludmVudG9yeV9pdGVtcycsJ2VxdWlwbWVudF9hdHRyaWJ1dGVzJywnZXF1aXBtZW50X2R1cmFiaWxpdHknLCdlcXVpcG1lbnRfZW5oYW5jZW1lbnQnLCdpdGVtX2V4cGlyYXRpb24nLCdpdGVtX2xvY2tzJywnZXF1aXBtZW50X29wdGlvbnMnLCdlcXVpcG1lbnRfaWRlbnRpZmljYXRpb24nLCdlcXVpcG1lbnRfZW5oYW5jZW1lbnRfcHJvZ3Jlc3MnLCdpdGVtX3NlYWxzJywnYXJ0aWZhY3RfZXF1aXBtZW50X3N0YXRlJywnZXF1aXBtZW50X2NoaXBfdHVuaW5nJywnZXF1aXBtZW50X3JlZm9yZ2Vfc3RhdGVzJywnZXF1aXBtZW50X2VuZ3JhdmVfcHJldmlld3MnLCd3YXJkcm9iZV9pdGVtX3N0YXRlJywnd2FyZHJvYmVfZHllcycpDQogaWYgZGIuZXhlY3V0ZSgiU0VMRUNUIDEgRlJPTSBzcWxpdGVfbWFzdGVyIFdIRVJFIHR5cGU9J3RyaWdnZXInQU5EIGxvd2VyKHRibF9uYW1lKSBJTigiKycsJy5qb2luKCc/J2ZvciBfIGluIHRhYmxlcykrJykgTElNSVQgMScsdGFibGVzKS5mZXRjaG9uZSgpOnJhaXNlIFZhbHVlRXJyb3IoJ1VucmV2aWV3ZWQgY291cGxlIGludmVudG9yeSB3cml0ZXIgdHJpZ2dlcicpDQogX3ByZXNlbnQoZGIpDQpkZWYgX2FjdG9yKGRiLHVpZCxhY2NvdW50KToNCiByZXF1aXJlX2FjdGl2ZV9jaGFyYWN0ZXIoZGIsdWlkKTtyZXF1aXJlX293bmVyKGRiLHVpZCxhY2NvdW50KQ0KIHJvdz1kYi5leGVjdXRlKCdTRUxFQ1QgdWlkLG5hbWUsdW5pdF90eXBlIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKHVpZCwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG1pc3Npbmcgc2F2ZWQgY2hhcmFjdGVyJykNCiByZXR1cm4gZGljdCh6aXAoKCd1aWQnLCduYW1lJywndW5pdF90eXBlJykscm93KSkNCmRlZiBfZGlnZXN0KHVpZCxraW5kLHBheWxvYWQpOnJldHVybiBoYXNobGliLnNoYTI1NihzdHIodWlkKS5lbmNvZGUoKStiJzonK3N0cihraW5kKS5lbmNvZGUoKStiJzonK3BheWxvYWQpLmhleGRpZ2VzdCgpDQpkZWYgX2RlYml0KGJlZm9yZSxhZnRlcixpdGVtX3VpZCk6DQogaWYgbm90IGlzaW5zdGFuY2UoYmVmb3JlLGxpc3Qpb3Igbm90IGlzaW5zdGFuY2UoYWZ0ZXIsbGlzdClvciBhbnkobm90IGlzaW5zdGFuY2UoaSxkaWN0KWZvciBpIGluIGJlZm9yZSthZnRlcik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHNhdmVkIGludmVudG9yeSByZWNlaXB0IGFycmF5cycpDQogc291cmNlPW5leHQoKGkgZm9yIGkgaW4gYmVmb3JlIGlmIGlbJ3VpZCddPT1pdGVtX3VpZCksTm9uZSkNCiBpZiBzb3VyY2UgaXMgTm9uZSBvcihzb3VyY2VbJ3RlbXBsYXRlJ10sc291cmNlWydtZXRhZGF0YSddLHNvdXJjZVsnZ3JvdXAnXSkhPShSSU5HLDAsNClvciBzb3VyY2VbJ2NvdW50J108MTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb3JpZ2luYWwgcmluZyBzb3VyY2UgcmVjZWlwdCcpDQogZXhwZWN0ZWQ9W2RpY3QoaSlmb3IgaSBpbiBiZWZvcmVdDQogZm9yIGkgaW4gZXhwZWN0ZWQ6DQogIGlmIGlbJ3VpZCddPT1pdGVtX3VpZDppWydjb3VudCddLT0xDQogZXhwZWN0ZWQ9W2kgZm9yIGkgaW4gZXhwZWN0ZWQgaWYgaVsnY291bnQnXV0NCiBpZiBleHBlY3RlZCE9YWZ0ZXI6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11c3QgZGViaXQgZXhhY3RseSBvbmUgYm91bmQgcmluZycpDQogcmV0dXJuIHNvdXJjZQ0KZGVmIHNuYXBzaG90KGRiLG93bmVyLGFjY291bnQpOg0KIGlmIGRiLmV4ZWN1dGUoJ1NFTEVDVCBhY2NvdW50X2lkIEZST00gY2hhcmFjdGVyX293bmVycyBXSEVSRSB1aWQ9PycsKG93bmVyLCkpLmZldGNob25lKCkhPShhY2NvdW50LCk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNvbGQgb3duZXInKQ0KIGlmIG5vdCBfcHJlc2VudChkYik6cmV0dXJuIE5vbmUNCiBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5jb3VwbGVfY2xvc3VyZXMgaW1wb3J0IGNsb3NlZF9wYWlycw0KIGNsb3NlZD1jbG9zZWRfcGFpcnMoZGIsb3duZXIsYWNjb3VudCkNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIHBhaXJfaWQsYWNjb3VudF9pZCBGUk9NIG5hdGl2ZV9jb3VwbGVfbWVtYmVyc192MSBXSEVSRSBvd25lcj0/Jywob3duZXIsKSkuZmV0Y2hvbmUoKQ0KICMgRXZlcnkgZ2VuZXJhdGlvbiBpbnZvbHZpbmcgdGhpcyBvd25lciBtdXN0IHJldGFpbiBpdHMgdmFsaWRhdGVkIGltbXV0YWJsZQ0KICMgc291cmNlLCBpbmNsdWRpbmcgb2xkIGNsb3N1cmVzIHdoaWxlIGEgbGF0ZXIgcGFpciBpcyBhY3RpdmUuDQogcGFpcnM9e3ZbMF1mb3IgdiBpbiBkYi5leGVjdXRlKCdTRUxFQ1QgaWQgRlJPTSBuYXRpdmVfY291cGxlX3BhaXJzX3YxIFdIRVJFIGE9P09SIGI9PycsKG93bmVyLG93bmVyKSl9DQogaWYgcGFpcnMhPWNsb3NlZHwoe3Jvd1swXX1pZiByb3cgaXMgbm90IE5vbmUgZWxzZSBzZXQoKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHBhaXIgbGFja3MgbWVtYmVyIG9yIGV4YWN0IGNsb3N1cmUnKQ0KIGlmIHJvdyBpcyBOb25lOnJldHVybiBOb25lDQogaWYgcm93WzFdIT1hY2NvdW50IG9yIHJvd1swXWluIGNsb3NlZDpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbWVtYmVyIGFjY291bnQgb3IgY2xvc2VkIGdlbmVyYXRpb24nKQ0KIHJldHVybiBfcGFpcl9zbmFwc2hvdChkYixyb3dbMF0sb3duZXIsYWNjb3VudCkNCg0KZGVmIF9wYWlyX3NuYXBzaG90KGRiLHBhaXJfaWQsb3duZXIsYWNjb3VudCwqLGNsb3NlZD1GYWxzZSk6DQogcGFpcj1kYi5leGVjdXRlKCdTRUxFQ1QgYSxiLGFfYWNjb3VudCxiX2FjY291bnQsY3JlYXRlZF9hdCxwcm9wb3NhbCxhY2NlcHRhbmNlLGl0ZW1fdWlkLHZlcnNpb24gRlJPTSBuYXRpdmVfY291cGxlX3BhaXJzX3YxIFdIRVJFIGlkPT8nLChwYWlyX2lkLCkpLmZldGNob25lKCkNCiBpZiBwYWlyIGlzIE5vbmUgb3IgcGFpclstMV0hPTE6cmFpc2UgVmFsdWVFcnJvcignVW5rbm93biBjb3VwbGUgbWVtYmVyL3BhaXInKQ0KIGEsYixhYSxiYSxzdGFtcCxwcm9wb3NhbCxhY2NlcHRhbmNlLGl0ZW1fdWlkLHZlcnNpb249cGFpcg0KIGlmKG93bmVyLGFjY291bnQpbm90IGluKChhLGFhKSwoYixiYSkpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleGFjdCBwYWlyIG93bmVyL2FjY291bnQnKQ0KIG1lbWJlcnM9ZGIuZXhlY3V0ZSgnU0VMRUNUIG93bmVyLGFjY291bnRfaWQgRlJPTSBuYXRpdmVfY291cGxlX21lbWJlcnNfdjEgV0hFUkUgcGFpcl9pZD0/IE9SREVSIEJZIG93bmVyJywocGFpcl9pZCwpKS5mZXRjaGFsbCgpDQogaWYgbWVtYmVycyE9KFtdaWYgY2xvc2VkIGVsc2Ugc29ydGVkKFsoYSxhYSksKGIsYmEpXSkpb3IgYT09YiBvciBvd25lciBub3QgaW4oYSxiKW9yIHN0YW1wPD0wOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleGFjdGx5IHR3byByZWNpcHJvY2FsIG93bmVkIG1lbWJlcnMnKQ0KIGZvciB1aWQsYWlkIGluIHNvcnRlZChbKGEsYWEpLChiLGJhKV0pOg0KICBpZiBkYi5leGVjdXRlKCdTRUxFQ1QgYWNjb3VudF9pZCBGUk9NIGNoYXJhY3Rlcl9vd25lcnMgV0hFUkUgdWlkPT8nLCh1aWQsKSkuZmV0Y2hvbmUoKSE9KGFpZCwpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtZW1iZXIgYWNjb3VudCBjaGFuZ2VkJykNCiBhY3Rpb249ZGIuZXhlY3V0ZSgnU0VMRUNUIHJlcXVlc3RfaGFzaCxraW5kLG93bmVyLHBlZXIscGF5bG9hZCxwcm9wb3NhbCxzdGF0dXMsY3JlYXRlZF9hdCxiZWZvcmVfanNvbixhZnRlcl9qc29uIEZST00gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIFdIRVJFIG9wZXJhdGlvbj0/JywoYWNjZXB0YW5jZSwpKS5mZXRjaG9uZSgpDQogaWYgYWN0aW9uIGlzIE5vbmUgb3IgYWN0aW9uWzE6NF0hPSgweDNmZSxiLGEpb3IgYWN0aW9uWzU6OF0hPShwcm9wb3NhbCwnYWNjZXB0ZWQnLHN0YW1wKW9yIGFjdGlvblswXSE9X2RpZ2VzdChiLDB4M2ZlLGFjdGlvbls0XSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGxhY2tzIGltbXV0YWJsZSBleGFjdCBhY2NlcHRhbmNlIHByb2R1Y2VyJykNCiBwYXJzZWQ9YW5zd2VyX3JlcXVlc3QoYWN0aW9uWzRdKQ0KIGlmKHBhcnNlZFsnYW5zd2VyJ10scGFyc2VkWydwcm9wb3NlciddLHBhcnNlZFsncmVjaXBpZW50J10pIT0oMCxhLGIpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtdXR1YWwgYWNjZXB0YW5jZSBzb3VyY2UgaWRlbnRpdGllcycpDQogc291cmNlPV9kZWJpdChqc29uLmxvYWRzKGFjdGlvbls4XSksanNvbi5sb2FkcyhhY3Rpb25bOV0pLGl0ZW1fdWlkKQ0KIHByb3Bvc2VkPWRiLmV4ZWN1dGUoJ1NFTEVDVCBraW5kLG93bmVyLHBlZXIscGF5bG9hZCxzdGF0dXMscmVxdWVzdF9oYXNoLGJlZm9yZV9qc29uLGFmdGVyX2pzb24gRlJPTSBuYXRpdmVfY291cGxlX2FjdGlvbnNfdjEgV0hFUkUgb3BlcmF0aW9uPT8nLChwcm9wb3NhbCwpKS5mZXRjaG9uZSgpDQogaWYgcHJvcG9zZWQgaXMgTm9uZSBvciBwcm9wb3NlZFs6M10hPSgweDNmYixhLGIpb3IgcHJvcG9zZWRbNF0hPSdwcm9wb3NlZCdvciBwcm9wb3NlZFs1XSE9X2RpZ2VzdChhLDB4M2ZiLHByb3Bvc2VkWzNdKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbGFja3Mgb3JpZ2luYWwgcHJvcG9zYWwnKQ0KIGlmIHByb3Bvc2VfcmVxdWVzdChwcm9wb3NlZFszXSkhPXBhcnNlZFsnb3duX25hbWUnXW9yIGpzb24ubG9hZHMocHJvcG9zZWRbNl0pIT1bc291cmNlXW9yIHByb3Bvc2VkWzZdIT1wcm9wb3NlZFs3XTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3QgcHJvcG9zYWwgcmluZyBzb3VyY2UgY2hhbmdlZCcpDQogcGVlcj1iIGlmIG93bmVyPT1hIGVsc2UgYTtuYW1lPWRiLmV4ZWN1dGUoJ1NFTEVDVCBuYW1lIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKHBlZXIsKSkuZmV0Y2hvbmUoKQ0KIGlmIG5hbWUgaXMgTm9uZTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcGFydG5lciBjaGFyYWN0ZXIgdW5hdmFpbGFibGUnKQ0KIHJldHVybiBkaWN0KHBhaXJfaWQ9cGFpcl9pZCxraW5kPTEscGVlcl91aWQ9cGVlcixwZWVyX25hbWU9bmFtZVswXSxjcmVhdGVkX2F0PXN0YW1wKQ0KZGVmIF9yaW5nKGRiLG93bmVyLCosbm93LHVpZD1Ob25lKToNCiBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50DQogZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5pdGVtX2xvY2tzIGltcG9ydCByZXF1aXJlX3VubG9ja2VkDQogY2FuZGlkYXRlcz1baSBmb3IgaSBpbiBsb2FkX2l0ZW1zKGRiLG93bmVyKWlmKGlbJ3RlbXBsYXRlJ10saVsnbWV0YWRhdGEnXSxpWydncm91cCddKT09KFJJTkcsMCw0KWFuZCh1aWQgaXMgTm9uZSBvciBpWyd1aWQnXT09dWlkKV0NCiBmb3IgaXRlbSBpbiBzb3J0ZWQoY2FuZGlkYXRlcyxrZXk9bGFtYmRhIGk6KGlbJ3Nsb3QnXSxpWyd1aWQnXSkpOg0KICB0cnk6DQogICByZXF1aXJlX2N1cnJlbnQoaXRlbSxub3c9bm93KTtyZXF1aXJlX3VubG9ja2VkKGl0ZW0sbm93PW5vdykNCiAgIGlmIGl0ZW0uZ2V0KCdzZWFsZWQnLEZhbHNlKW9yIGl0ZW0uZ2V0KCdzZWFsX2NvdW50JywwKTpjb250aW51ZQ0KICAgcmV0dXJuIGl0ZW0NCiAgZXhjZXB0IFZhbHVlRXJyb3I6Y29udGludWUNCiByYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbmVlZHMgYSBjdXJyZW50IHVubG9ja2VkIG93bmVkMjY5NzEwJykNCmRlZiBfY2xvY2sobm93KToNCiBub3c9aW50KHRpbWUudGltZSgpKWlmIG5vdyBpcyBOb25lIGVsc2Ugbm93DQogaWYgdHlwZShub3cpaXMgbm90IGludCBvciBub3QgMDxub3c8MioqNjM6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHNlcnZlciBjbG9jaycpDQogcmV0dXJuIG5vdw0KZGVmIF9wcmV2aW91cyhkYixvcGVyYXRpb24sb3duZXIscGVlcixraW5kLHBheWxvYWQpOg0KIGlmIHR5cGUob3BlcmF0aW9uKWlzIG5vdCBzdHIgb3Igbm90IDE8PWxlbihvcGVyYXRpb24pPD0xNjA6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG9wZXJhdGlvbiBpZGVudGl0eScpDQogcm93PWRiLmV4ZWN1dGUoJ1NFTEVDVCByZXF1ZXN0X2hhc2gsb3duZXIscGVlcixraW5kLHN0YXR1cyxwcm9wb3NhbCBGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wZXJhdGlvbiwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIG5vdCBOb25lIGFuZCByb3dbOjRdIT0oX2RpZ2VzdChvd25lcixraW5kLHBheWxvYWQpLG93bmVyLHBlZXIsa2luZCk6cmFpc2UgVmFsdWVFcnJvcignQ29uZmxpY3RpbmcgY291cGxlIHJlcGxheScpDQogcmV0dXJuIHJvdw0KZGVmIHByb3Bvc2UoZGIsb3duZXIsYWNjb3VudCx0YXJnZXQsdGFyZ2V0X2FjY291bnQsc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbixwYXlsb2FkLG9wZXJhdGlvbiwqLGd1YXJkLGVuY29kZSxub3c9Tm9uZSk6DQogcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11dGF0aW9ucyBkaXNhYmxlZCBpbiBmcmVlLWZhcmV3ZWxsIGNvbXBhdGlibGUgcmVjb3ZlcnknKQ0KIG5vdz1fY2xvY2sobm93KTtfd3JpdGVfZ3VhcmQoZGIpO2d1YXJkKGRiKTthPV9hY3RvcihkYixvd25lcixhY2NvdW50KTtiPV9hY3RvcihkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpO2VsaWdpYmxlKGEsYikNCiBpZiBwcm9wb3NlX3JlcXVlc3QocGF5bG9hZCkhPWJbJ25hbWUnXTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb25saW5lIHRhcmdldCBuaWNrbmFtZScpDQogaWYgc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClpcyBub3QgTm9uZSBvciBzbmFwc2hvdChkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpaXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGFjdG9ycyBtdXN0IGJvdGggYmUgc29sbycpDQogX3NjaGVtYShkYik7b2xkPV9wcmV2aW91cyhkYixvcGVyYXRpb24sb3duZXIsdGFyZ2V0LDB4M2ZiLHBheWxvYWQpDQogaWYgb2xkIGlzIE5vbmU6DQogIHJpbmc9X3JpbmcoZGIsb3duZXIsbm93PW5vdykNCiAgcGVuZGluZz1kYi5leGVjdXRlKCdTRUxFQ1Qgb3BlcmF0aW9uLHByb3Bvc2VyLHJlY2lwaWVudCxwcm9wb3Nlcl9zZXNzaW9uLHJlY2lwaWVudF9zZXNzaW9uLGNyZWF0ZWRfYXQgRlJPTSBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEgV0hFUkUgcHJvcG9zZXIgSU4oPyw/KU9SIHJlY2lwaWVudCBJTig/LD8pJywob3duZXIsdGFyZ2V0LG93bmVyLHRhcmdldCkpLmZldGNoYWxsKCkNCiAgZm9yIG9wLHAsdCxwcyx0cyxjcmVhdGVkIGluIHBlbmRpbmc6DQogICBjdXJyZW50PXtvd25lcjpzZXNzaW9uLHRhcmdldDp0YXJnZXRfc2Vzc2lvbn0NCiAgIGlmIG5vdz5jcmVhdGVkKzEwIG9yIGFueSh1aWQgaW4gY3VycmVudCBhbmQgY3VycmVudFt1aWRdIT1zaWQgZm9yIHVpZCxzaWQgaW4oKHAscHMpLCh0LHRzKSkpOmRiLmV4ZWN1dGUoJ0RFTEVURSBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wLCkpDQogICBlbHNlOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBjdXJyZW50IHBlbmRpbmcgaW52aXRhdGlvbiBleGlzdHMnKQ0KICBkYi5leGVjdXRlKCdJTlNFUlQgSU5UTyBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEgVkFMVUVTKD8sPyw/LD8sPyw/LD8sPyw/LD8sPyknLChvcGVyYXRpb24sb3duZXIsdGFyZ2V0LGFjY291bnQsdGFyZ2V0X2FjY291bnQsc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbixyaW5nWyd1aWQnXSxqc29uLmR1bXBzKHJpbmcsc29ydF9rZXlzPVRydWUpLG5vdyxwYXlsb2FkKSkNCiAgb3JpZ2luYWxfcmluZz1qc29uLmR1bXBzKFtyaW5nXSxzb3J0X2tleXM9VHJ1ZSkNCiAgZGIuZXhlY3V0ZSgnSU5TRVJUIElOVE8gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIFZBTFVFUyg/LD8sPyw/LD8sPyw/LD8sPyw/LD8pJywob3BlcmF0aW9uLF9kaWdlc3Qob3duZXIsMHgzZmIscGF5bG9hZCksMHgzZmIsb3duZXIsdGFyZ2V0LHBheWxvYWQsb3BlcmF0aW9uLCdwcm9wb3NlZCcsbm93LG9yaWdpbmFsX3Jpbmcsb3JpZ2luYWxfcmluZykpDQogZWxzZToNCiAgaWYgb2xkWzQ6XSE9KCdwcm9wb3NlZCcsb3BlcmF0aW9uKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcHJvcG9zYWwgcmVjZWlwdCBzdGF0ZScpDQogIHJpbmc9X3JpbmcoZGIsb3duZXIsbm93PW5vdykNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIHByb3Bvc2VyX3Nlc3Npb24scmVjaXBpZW50X3Nlc3Npb24sY3JlYXRlZF9hdCxpdGVtX3VpZCxkZXNjcmlwdG9yIEZST00gbmF0aXZlX2NvdXBsZV9wZW5kaW5nX3YxIFdIRVJFIG9wZXJhdGlvbj0/Jywob3BlcmF0aW9uLCkpLmZldGNob25lKCkNCiBpZiByb3cgaXMgTm9uZSBvciByb3dbOjJdIT0oc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbilvciByb3dbMzpdIT0ocmluZ1sndWlkJ10scGF5bG9hZClvciBub3c+cm93WzJdKzEwOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleHBpcmVkIG9yIGNoYW5nZWQgcHJvcG9zYWwnKQ0KIGV2ZW50cz1lbmNvZGUoYSxiLEZhbHNlLCgpKQ0KIGZvciBlIGluIGV2ZW50czplbmNvZGVfZXZlbnQoZSkNCiBndWFyZChkYikNCiBfd3JpdGVfZ3VhcmQoZGIpDQogaWYgX2FjdG9yKGRiLG93bmVyLGFjY291bnQpIT1hIG9yIF9hY3RvcihkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpIT1iOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBsYXRlIGlkZW50aXR5IGNoYW5nZWQnKQ0KIHJldHVybiBldmVudHMNCmRlZiBhbnN3ZXIoZGIsb3duZXIsYWNjb3VudCxwZWVyLHBlZXJfYWNjb3VudCxzZXNzaW9uLHBlZXJfc2Vzc2lvbixwYXlsb2FkLG9wZXJhdGlvbiwqLGd1YXJkLGVuY29kZSxub3c9Tm9uZSk6DQogcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11dGF0aW9ucyBkaXNhYmxlZCBpbiBmcmVlLWZhcmV3ZWxsIGNvbXBhdGlibGUgcmVjb3ZlcnknKQ0KIG5vdz1fY2xvY2sobm93KTtfd3JpdGVfZ3VhcmQoZGIpO3BhcnNlZD1hbnN3ZXJfcmVxdWVzdChwYXlsb2FkKTtndWFyZChkYik7dGFyZ2V0PV9hY3RvcihkYixvd25lcixhY2NvdW50KTtwcm9wb3Nlcj1fYWN0b3IoZGIscGVlcixwZWVyX2FjY291bnQpO2VsaWdpYmxlKHByb3Bvc2VyLHRhcmdldCkNCiBpZihwYXJzZWRbJ3Byb3Bvc2VyJ10scGFyc2VkWydyZWNpcGllbnQnXSxwYXJzZWRbJ25hbWUnXSxwYXJzZWRbJ293bl9uYW1lJ10pIT0ocGVlcixvd25lcixwcm9wb3NlclsnbmFtZSddLHRhcmdldFsnbmFtZSddKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb3JpZ2luYWwgYW5zd2VyIGlkZW50aXRpZXMnKQ0KIGlmIG5vdCBfcHJlc2VudChkYik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG1pc3Npbmcgb3JpZ2luYWwgcHJvcG9zYWwgc2NoZW1hJykNCiBvbGQ9X3ByZXZpb3VzKGRiLG9wZXJhdGlvbixvd25lcixwZWVyLDB4M2ZlLHBheWxvYWQpDQogaWYgb2xkIGlzIG5vdCBOb25lOg0KICBzYXZlZD1zbmFwc2hvdChkYixvd25lcixhY2NvdW50KQ0KICBpZiBvbGRbNF09PSdhY2NlcHRlZCdhbmQgc2F2ZWQgaXMgbm90IE5vbmUgYW5kIHNhdmVkWydwYWlyX2lkJ109PW9wZXJhdGlvbiBhbmQgc2F2ZWRbJ3BlZXJfdWlkJ109PXBlZXI6DQogICBldmVudHM9ZW5jb2RlKHByb3Bvc2VyLHRhcmdldCxUcnVlLCgpKTtndWFyZChkYik7cmV0dXJuIGV2ZW50cw0KICBpZiBvbGRbNF09PSdyZWplY3RlZCc6ZXZlbnRzPWVuY29kZShwcm9wb3Nlcix0YXJnZXQsVHJ1ZSwoKSk7Z3VhcmQoZGIpO3JldHVybiBldmVudHMNCiAgcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHVua25vd24gYW5zd2VyIHJlY2VpcHQnKQ0KIGlmIHNuYXBzaG90KGRiLG93bmVyLGFjY291bnQpaXMgbm90IE5vbmUgb3Igc25hcHNob3QoZGIscGVlcixwZWVyX2FjY291bnQpaXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGFuc3dlciBhZnRlciByZWxhdGlvbiBjaGFuZ2VkJykNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIG9wZXJhdGlvbixwcm9wb3Nlcl9hY2NvdW50LHJlY2lwaWVudF9hY2NvdW50LHByb3Bvc2VyX3Nlc3Npb24scmVjaXBpZW50X3Nlc3Npb24saXRlbV91aWQsaXRlbV9qc29uLGNyZWF0ZWRfYXQsZGVzY3JpcHRvciBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBwcm9wb3Nlcj0/QU5EIHJlY2lwaWVudD0/JywocGVlcixvd25lcikpLmZldGNob25lKCkNCiBpZiByb3cgaXMgTm9uZSBvciByb3dbMTo1XSE9KHBlZXJfYWNjb3VudCxhY2NvdW50LHBlZXJfc2Vzc2lvbixzZXNzaW9uKW9yIG5vdz5yb3dbN10rMTAgb3Igcm93WzhdIT1fX2ltcG9ydF9fKCdlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcycsZnJvbWxpc3Q9WydkZXNjcmlwdG9yJ10pLmRlc2NyaXB0b3IodGFyZ2V0WyduYW1lJ10pOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBwZW5kaW5nIHNvdXJjZS9zZXNzaW9uL2RlYWRsaW5lJykNCiBzb3VyY2U9ZGIuZXhlY3V0ZSgnU0VMRUNUIGJlZm9yZV9qc29uLGFmdGVyX2pzb24scGF5bG9hZCxraW5kLG93bmVyLHBlZXIsc3RhdHVzLHJlcXVlc3RfaGFzaCBGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBXSEVSRSBvcGVyYXRpb249PycsKHJvd1swXSwpKS5mZXRjaG9uZSgpDQogaWYoc291cmNlIGlzIE5vbmUgb3Igc291cmNlWzBdIT1zb3VyY2VbMV1vciBqc29uLmxvYWRzKHNvdXJjZVswXSkhPVtqc29uLmxvYWRzKHJvd1s2XSldb3Igc291cmNlWzJdIT1yb3dbOF0NCiAgICBvciBzb3VyY2VbMzo3XSE9KDB4M2ZiLHBlZXIsb3duZXIsJ3Byb3Bvc2VkJylvciBzb3VyY2VbN10hPV9kaWdlc3QocGVlciwweDNmYixzb3VyY2VbMl0pKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcGVuZGluZyBsYWNrcyBleGFjdCBpbW11dGFibGUgcHJvcG9zYWwgcmluZyBwcm9kdWNlcicpDQogYmVmb3JlPWxvYWRfaXRlbXMoZGIscGVlcik7Y2hhbmdlcz1bXTtzdGF0dXM9J3JlamVjdGVkJw0KIGlmIHBhcnNlZFsnYW5zd2VyJ109PTA6DQogIHJpbmc9X3JpbmcoZGIscGVlcixub3c9bm93LHVpZD1yb3dbNV0pDQogIGlmIHJpbmchPWpzb24ubG9hZHMocm93WzZdKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcHJvcG9zYWwtYm91bmQgcmluZyBjaGFuZ2VkJykNCiAgaWYgcmluZ1snY291bnQnXT09MTpyZW1vdmUoZGIscGVlcixyaW5nKQ0KICBlbGlmIGRiLmV4ZWN1dGUoJ1VQREFURSBpbnZlbnRvcnlfaXRlbXMgU0VUIGNvdW50PWNvdW50LTEgV0hFUkUgb3duZXI9P0FORCB1aWQ9P0FORCBjb3VudD0/JywocGVlcixyaW5nWyd1aWQnXSxyaW5nWydjb3VudCddKSkucm93Y291bnQhPTE6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHJpbmcgZGViaXQgY2hhbmdlZCcpDQogIGFmdGVyPWxvYWRfaXRlbXMoZGIscGVlcik7X2RlYml0KGJlZm9yZSxhZnRlcixyaW5nWyd1aWQnXSk7cG9zaXRpb249KHJpbmdbJ2dyb3VwJ10scmluZ1snc2xvdCddKTtjaGFuZ2VzPVsocG9zaXRpb24sbmV4dCgoaSBmb3IgaSBpbiBhZnRlciBpZihpWydncm91cCddLGlbJ3Nsb3QnXSk9PXBvc2l0aW9uKSxOb25lKSldO3N0YXR1cz0nYWNjZXB0ZWQnDQogIGRiLmV4ZWN1dGUoJ0lOU0VSVCBJTlRPIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEgVkFMVUVTKD8sPyw/LD8sPyw/LD8sPyw/LDEpJywob3BlcmF0aW9uLHBlZXIsb3duZXIscGVlcl9hY2NvdW50LGFjY291bnQsbm93LHJvd1swXSxvcGVyYXRpb24scmluZ1sndWlkJ10pKQ0KICBkYi5leGVjdXRlbWFueSgnSU5TRVJUIElOVE8gbmF0aXZlX2NvdXBsZV9tZW1iZXJzX3YxIFZBTFVFUyg/LD8sPyknLCgocGVlcixwZWVyX2FjY291bnQsb3BlcmF0aW9uKSwob3duZXIsYWNjb3VudCxvcGVyYXRpb24pKSkNCiBlbHNlOmFmdGVyPWJlZm9yZQ0KIGRiLmV4ZWN1dGUoJ0lOU0VSVCBJTlRPIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBWQUxVRVMoPyw/LD8sPyw/LD8sPyw/LD8sPyw/KScsKG9wZXJhdGlvbixfZGlnZXN0KG93bmVyLDB4M2ZlLHBheWxvYWQpLDB4M2ZlLG93bmVyLHBlZXIscGF5bG9hZCxyb3dbMF0sc3RhdHVzLG5vdyxqc29uLmR1bXBzKGJlZm9yZSxzb3J0X2tleXM9VHJ1ZSksanNvbi5kdW1wcyhhZnRlcixzb3J0X2tleXM9VHJ1ZSkpKQ0KIGRiLmV4ZWN1dGUoJ0RFTEVURSBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBvcGVyYXRpb249PycsKHJvd1swXSwpKQ0KIGV2ZW50cz1lbmNvZGUocHJvcG9zZXIsdGFyZ2V0LEZhbHNlLGNoYW5nZXMpDQogZm9yIGUgaW4gZXZlbnRzOmVuY29kZV9ldmVudChlKQ0KIGd1YXJkKGRiKQ0KIGlmIHBhcnNlZFsnYW5zd2VyJ109PTA6DQogIGlmIGxvYWRfaXRlbXMoZGIscGVlcikhPWFmdGVyOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBpbnZlbnRvcnkgY2hhbmdlZCBhZnRlciBleGFjdCBkZWJpdCByZWNlaXB0JykNCiAgX2RlYml0KGJlZm9yZSxsb2FkX2l0ZW1zKGRiLHBlZXIpLHJvd1s1XSkNCiAgaWYgc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClbJ3BlZXJfdWlkJ10hPXBlZXIgb3Igc25hcHNob3QoZGIscGVlcixwZWVyX2FjY291bnQpWydwZWVyX3VpZCddIT1vd25lcjpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcmVjaXByb2NhbCBjb2xkIHNvdXJjZSBjaGFuZ2VkJykNCiBfd3JpdGVfZ3VhcmQoZGIpDQogaWYgX2FjdG9yKGRiLG93bmVyLGFjY291bnQpIT10YXJnZXQgb3IgX2FjdG9yKGRiLHBlZXIscGVlcl9hY2NvdW50KSE9cHJvcG9zZXI6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGxhdGUgc2F2ZWQgY2hhcmFjdGVyIGNoYW5nZWQnKQ0KIHJldHVybiBldmVudHMNCg==', 'size': 15544, 'sha256': 'ddb601d64ed6100187f945a34b997483f6198c9338fb9010ea032cc927d63e3c'}, 'els_server/storage/couple_closures.py': {'base64': 'IiIiRXhhY3QgbGF6eSBjbG9zdXJlIGxlZGdlciBmb3IgaHVtYW4tYXBwcm92ZWQgZnJlZSBjb3VwbGUxIGZhcmV3ZWxsLg0KT2xkIHBhaXIvYWNjZXB0YW5jZS9wcm9wb3NhbC9kZWJpdCBmYWN0cyByZW1haW4gaW1tdXRhYmxlOyBvbmx5IGFjdGl2ZSBtZW1iZXJzaGlwcw0KYXJlIHJlbW92ZWQuIE5vIEVEL2ludmVudG9yeS9yZWZ1bmQgd3JpdGVyIGFuZCBubyBndWVzc2VkIG1hcnJpYWdlIHBvbGljeS4NCiIiIg0KaW1wb3J0IGpzb24NCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlIGltcG9ydCByZWxhdGlvbnNoaXBzIGFzIHJlbA0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcyBpbXBvcnQgZmFyZXdlbGxfcmVxdWVzdA0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQNClRBQkxFPSduYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxJw0KUE9MSUNZPSdodW1hbi1mcmVlLWNvdXBsZTEtbm8tcmluZy1yZWZ1bmQtMjAyNjEwMjktdjEnDQpTQ0hFTUE9IkNSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxKHBhaXJfaWQgVEVYVCBQUklNQVJZIEtFWSBSRUZFUkVOQ0VTIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEoaWQpLG9wZXJhdGlvbiBURVhUIE5PVCBOVUxMIFVOSVFVRSxyZXF1ZXN0X2hhc2ggVEVYVCBOT1QgTlVMTCxvd25lciBJTlRFR0VSIE5PVCBOVUxMLGFjY291bnRfaWQgSU5URUdFUiBOT1QgTlVMTCxwZWVyIElOVEVHRVIgTk9UIE5VTEwscGVlcl9hY2NvdW50IElOVEVHRVIgTk9UIE5VTEwsY3JlYXRlZF9hdCBJTlRFR0VSIE5PVCBOVUxMLGZlZSBJTlRFR0VSIE5PVCBOVUxMIENIRUNLKGZlZT0wKSxyZWZ1bmQgSU5URUdFUiBOT1QgTlVMTCBDSEVDSyhyZWZ1bmQ9MCksYmVmb3JlX2pzb24gVEVYVCBOT1QgTlVMTCxhZnRlcl9qc29uIFRFWFQgTk9UIE5VTEwscGF5bG9hZCBCTE9CIE5PVCBOVUxMLHBvbGljeSBURVhUIE5PVCBOVUxMLHZlcnNpb24gSU5URUdFUiBOT1QgTlVMTCBDSEVDSyh2ZXJzaW9uPTEpKSINCg0KZGVmIGNhbm9uaWNhbCh2YWx1ZSk6cmV0dXJuIGpzb24uZHVtcHModmFsdWUsc29ydF9rZXlzPVRydWUsc2VwYXJhdG9ycz0oJywnLCc6JykpDQoNCmRlZiBwcmVzZW50KGRiLCosYmFzZT1UcnVlKToNCiBmb3VuZD1kaWN0KGRiLmV4ZWN1dGUoIlNFTEVDVCBuYW1lLHNxbCBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIobmFtZSk9PyIsKFRBQkxFLCkpKQ0KIGlmIGZvdW5kIGFuZChmb3VuZCE9e1RBQkxFOlNDSEVNQX1vciBub3QgYmFzZSk6cmFpc2UgVmFsdWVFcnJvcignVW5rbm93biBvciBvcnBoYW4gY291cGxlIGNsb3N1cmUgc2NoZW1hJykNCiBpZiBkYi5leGVjdXRlKCJTRUxFQ1QgMSBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIodGJsX25hbWUpPT9BTkQodHlwZT0ndHJpZ2dlcidPUih0eXBlPSdpbmRleCdBTkQgc3FsIElTIE5PVCBOVUxMKSkgTElNSVQgMSIsKFRBQkxFLCkpLmZldGNob25lKCk6cmFpc2UgVmFsdWVFcnJvcignVW5yZXZpZXdlZCBjb3VwbGUgY2xvc3VyZSBzY2hlbWEgZXh0ZW5zaW9uJykNCiByZXR1cm4gYm9vbChmb3VuZCkNCg0KZGVmIGluaXRpYWxpemUoZGIpOg0KIGlmIG5vdCBkYi5pbl90cmFuc2FjdGlvbjpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgY2xvc3VyZSBvdXRzaWRlIHdyaXRlciB0cmFuc2FjdGlvbicpDQogaWYgbm90IHJlbC5fcHJlc2VudChkYik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3N1cmUgcmVxdWlyZXMgb3JpZ2luYWwgYWNjZXB0ZWQgc2NoZW1hJykNCiBpZiBub3QgcHJlc2VudChkYik6ZGIuZXhlY3V0ZShTQ0hFTUEpDQogcHJlc2VudChkYikNCg0KZGVmIHBhaXJfcm93KGRiLHBhaXJfaWQpOg0KIHJvdz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBXSEVSRSBpZD0/JywocGFpcl9pZCwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignTWlzc2luZyBvcmlnaW5hbCBjb3VwbGUgcGFpcicpDQogcmV0dXJuIHJvdw0KDQpkZWYgcmVjZWlwdF9iZWZvcmUocGFpcixvd25lcixhY2NvdW50KToNCiByZXR1cm4gY2Fub25pY2FsKGRpY3QocGFpcj1saXN0KHBhaXIpLG1lbWJlcnM9c29ydGVkKFtbcGFpclsxXSxwYWlyWzNdLHBhaXJbMF1dLFtwYWlyWzJdLHBhaXJbNF0scGFpclswXV1dKSxhY3Rvcj1bb3duZXIsYWNjb3VudF0pKQ0KDQpkZWYgcmVjZWlwdF9hZnRlcihwYWlyX2lkKTpyZXR1cm4gY2Fub25pY2FsKGRpY3QocGFpcl9pZD1wYWlyX2lkLG1lbWJlcnM9W10sZmVlX0VEPTAscmluZ19yZWZ1bmQ9RmFsc2UpKQ0KDQpkZWYgY2hlY2tlZChkYixyb3cpOg0KIHBhaXJfaWQsb3BlcmF0aW9uLGRpZ2VzdCxvd25lcixhY2NvdW50LHBlZXIscGVlcl9hY2NvdW50LHN0YW1wLGZlZSxyZWZ1bmQsYmVmb3JlLGFmdGVyLHBheWxvYWQscG9saWN5LHZlcnNpb249cm93DQogcGFpcj1wYWlyX3JvdyhkYixwYWlyX2lkKQ0KIGlmKHR5cGUob3BlcmF0aW9uKWlzIG5vdCBzdHIgb3Igbm90IDE8PWxlbihvcGVyYXRpb24pPD0xNjAgb3IgcGF5bG9hZCE9Yicnb3IgZGlnZXN0IT1yZWwuX2RpZ2VzdChvd25lciwweDQxYyxwYXlsb2FkKQ0KICBvcihvd25lcixhY2NvdW50LHBlZXIscGVlcl9hY2NvdW50KW5vdCBpbigocGFpclsxXSxwYWlyWzNdLHBhaXJbMl0scGFpcls0XSksKHBhaXJbMl0scGFpcls0XSxwYWlyWzFdLHBhaXJbM10pKQ0KICBvciB0eXBlKHN0YW1wKWlzIG5vdCBpbnQgb3Igbm90IHBhaXJbNV08PXN0YW1wPDIqKjYzIG9yIGZlZSE9MCBvciByZWZ1bmQhPTAgb3IgcG9saWN5IT1QT0xJQ1kgb3IgdmVyc2lvbiE9MQ0KICBvciBiZWZvcmUhPXJlY2VpcHRfYmVmb3JlKHBhaXIsb3duZXIsYWNjb3VudClvciBhZnRlciE9cmVjZWlwdF9hZnRlcihwYWlyX2lkKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3N1cmUgaW1tdXRhYmxlIHNvdXJjZSByZWNlaXB0IGNoYW5nZWQnKQ0KIHJlbC5fcGFpcl9zbmFwc2hvdChkYixwYWlyX2lkLG93bmVyLGFjY291bnQsY2xvc2VkPVRydWUpDQogcmV0dXJuIHBhaXJfaWQNCg0KZGVmIGNsb3NlZF9wYWlycyhkYixvd25lcixhY2NvdW50KToNCiBpZiBub3QgcHJlc2VudChkYik6cmV0dXJuIHNldCgpDQogcm93cz1kYi5leGVjdXRlKCdTRUxFQ1QgYy4qRlJPTSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIGMgTEVGVCBKT0lOIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEgcCBPTiBwLmlkPWMucGFpcl9pZCBXSEVSRSBjLm93bmVyPT9PUiBjLnBlZXI9P09SIHAuYT0/T1IgcC5iPT8nLChvd25lcixvd25lcixvd25lcixvd25lcikpLmZldGNoYWxsKCkNCiByZXN1bHQ9c2V0KCkNCiBmb3Igcm93IGluIHJvd3M6DQogIGlkZW50PWNoZWNrZWQoZGIscm93KTtwYWlyPXBhaXJfcm93KGRiLGlkZW50KQ0KICBpZihvd25lcixhY2NvdW50KW5vdCBpbigocGFpclsxXSxwYWlyWzNdKSwocGFpclsyXSxwYWlyWzRdKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3NlZCBoaXN0b3J5IG93bmVyIGNoYW5nZWQnKQ0KICByZXN1bHQuYWRkKGlkZW50KQ0KIHJldHVybiByZXN1bHQNCg0KZGVmIHF1b3RlKGRiLG93bmVyLGFjY291bnQpOg0KIHNhdmVkPXJlbC5zbmFwc2hvdChkYixvd25lcixhY2NvdW50KQ0KIGlmIHNhdmVkIGlzIE5vbmUgb3Igc2F2ZWRbJ2tpbmQnXSE9MTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZXF1aXJlcyBjdXJyZW50IGNvdXBsZTEnKQ0KIHBhaXI9cGFpcl9yb3coZGIsc2F2ZWRbJ3BhaXJfaWQnXSk7cGVlcj1zYXZlZFsncGVlcl91aWQnXTtwZWVyX2FjY291bnQ9cGFpcls0XWlmIG93bmVyPT1wYWlyWzFdZWxzZSBwYWlyWzNdDQogb3RoZXI9cmVsLnNuYXBzaG90KGRiLHBlZXIscGVlcl9hY2NvdW50KQ0KIGlmIG90aGVyIGlzIE5vbmUgb3Iob3RoZXJbJ3BhaXJfaWQnXSxvdGhlclsncGVlcl91aWQnXSkhPShzYXZlZFsncGFpcl9pZCddLG93bmVyKTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZWNpcHJvY2FsIHBhaXIgY2hhbmdlZCcpDQogcmV0dXJuIGRpY3Qoc2F2ZWQsb3duZXI9b3duZXIsYWNjb3VudF9pZD1hY2NvdW50LHBlZXJfYWNjb3VudD1wZWVyX2FjY291bnQpDQoNCmRlZiBwZXJmb3JtKGRiLG93bmVyLGFjY291bnQscGF5bG9hZCxvcGVyYXRpb24sZXhwZWN0ZWQsKixndWFyZCxlbmNvZGUsbm93PU5vbmUpOg0KIHJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtdXRhdGlvbnMgZGlzYWJsZWQgaW4gZnJlZS1mYXJld2VsbCBjb21wYXRpYmxlIHJlY292ZXJ5JykNCiBmYXJld2VsbF9yZXF1ZXN0KHBheWxvYWQpDQogaWYgdHlwZShvcGVyYXRpb24paXMgbm90IHN0ciBvciBub3QgMTw9bGVuKG9wZXJhdGlvbik8PTE2MDpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgY2xvc3VyZSBvcGVyYXRpb24nKQ0KIGlmIG5vdCBkYi5pbl90cmFuc2FjdGlvbjpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZXF1aXJlcyBjYWxsZXIgd3JpdGVyJykNCiBndWFyZChkYik7cmVsLl93cml0ZV9ndWFyZChkYik7cmVsLl9hY3RvcihkYixvd25lcixhY2NvdW50KQ0KIGlmIHByZXNlbnQoZGIpOg0KICBwcmV2aW91cz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9jbG9zdXJlc192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wZXJhdGlvbiwpKS5mZXRjaG9uZSgpDQogIGlmIHByZXZpb3VzIGlzIG5vdCBOb25lOg0KICAgY2hlY2tlZChkYixwcmV2aW91cykNCiAgIGlmIHByZXZpb3VzWzM6NV0hPShvd25lcixhY2NvdW50KW9yIHByZXZpb3VzWzJdIT1yZWwuX2RpZ2VzdChvd25lciwweDQxYyxwYXlsb2FkKW9yIHJlbC5zbmFwc2hvdChkYixvd25lcixhY2NvdW50KWlzIG5vdCBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIHJlcGxheSBtZWV0cyBhbm90aGVyIHBhaXIgb3IgaWRlbnRpdHknKQ0KICAgYW5zd2VyPWVuY29kZShUcnVlKTtndWFyZChkYikNCiAgIGZvciBldmVudCBpbiBhbnN3ZXI6ZW5jb2RlX2V2ZW50KGV2ZW50KQ0KICAgcmV0dXJuIGFuc3dlcg0KIGFjdHVhbD1xdW90ZShkYixvd25lcixhY2NvdW50KQ0KIGlmIGFjdHVhbCE9ZXhwZWN0ZWQ6cmFpc2UgVmFsdWVFcnJvcignRmFyZXdlbGwgcXVvdGUgYmVsb25ncyB0byBhbm90aGVyIHBhaXIgZ2VuZXJhdGlvbicpDQogZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaW52ZW50b3J5X3N0YXRlIGltcG9ydCBsb2FkX2l0ZW1zDQogZGVmIGVjb25vbWljKCk6DQogIHJldHVybihbbG9hZF9pdGVtcyhkYix1aWQpZm9yIHVpZCBpbihvd25lcixhY3R1YWxbJ3BlZXJfdWlkJ10pXSxkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gcmV3YXJkX2JhbGFuY2VzIFdIRVJFIHVpZCBJTig/LD8pT1JERVIgQlkgdWlkJywob3duZXIsYWN0dWFsWydwZWVyX3VpZCddKSkuZmV0Y2hhbGwoKSkNCiBlY29ub215PWVjb25vbWljKCkNCiBzdGFtcD1yZWwuX2Nsb2NrKG5vdykNCiBpZiBzdGFtcDxhY3R1YWxbJ2NyZWF0ZWRfYXQnXTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCBwcmVjZWRlcyB0cnVlIHBhaXJpbmcnKQ0KIHBhaXI9cGFpcl9yb3coZGIsYWN0dWFsWydwYWlyX2lkJ10pO29sZF9wYWlycz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBPUkRFUiBCWSBpZCcpLmZldGNoYWxsKCk7b2xkX2FjdGlvbnM9ZGIuZXhlY3V0ZSgnU0VMRUNUICpGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBPUkRFUiBCWSBvcGVyYXRpb24nKS5mZXRjaGFsbCgpDQogaW5pdGlhbGl6ZShkYikNCiBkYi5leGVjdXRlKCdJTlNFUlQgSU5UTyBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIFZBTFVFUyg/LD8sPyw/LD8sPyw/LD8sPyw/LD8sPyw/LD8sMSknLChhY3R1YWxbJ3BhaXJfaWQnXSxvcGVyYXRpb24scmVsLl9kaWdlc3Qob3duZXIsMHg0MWMscGF5bG9hZCksb3duZXIsYWNjb3VudCxhY3R1YWxbJ3BlZXJfdWlkJ10sYWN0dWFsWydwZWVyX2FjY291bnQnXSxzdGFtcCwwLDAscmVjZWlwdF9iZWZvcmUocGFpcixvd25lcixhY2NvdW50KSxyZWNlaXB0X2FmdGVyKGFjdHVhbFsncGFpcl9pZCddKSxwYXlsb2FkLFBPTElDWSkpDQogaWYgZGIuZXhlY3V0ZSgnREVMRVRFIEZST00gbmF0aXZlX2NvdXBsZV9tZW1iZXJzX3YxIFdIRVJFIHBhaXJfaWQ9PycsKGFjdHVhbFsncGFpcl9pZCddLCkpLnJvd2NvdW50IT0yOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGV4YWN0bHkgdHdvIGFjdGl2ZSBtZW1iZXJzJykNCiBpZiByZWwuc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClpcyBub3QgTm9uZSBvciByZWwuc25hcHNob3QoZGIsYWN0dWFsWydwZWVyX3VpZCddLGFjdHVhbFsncGVlcl9hY2NvdW50J10paXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignRmFyZXdlbGwgYm90aCBjb2xkIHByb2plY3Rpb25zIG11c3QgYmUgc29sbycpDQogYW5zd2VyPWVuY29kZShGYWxzZSkNCiBmb3IgZXZlbnQgaW4gYW5zd2VyOmVuY29kZV9ldmVudChldmVudCkNCiBndWFyZChkYik7cmVsLl93cml0ZV9ndWFyZChkYikNCiBpZiBkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBPUkRFUiBCWSBpZCcpLmZldGNoYWxsKCkhPW9sZF9wYWlycyBvciBkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIE9SREVSIEJZIG9wZXJhdGlvbicpLmZldGNoYWxsKCkhPW9sZF9hY3Rpb25zOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGFsdGVyZWQgaW1tdXRhYmxlIHBhaXJpbmcvZGViaXQgc291cmNlJykNCiBpZiBlY29ub21pYygpIT1lY29ub215OnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIG11c3QgcHJlc2VydmUgYWxsIG93bmVkIFVJRCBpbnZlbnRvcnkgYW5kIEVEJykNCiBpZiBjaGVja2VkKGRiLGRiLmV4ZWN1dGUoJ1NFTEVDVCAqRlJPTSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIFdIRVJFIG9wZXJhdGlvbj0/Jywob3BlcmF0aW9uLCkpLmZldGNob25lKCkpIT1wYWlyWzBdOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGZpbmFsIGNsb3N1cmUgcmVjZWlwdCcpDQogcmV0dXJuIGFuc3dlcg0K', 'size': 7065, 'sha256': '4008884caac32d2e8d6393e15d095416015283c82c179c9a252925d1cc639dbe'}, 'els_server/storage/identification_ui.py': {'size': 5446, 'sha256': '9ff48abd45a634a2838a6e9efa1275a7537c655ab5901d66ae4e707c51b30555', 'base64': 'IiIiUmVzZXQgc2Nyb2xsIC0+IHVuaWRlbnRpZmllZCBpdGVtIC0+IHBhaWQtb25jZSBzY3JvbGwgYW5kIGZyZWUgaWRlbnRpZmljYXRpb24uIiIiCmltcG9ydCBzcWxpdGUzLHNlY3JldHMKZnJvbSBjb250ZXh0bGliIGltcG9ydCBjbG9zaW5nCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLnByb2Zlc3Npb25fc3RhdGUgaW1wb3J0IHJlcXVpcmVfb3duZXIKZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5pZGVudGlmaWNhdGlvbl91aSBpbXBvcnQgcmVxdWlyZV90ZW1wbGF0ZSxjYXRhbG9nLGRyYXdfaW5pdGlhbApmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50CmZyb20gZWxzX3NlcnZlci5kb21haW4uaXRlbV9sb2NrcyBpbXBvcnQgcmVxdWlyZV91bmxvY2tlZApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuaWRlbnRpZmljYXRpb25fbWVzc2FnZXMgaW1wb3J0IHJlcXVlc3QsYWNrbm93bGVkZ2VtZW50CmZyb20gZWxzX3NlcnZlci5wcm90b2NvbC5wcm90b2NvbF9jb2RlYyBpbXBvcnQgRXZlbnQKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaW52ZW50b3J5X2FjdGlvbnMgaW1wb3J0IF9pZGVudGl0eSxfcHJldmlvdXMsX2NvbW1pdApmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfc3RhdGUgaW1wb3J0IGxvYWRfaXRlbXMKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X3JlY2VpcHRfc3RhdGUgaW1wb3J0IGN1cnJlbnRfY2hhbmdlcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pdGVtX2luc3RhbmNlcyBpbXBvcnQgcmVtb3ZlCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLm5wY190cmFkZSBpbXBvcnQgYmFsYW5jZXMKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X29wdGlvbnMgaW1wb3J0IHJlcGxhY2UgYXMgcmVwbGFjZV9vcHRpb25zCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmVxdWlwbWVudF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgcmVwbGFjZSBhcyByZXBsYWNlX2lkZW50aWZpZWQKZGVmIHBlcmZvcm0ocGF0aCxvd25lcixraW5kLHBheWxvYWQsb3BlcmF0aW9uLHJhbmRiZWxvdz1zZWNyZXRzLnJhbmRiZWxvdywqLGFjY291bnRfaWQ9Tm9uZSxwcmVwYXJlPU5vbmUpOgogdWlkLG1hdGVyaWFsX3VpZD1yZXF1ZXN0KGtpbmQscGF5bG9hZCk7b3duZXIsZGlnZXN0PV9pZGVudGl0eShvd25lcixraW5kLHBheWxvYWQsb3BlcmF0aW9uKQogd2l0aCBjbG9zaW5nKHNxbGl0ZTMuY29ubmVjdChwYXRoLHRpbWVvdXQ9MTApKSBhcyBkYixkYjoKICBkYi5leGVjdXRlKCdQUkFHTUEgZm9yZWlnbl9rZXlzPU9OJyk7ZGIuZXhlY3V0ZSgnQkVHSU4gSU1NRURJQVRFJykKICBpZiBwcmVwYXJlIGlzIG5vdCBOb25lOnByZXBhcmUoKQogIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1fYWN0b3IgaW1wb3J0IHJlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcgogIHJlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcihkYixvd25lcikKICBpZiBhY2NvdW50X2lkIGlzIG5vdCBOb25lOnJlcXVpcmVfb3duZXIoZGIsb3duZXIsYWNjb3VudF9pZCkKICBvbGQ9X3ByZXZpb3VzKGRiLG9wZXJhdGlvbixkaWdlc3QpO2JlZm9yZT1sb2FkX2l0ZW1zKGRiLG93bmVyKTtlZD1iYWxhbmNlcyhkYixvd25lcilbJ2VkJ107YnlfdWlkPXtpWyd1aWQnXTppIGZvciBpIGluIGJlZm9yZX0KICBpZiBvbGQgaXMgbm90IE5vbmU6CiAgIGN1cnJlbnQ9eyhpWydncm91cCddLGlbJ3Nsb3QnXSk6aSBmb3IgaSBpbiBiZWZvcmV9CiAgIHJldHVybiBbRXZlbnQoMHgyMDEsa2luZD1raW5kKzEscGF5bG9hZD1hY2tub3dsZWRnZW1lbnQoa2luZCxlZCxjdXJyZW50X2NoYW5nZXMoZGIsb3BlcmF0aW9uLG93bmVyLGtpbmQsb2xkLGJlZm9yZSkpKV0KICBpdGVtPWJ5X3VpZC5nZXQodWlkKQogIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfZ2Vhcl9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkIGFzIGFjdGl2aXR5X3N1cHBvcnRlZCxkcmF3IGFzIGFjdGl2aXR5X2RyYXcKICBhY3Rpdml0eT1pdGVtIGlzIG5vdCBOb25lIGFuZCBhY3Rpdml0eV9zdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkKICBpZiBhY3Rpdml0eSBhbmQga2luZCE9MHg0Mzg6cmFpc2UgVmFsdWVFcnJvcignQWN0aXZpdHkgYXJtb3Igb3JkaW5hcnkgaW5pdGlhbCBpZGVudGlmaWNhdGlvbiBvbmx5JykKICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmFjY2Vzc29yeV9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkIGFzIGFjY2Vzc29yeV9zdXBwb3J0ZWQsZHJhdyBhcyBhY2Nlc3NvcnlfZHJhdwogIGFjY2Vzc29yeT1pdGVtIGlzIG5vdCBOb25lIGFuZCBhY2Nlc3Nvcnlfc3VwcG9ydGVkKGl0ZW1bJ3RlbXBsYXRlJ10pCiAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hY2Nlc3NvcnlfaWRlbnRpZmljYXRpb24gaW1wb3J0IHByb2ZpbGUgYXMgYWNjZXNzb3J5X3Byb2ZpbGUKICBpZiBhY2Nlc3NvcnkgYW5kIGFjY2Vzc29yeV9wcm9maWxlKGl0ZW1bJ3RlbXBsYXRlJ10paXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQWNjZXNzb3J5IGlkZW50aWZpY2F0aW9uIG1haW50ZW5hbmNlJykKICBpZiBhY2Nlc3Nvcnk6CiAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYWNjZXNzb3J5X2lkZW50aWZpY2F0aW9uIGltcG9ydCByZXNldF9zdXBwb3J0ZWQKICAgaWYgaXRlbVsnZ3JvdXAnXSE9MiBvciBraW5kPT0weDQzYSBhbmQgbm90IHJlc2V0X3N1cHBvcnRlZChpdGVtWyd0ZW1wbGF0ZSddKTpyYWlzZSBWYWx1ZUVycm9yKCdBY2Nlc3NvcnkgaWRlbnRpZmljYXRpb24gcmVxdWlyZXMgYW4gZWxpZ2libGUgYmFnIGl0ZW0nKQogIGlmIGl0ZW0gaXMgTm9uZSBvciBpdGVtWydjb3VudCddIT0xIG9yKGl0ZW1bJ2dyb3VwJ10hPTEgYW5kIG5vdCBhY2Nlc3NvcnkpOnJhaXNlIFZhbHVlRXJyb3IoJ093bmVkIHVuZXF1aXBwZWQgaWRlbnRpZmljYXRpb24gaXRlbSByZXF1aXJlZCcpCiAgcmVxdWlyZV90ZW1wbGF0ZShpdGVtWyd0ZW1wbGF0ZSddLHJlc2V0PWtpbmQ9PTB4NDNhKTtyZXF1aXJlX2N1cnJlbnQoaXRlbSk7cmVxdWlyZV91bmxvY2tlZChpdGVtKQogIGZyb20gZWxzX3NlcnZlci5kb21haW4uaWRlbnRpZmljYXRpb25fdWkgaW1wb3J0IGluaXRpYWxfcGVuZGluZwogIGZyb20gZWxzX3NlcnZlci5kb21haW4uaWRlbnRpZmljYXRpb25fdWkgaW1wb3J0IGNvbXBhdGliaWxpdHlfcHJvZmlsZQogIGlmIGNvbXBhdGliaWxpdHlfcHJvZmlsZShpdGVtWyd0ZW1wbGF0ZSddKWlzIG5vdCBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0NvbXBhdGliaWxpdHkgaWRlbnRpZmljYXRpb24gcmVjb3ZlcnkgZGVuaWVzIG5ldyBvcGVyYXRpb24nKQogIGlkZW50aWZpZWQ9aXRlbS5nZXQoJ2lkZW50aWZpZWQnLG5vdCBpbml0aWFsX3BlbmRpbmcoaXRlbSkpO3ByZXZpb3VzPWl0ZW0uZ2V0KCdvcHRpb25fZ3JvdXBzJyx7fSk7cG9zaXRpb25zPVsoaXRlbVsnZ3JvdXAnXSxpdGVtWydzbG90J10pXQogIGlmIGtpbmQ9PTB4NDNhOgogICBpZiBub3QgaWRlbnRpZmllZDpyYWlzZSBWYWx1ZUVycm9yKCdJdGVtIGlzIGFscmVhZHkgdW5pZGVudGlmaWVkJykKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkLHJlc2V0X3ZhbHVlcwogICByZXNldF9vcHRpb25zPXJlc2V0X3ZhbHVlcyhpdGVtWyd0ZW1wbGF0ZSddLHByZXZpb3VzLmdldCgnMScsW10pKSBpZiBzdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkgZWxzZSBbXQogICBtYXRlcmlhbD1ieV91aWQuZ2V0KG1hdGVyaWFsX3VpZCkKICAgaWYgbWF0ZXJpYWwgaXMgTm9uZSBvciBzdHIobWF0ZXJpYWxbJ3RlbXBsYXRlJ10pIG5vdCBpbiBjYXRhbG9nKClbJ21hdGVyaWFscyddOnJhaXNlIFZhbHVlRXJyb3IoJ093bmVkIG9yaWdpbmFsIHJlc2V0IHNjcm9sbCByZXF1aXJlZCcpCiAgIHJlcXVpcmVfY3VycmVudChtYXRlcmlhbCk7cmVxdWlyZV91bmxvY2tlZChtYXRlcmlhbCkKICAgaWYgbWF0ZXJpYWxbJ2NvdW50J109PTE6cmVtb3ZlKGRiLG93bmVyLG1hdGVyaWFsKQogICBlbHNlOmRiLmV4ZWN1dGUoJ1VQREFURSBpbnZlbnRvcnlfaXRlbXMgU0VUIGNvdW50PWNvdW50LTEgV0hFUkUgdWlkPT8gQU5EIG93bmVyPT8nLChtYXRlcmlhbF91aWQsb3duZXIpKQogICBwb3NpdGlvbnMuYXBwZW5kKChtYXRlcmlhbFsnZ3JvdXAnXSxtYXRlcmlhbFsnc2xvdCddKSk7dXBkYXRlZD17KipwcmV2aW91cywnMSc6cmVzZXRfb3B0aW9uc307ZmxhZz1GYWxzZQogIGVsc2U6CiAgIGlmIGlkZW50aWZpZWQ6cmFpc2UgVmFsdWVFcnJvcignSWRlbnRpZnkgcmVxdWlyZXMgYW4gdW5pZGVudGlmaWVkIGl0ZW0sIG5vdCBhIGZyZWUgcmVyb2xsJykKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkLGlkZW50aWZ5X3ZhbHVlcwogICB1cGRhdGVkPXsqKnByZXZpb3VzLCcxJzphY3Rpdml0eV9kcmF3KHJhbmRiZWxvdykgaWYgYWN0aXZpdHkgZWxzZSBhY2Nlc3NvcnlfZHJhdyhyYW5kYmVsb3csaXRlbVsndGVtcGxhdGUnXSkgaWYgYWNjZXNzb3J5IGVsc2UgaWRlbnRpZnlfdmFsdWVzKGl0ZW1bJ3RlbXBsYXRlJ10scHJldmlvdXMuZ2V0KCcxJyxbXSkscmFuZGJlbG93KSBpZiBzdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkgZWxzZSBkcmF3X2luaXRpYWwoaXRlbVsndGVtcGxhdGUnXSxyYW5kYmVsb3cpfTtmbGFnPVRydWUKICBpZiBraW5kPT0weDQzOCBhbmQgaXRlbVsndGVtcGxhdGUnXSBpbiAoMTY4OTE1LDE2ODkxNiwxNjg5MTcsMTY4OTE4KSBhbmQgbm90IHByZXZpb3VzLmdldCgnMzEnKToKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9jb252ZXJzaW9uIGltcG9ydCBkcmF3IGFzIGNvbnZlcnNpb25fZHJhdwogICB1cGRhdGVkWyczMSddPWNvbnZlcnNpb25fZHJhdyhbMCwwLDBdLHt9LHJhbmRiZWxvdykKICByZXBsYWNlX2lkZW50aWZpZWQoZGIsb3duZXIsdWlkLGlkZW50aWZpZWQsZmxhZyk7cmVwbGFjZV9vcHRpb25zKGRiLG93bmVyLHVpZCxwcmV2aW91cyx1cGRhdGVkKQogIGFmdGVyPWxvYWRfaXRlbXMoZGIsb3duZXIpO2N1cnJlbnQ9eyhpWydncm91cCddLGlbJ3Nsb3QnXSk6aSBmb3IgaSBpbiBhZnRlcn0KICB3aXJlPWFja25vd2xlZGdlbWVudChraW5kLGVkLFsocCxjdXJyZW50LmdldChwKSkgZm9yIHAgaW4gcG9zaXRpb25zXSkKICBldmVudD1FdmVudCgweDIwMSxraW5kPWtpbmQrMSxwYXlsb2FkPXdpcmUpCiAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICBlbmNvZGVfZXZlbnQoZXZlbnQpCiAgaWYgcHJlcGFyZSBpcyBub3QgTm9uZTpwcmVwYXJlKCkKICBfY29tbWl0KGRiLG9wZXJhdGlvbixkaWdlc3Qsb3duZXIsa2luZCxwb3NpdGlvbnMsYmVmb3JlLGFmdGVyKQogIHJldHVybiBbZXZlbnRdCg=='}, 'els_server/storage/fixed_cubes.py': {'size': 8973, 'sha256': 'eac5378c76e116cdfe6c004b78e32edc509a6a7da437b925fc4d30d8bce60880', 'base64': 'IiIiQ29uc3VtZSBvbmUgb3duZWQgZml4ZWQgY3ViZSBhbmQgZGVsaXZlciBpdHMgb3JpZ2luYWwgY29udGVudHMgYXRvbWljYWxseS4iIiIKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaXRlbV9hY3RvciBpbXBvcnQgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyCmltcG9ydCBzZWNyZXRzLHNxbGl0ZTMsc3RydWN0CmZyb20gY29udGV4dGxpYiBpbXBvcnQgY2xvc2luZwpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmN1YmVzIGltcG9ydCBjYXRhbG9nCmZyb20gZWxzX3NlcnZlci5kb21haW4uaW52ZW50b3J5X2l0ZW1zIGltcG9ydCBWRVJJRklFRF9URU1QTEFURVMsVEVNUExBVEVfQkFHX0dST1VQUwpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50CmZyb20gZWxzX3NlcnZlci5kb21haW4uaXRlbV9sb2NrcyBpbXBvcnQgcmVxdWlyZV91bmxvY2tlZApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuaWNlX21lc3NhZ2VzIGltcG9ydCB1c2VfcmVxdWVzdApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuY3ViZV9tZXNzYWdlcyBpbXBvcnQgcmVzdWx0CmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmludmVudG9yeV9zdGF0ZSBpbXBvcnQgbG9hZF9pdGVtcyxncmFudF9pdGVtcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfYWN0aW9ucyBpbXBvcnQgX2lkZW50aXR5LF9wcmV2aW91cyxfY29tbWl0CmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmludmVudG9yeV9tYW5hZ2VtZW50IGltcG9ydCBfdXBkYXRlcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ucGNfdHJhZGUgaW1wb3J0IGJhbGFuY2VzCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1faW5zdGFuY2VzIGltcG9ydCByZW1vdmUKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X3JlY2VpcHRfc3RhdGUgaW1wb3J0IGN1cnJlbnRfY2hhbmdlcwoKCmRlZiBfbGVnYWN5X2FjdG9yKGRiLG93bmVyLGFjY291bnRfaWQscHJlcGFyZSk6CiAgICBpZiBub3QgY2FsbGFibGUocHJlcGFyZSk6cmFpc2UgVmFsdWVFcnJvcignTGVnYWN5IGN1YmUgY3VycmVudCBzZWxlY3RlZCBhY3RvciBjYWxsYmFjayByZXF1aXJlZCcpCiAgICBwcmVwYXJlKGRiKQogICAgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyKGRiLG93bmVyKQogICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UucHJvZmVzc2lvbl9zdGF0ZSBpbXBvcnQgcmVxdWlyZV9vd25lcgogICAgcmVxdWlyZV9vd25lcihkYixvd25lcixhY2NvdW50X2lkKQoKCmRlZiBvcGVuX2N1YmUocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbixyYW5kYmVsb3c9c2VjcmV0cy5yYW5kYmVsb3csKixhY2NvdW50X2lkPU5vbmUscHJlcGFyZT1Ob25lKToKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uam9iX3Jld2FyZF9ib3hlcyBpbXBvcnQgQk9YRVMgYXMgam9iX2JveGVzCiAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZSBpbiBqb2JfYm94ZXM6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2Uuam9iX3Jld2FyZF9ib3hlcyBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbixhY2NvdW50X2lkPWFjY291bnRfaWQscHJlcGFyZT1wcmVwYXJlKQogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGU9PTcxNTAzNjoKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS53YXJkcm9iZV90aWNrZXRfYm94IGltcG9ydCBvcGVuX2JveAogICAgICAgIHJldHVybiBvcGVuX2JveChwYXRoLG93bmVyLHBheWxvYWQsb3BlcmF0aW9uLGFjY291bnRfaWQ9YWNjb3VudF9pZCkKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4ucHVibGlzaGVkXzIwMjZfYnVuZGxlcyBpbXBvcnQgZW5hYmxlZAogICAgZGVmaW5pdGlvbj1lbmFibGVkKCkuZ2V0KGV4cGVjdGVkX3RlbXBsYXRlKQogICAgaWYgZGVmaW5pdGlvbiBpcyBub3QgTm9uZToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5wdWJsaXNoZWRfMjAyNl9idW5kbGVzIGltcG9ydCBvcGVuX2J1bmRsZQogICAgICAgIHJldHVybiBvcGVuX2J1bmRsZShwYXRoLG93bmVyLHBheWxvYWQsb3BlcmF0aW9uLGRlZmluaXRpb249ZGVmaW5pdGlvbikKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl9mb3JjZV9yZXdhcmRzIGltcG9ydCBib3hlcyBhcyBmb3JjZV9ib3hlcwogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGUgaW4gZm9yY2VfYm94ZXMoKToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ib29zdGluZ18yMDI2X2ZvcmNlX3Jld2FyZHMgaW1wb3J0IG9wZW5fYm94CiAgICAgICAgcmV0dXJuIG9wZW5fYm94KHBhdGgsb3duZXIsZXhwZWN0ZWRfdGVtcGxhdGUscGF5bG9hZCxvcGVyYXRpb24pCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmJvb3N0aW5nXzIwMjZfcGFydGljaXBhdGlvbl9nZWFyIGltcG9ydCBCT1gsZW5hYmxlZCBhcyBnZWFyX2VuYWJsZWQKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlPT1CT1ggYW5kIGdlYXJfZW5hYmxlZCgpOgogICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmJvb3N0aW5nXzIwMjZfcGFydGljaXBhdGlvbl9nZWFyIGltcG9ydCBvcGVuX2dlYXIKICAgICAgICByZXR1cm4gb3Blbl9nZWFyKHBhdGgsb3duZXIscGF5bG9hZCxvcGVyYXRpb24sYWNjb3VudF9pZD1hY2NvdW50X2lkLHByZXBhcmU9cHJlcGFyZSkKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl9mYXNoaW9uX3Jld2FyZHMgaW1wb3J0IEJPWEVTLGVudHJpZXMgYXMgZmFzaGlvbl9lbnRyaWVzCiAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZSBpbiBCT1hFUyBhbmQgZmFzaGlvbl9lbnRyaWVzKCk6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuYm9vc3RpbmdfMjAyNl9mYXNoaW9uX3Jld2FyZHMgaW1wb3J0IG9wZW5fZmFzaGlvbgogICAgICAgIHJldHVybiBvcGVuX2Zhc2hpb24ocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbikKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl9uZXN0ZWRfY2FwYWNpdHkgaW1wb3J0IEJPWCBhcyBjYXBhY2l0eV9ib3gsaXRlbXMgYXMgY2FwYWNpdHlfaXRlbXMKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlPT1jYXBhY2l0eV9ib3ggYW5kIGNhcGFjaXR5X2l0ZW1zKCk6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuYm9vc3RpbmdfMjAyNl9uZXN0ZWRfY2FwYWNpdHkgaW1wb3J0IG9wZW5fYm94CiAgICAgICAgcmV0dXJuIG9wZW5fYm94KHBhdGgsb3duZXIscGF5bG9hZCxvcGVyYXRpb24pCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmJvb3N0aW5nXzIwMjZfdGl0bGVfcmV3YXJkcyBpbXBvcnQgQk9YIGFzIHRpdGxlX2JveCxlbmFibGVkIGFzIHRpdGxlX2VuYWJsZWQKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlPT10aXRsZV9ib3ggYW5kIHRpdGxlX2VuYWJsZWQoKToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ib29zdGluZ18yMDI2X3RpdGxlX3Jld2FyZHMgaW1wb3J0IG9wZW5fYm94CiAgICAgICAgcmV0dXJuIG9wZW5fYm94KHBhdGgsb3duZXIsZXhwZWN0ZWRfdGVtcGxhdGUscGF5bG9hZCxvcGVyYXRpb24pCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmJvb3N0aW5nXzIwMjZfYWNjZXNzb3JpZXMgaW1wb3J0IGJveGVzIGFzIGFjY2Vzc29yeV9ib3hlcwogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGUgaW4gYWNjZXNzb3J5X2JveGVzKCk6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuYm9vc3RpbmdfMjAyNl9hY2Nlc3NvcmllcyBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbikKICAgIHJlcXVlc3Q9dXNlX3JlcXVlc3QocGF5bG9hZCkKICAgIGlmIChhbnkodiBub3QgaW4gKDAsMSkgZm9yIHYgaW4gKHJlcXVlc3QuZmxhZzEscmVxdWVzdC5mbGFnMixyZXF1ZXN0LmZsYWczKSkKICAgICAgICBvciBleHBlY3RlZF90ZW1wbGF0ZSBub3QgaW4gY2F0YWxvZygpKTpyYWlzZSBWYWx1ZUVycm9yKCdVbnN1cHBvcnRlZCBmaXhlZCBjdWJlIHVzZScpCiAgICByb3c9Y2F0YWxvZygpW2V4cGVjdGVkX3RlbXBsYXRlXQogICAgIyBOYXRpdmUgc2VsZWN0aW9uIHF1YW50aXR5IFVJIHNlbmRzIENvdW50IGFzIHRoZSBmaW5hbCByZXF1ZXN0IG9wdGlvbi4KICAgICMgWmVybyBpcyB0aGUgaGlzdG9yaWNhbCBvbmUtYm94IHJvdXRlOyBvbmUgZXhwbGljaXRseSByZXF1ZXN0cyBvbmUgYm94LgogICAgIyBCdWxrIGNvdW50cyByZW1haW4gdW5zdXBwb3J0ZWQ6IG5ldmVyIGNvbnN1bWUgb25lIGZvciBhIGxhcmdlciByZXF1ZXN0LgogICAgaWYgcmVxdWVzdC5vcHRpb24hPTAgYW5kIG5vdChyZXF1ZXN0Lm9wdGlvbj09MSBhbmQgcm93WydzZWxlY3Rpb25fY291bnQnXT09MSk6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignVW5zdXBwb3J0ZWQgZml4ZWQgY3ViZSBxdWFudGl0eScpCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJlZ2lvbmFsX2Jvc3NfY3ViZXNfbGVnYWN5IGltcG9ydCBCT1hFUyxwb29sX2ZvcgogICAgbGVnYWN5PWV4cGVjdGVkX3RlbXBsYXRlIGluIEJPWEVTCiAgICBncm93aW5nPShleHBlY3RlZF90ZW1wbGF0ZT09MTY4ODg5IGFuZCByb3cuZ2V0KCdncm93aW5nX2FkdmVudHVyZV9raXQnKWlzIFRydWUpCiAgICBpZiByb3dbJ3NlbGVjdGlvbl9jb3VudCddOgogICAgICAgIGlmIGxlbihyZXF1ZXN0LmNob2ljZXMpIT0xOnJhaXNlIFZhbHVlRXJyb3IoJ1NlbGVjdCBleGFjdGx5IG9uZSBuYXRpdmUgY3ViZSBpdGVtJykKICAgICAgICBvdXRwdXQ9bmV4dCgoZSBmb3IgZSBpbiByb3dbJ2VudHJpZXMnXSBpZiBlWyd0ZW1wbGF0ZSddPT1yZXF1ZXN0LmNob2ljZXNbMF0pLE5vbmUpCiAgICAgICAgaWYgb3V0cHV0IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ2hvaWNlIGlzIG91dHNpZGUgdGhpcyBjdWJlJykKICAgIGVsc2U6CiAgICAgICAgaWYgcmVxdWVzdC5jaG9pY2VzOnJhaXNlIFZhbHVlRXJyb3IoJ0ZpeGVkIGN1YmUgZG9lcyBub3QgYWNjZXB0IGEgY2hvaWNlJykKICAgICAgICBvdXRwdXQ9Tm9uZSBpZiByb3cuZ2V0KCdyYW5kb20nKW9yIGdyb3dpbmcgZWxzZSByb3dbJ2VudHJpZXMnXVswXQogICAgb3duZXIsZGlnZXN0PV9pZGVudGl0eShvd25lciwweDE5NixzdHJ1Y3QucGFjaygnPmknLGV4cGVjdGVkX3RlbXBsYXRlKStwYXlsb2FkLG9wZXJhdGlvbikKICAgIHdpdGggY2xvc2luZyhzcWxpdGUzLmNvbm5lY3QocGF0aCx0aW1lb3V0PTEwKSkgYXMgZGIsZGI6CiAgICAgICAgZGIuZXhlY3V0ZSgnUFJBR01BIGZvcmVpZ25fa2V5cz1PTicpO2RiLmV4ZWN1dGUoJ0JFR0lOIElNTUVESUFURScpO3JlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcihkYixvd25lcikKICAgICAgICBpZiBsZWdhY3k6X2xlZ2FjeV9hY3RvcihkYixvd25lcixhY2NvdW50X2lkLHByZXBhcmUpCiAgICAgICAgaWYgZ3Jvd2luZzoKICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5ncm93aW5nX2FkdmVudHVyZV9raXQgaW1wb3J0IG91dHB1dHNfZm9yCiAgICAgICAgICAgIHJvbGU9ZGIuZXhlY3V0ZSgnU0VMRUNUIHVuaXRfY2xhc3MgRlJPTSBjaGFyYWN0ZXJzIFdIRVJFIHVpZD0/Jywob3duZXIsKSkuZmV0Y2hvbmUoKQogICAgICAgICAgICBpZiByb2xlIGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignR3Jvd2luZyBraXQgb3duZXIgbWlzc2luZycpCiAgICAgICAgICAgIGtpdF9vdXRwdXRzPW91dHB1dHNfZm9yKHJvbGVbMF0pCiAgICAgICAgb2xkPV9wcmV2aW91cyhkYixvcGVyYXRpb24sZGlnZXN0KTtiZWZvcmU9bG9hZF9pdGVtcyhkYixvd25lcik7YmFsYW5jZT1iYWxhbmNlcyhkYixvd25lcikKICAgICAgICBpZiBvbGQgaXMgbm90IE5vbmU6CiAgICAgICAgICAgIGV2ZW50cz1fdXBkYXRlcyhjdXJyZW50X2NoYW5nZXMoZGIsb3BlcmF0aW9uLG93bmVyLDB4MTk2LG9sZCxiZWZvcmUpKStyZXN1bHQoYmFsYW5jZVsnZWQnXSkKICAgICAgICAgICAgaWYgbGVnYWN5OgogICAgICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICAgICAgICAgICAgICAgIGZvciBldmVudCBpbiBldmVudHM6ZW5jb2RlX2V2ZW50KGV2ZW50KQogICAgICAgICAgICAgICAgX2xlZ2FjeV9hY3RvcihkYixvd25lcixhY2NvdW50X2lkLHByZXBhcmUpCiAgICAgICAgICAgIHJldHVybiBldmVudHMKICAgICAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZT09NzIyNTMxOnJhaXNlIFZhbHVlRXJyb3IoJ1NlbGVjdGlvbjcyMjUzMSBuZXcgb3BlcmF0aW9ucyBwYXVzZWQgaW4gcmVhZGVyLXByZXNlcnZpbmcgQ291bnQxIHJlY292ZXJ5JykKICAgICAgICBpdGVtPW5leHQoKGkgZm9yIGkgaW4gYmVmb3JlIGlmIGlbJ3VpZCddPT1yZXF1ZXN0LnVpZCksTm9uZSkKICAgICAgICBpZiBpdGVtIGlzIE5vbmUgb3IgaXRlbVsndGVtcGxhdGUnXSE9ZXhwZWN0ZWRfdGVtcGxhdGUgb3IgaXRlbVsnZ3JvdXAnXSE9NDoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignRml4ZWQgY3ViZSBkb2VzIG5vdCBtYXRjaCBvd25lZCBwcmV2aWV3ZWQgaW5zdGFuY2UnKQogICAgICAgIHJlcXVpcmVfY3VycmVudChpdGVtKTtyZXF1aXJlX3VubG9ja2VkKGl0ZW0pCiAgICAgICAgaWYgYmFsYW5jZVsncmV2aXNpb24nXT49MioqNjMtMTpyYWlzZSBWYWx1ZUVycm9yKCdGaXhlZCBjdWJlIHJldmlzaW9uIG92ZXJmbG93JykKICAgICAgICBpZiBsZWdhY3k6CiAgICAgICAgICAgIHJvbGU9ZGIuZXhlY3V0ZSgnU0VMRUNUIHVuaXRfdHlwZSx1bml0X2NsYXNzIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKG93bmVyLCkpLmZldGNob25lKCkKICAgICAgICAgICAgaWYgcm9sZSBpcyBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0xlZ2FjeSBjdWJlIG93bmVyIG1pc3NpbmcnKQogICAgICAgICAgICByb3c9cG9vbF9mb3Iocm93LCpyb2xlKQogICAgICAgIGlmIHJvdy5nZXQoJ3JhbmRvbScpOgogICAgICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJlZ2lvbmFsX2Jvc3NfY3ViZXMgaW1wb3J0IGRyYXcKICAgICAgICAgICAgb3V0cHV0PWRyYXcocm93LHJhbmRiZWxvdygxMDAwMCkpCiAgICAgICAgcmVnaW9uYWxfc291cmNlPU5vbmUKICAgICAgICBpZiBsZWdhY3k6CiAgICAgICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLnJlZ2lvbmFsX2Jvc3NfY3ViZV9zb3VyY2UgaW1wb3J0IF9Pd25lZEN1YmVTb3VyY2UKICAgICAgICAgICAgcmVnaW9uYWxfc291cmNlPV9Pd25lZEN1YmVTb3VyY2UoZGIsb3duZXIsaXRlbSxvdXRwdXQpCiAgICAgICAgc291cmNlPShpdGVtWydncm91cCddLGl0ZW1bJ3Nsb3QnXSkKICAgICAgICBpZiBpdGVtWydjb3VudCddPT0xOnJlbW92ZShkYixvd25lcixpdGVtKQogICAgICAgIGVsc2U6ZGIuZXhlY3V0ZSgnVVBEQVRFIGludmVudG9yeV9pdGVtcyBTRVQgY291bnQ9Y291bnQtMSBXSEVSRSB1aWQ9PyBBTkQgb3duZXI9PycsKGl0ZW1bJ3VpZCddLG93bmVyKSkKICAgICAgICBpZiByZWdpb25hbF9zb3VyY2UgaXMgbm90IE5vbmU6cmVnaW9uYWxfc291cmNlLmRlYml0X2NvbXBsZXRlKCkKICAgICAgICBvdXRwdXRzPWtpdF9vdXRwdXRzIGlmIGdyb3dpbmcgZWxzZShvdXRwdXQsKQogICAgICAgIHBsYW49W10KICAgICAgICBmb3Igc2VsZWN0ZWQgaW4gb3V0cHV0czoKICAgICAgICAgICAgcXVhbnRpdHk9c2VsZWN0ZWRbJ3F1YW50aXR5J10KICAgICAgICAgICAgd2hpbGUgcXVhbnRpdHk6CiAgICAgICAgICAgICAgICBkZWx0YT1taW4ocXVhbnRpdHksOTkpO3F1YW50aXR5LT1kZWx0YQogICAgICAgICAgICAgICAgcGxhbi5hcHBlbmQoZGljdCh0ZW1wbGF0ZT1zZWxlY3RlZFsndGVtcGxhdGUnXSxtZXRhZGF0YT1WRVJJRklFRF9URU1QTEFURVNbc2VsZWN0ZWRbJ3RlbXBsYXRlJ11dLAogICAgICAgICAgICAgICAgICAgIGdyb3VwPVRFTVBMQVRFX0JBR19HUk9VUFNbc2VsZWN0ZWRbJ3RlbXBsYXRlJ11dLHF1YW50aXR5PWRlbHRhKSkKICAgICAgICAgICAgICAgIGlmIGdyb3dpbmc6cGxhblstMV1bJ2VuaGFuY2VtZW50J109c2VsZWN0ZWRbJ2VuaGFuY2VtZW50J10KICAgICAgICBncmFudHM9Z3JhbnRfaXRlbXMoZGIscGxhbixvd25lcixyZWdpb25hbF9jdWJlX3NvdXJjZT1yZWdpb25hbF9zb3VyY2UpCiAgICAgICAgYWZ0ZXI9bG9hZF9pdGVtcyhkYixvd25lcik7Y3VycmVudD17KGlbJ2dyb3VwJ10saVsnc2xvdCddKTppIGZvciBpIGluIGFmdGVyfQogICAgICAgIHBvc2l0aW9ucz1zb3J0ZWQoe3NvdXJjZSwqWyhpWydncm91cCddLGlbJ3Nsb3QnXSkgZm9yIGkgaW4gZ3JhbnRzXX0pCiAgICAgICAgZXZlbnRzPXJlc3VsdChiYWxhbmNlWydlZCddLFsocCxjdXJyZW50LmdldChwKSkgZm9yIHAgaW4gcG9zaXRpb25zXSxbKHNlbGVjdGVkWyd0ZW1wbGF0ZSddLHNlbGVjdGVkWydxdWFudGl0eSddKWZvciBzZWxlY3RlZCBpbiBvdXRwdXRzXSkKICAgICAgICBpZiBncm93aW5nIG9yIGxlZ2FjeToKICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICAgICAgICAgICAgZm9yIGV2ZW50IGluIGV2ZW50czplbmNvZGVfZXZlbnQoZXZlbnQpCiAgICAgICAgZGIuZXhlY3V0ZSgnVVBEQVRFIHJld2FyZF9iYWxhbmNlcyBTRVQgcmV2aXNpb249cmV2aXNpb24rMSBXSEVSRSB1aWQ9PycsKG93bmVyLCkpCiAgICAgICAgX2NvbW1pdChkYixvcGVyYXRpb24sZGlnZXN0LG93bmVyLDB4MTk2LHBvc2l0aW9ucyxiZWZvcmUsYWZ0ZXIpCiAgICAgICAgaWYgbGVnYWN5Ol9sZWdhY3lfYWN0b3IoZGIsb3duZXIsYWNjb3VudF9pZCxwcmVwYXJlKQogICAgICAgIHJldHVybiBldmVudHMK'}}

def nine_raw_settle(workspace,psutil,j):
 import base64
 need(j.get('nine_recovery_schema')==1,'Nine-leaf recovery journal required')
 operation=Path(j['journal']).resolve().parent
 need(operation.is_relative_to(workspace/'state/local-updater'),'Recovery operation escaped')
 pointer_path=workspace/'releases/local/current.json';parent_pointer=j['parent']
 parent=under(workspace,parent_pointer['path'])
 need(sha(parent/'local-business-manifest.json')==parent_pointer['manifest_sha256'],'Recovery parent changed')
 current=read(pointer_path);candidate_pointer=j.get('candidate');guarded_pointer=j.get('nine_guarded_candidate')
 need(current==parent_pointer or current==candidate_pointer or current==guarded_pointer,'Recovery current changed externally')
 candidate=under(workspace,candidate_pointer['path'])if candidate_pointer else None
 if candidate is not None:
  need(candidate!=parent and candidate.is_relative_to(workspace/'releases/local')and candidate.name.startswith('local-git-'),'Recovery candidate path differs')
  stop_owned(candidate,workspace,psutil,operation/'nine-stop-candidate')
 stop_owned(parent,workspace,psutil,operation/'nine-stop-parent')
 doc,dbs,save=config_paths(parent,workspace);need(len(dbs)==2,'Both existing player databases required for recovery')
 port_idle(doc['port']);j['nine_safe_to_release']=False;atomic(operation/'journal.json',j)
 # Original stopped-service identity is an owned pre-update birth, never a
 # guessed process or a process selected only by executable name.
 stopped=operation/'stopped-service.json';old_service=read(stopped)if stopped.exists()else None
 restored=False
 with ExitStack()as stack:
  leases(parent,dbs,stack);state={str(p):dbdigest(p)for p in dbs}
  safe_parent=(candidate_pointer is None and current==parent_pointer and j.get('nine_writer_admission_opened')is False)or(j.get('nine_writer_admission_opened')is False and j.get('nine_database_before')==state and guarded_pointer is None)
  if safe_parent:
   need(read(pointer_path)==current,'Recovery pointer raced')
   atomic(pointer_path,parent_pointer);restored=True
   observation=operation/('nine-parent-observation-'+uuid.uuid4().hex[:8]);observation.mkdir()
   parent_proof=smoke(parent,save,observation,120)
   need(parent_proof['seconds']>=120 and {str(p):dbdigest(p)for p in dbs}==state,'Parent recovery observation changed data')
   restored_pointer,restored_root,restored_rows=local(workspace);need(restored_pointer==parent_pointer and restored_root==parent,'Parent recovery tree/current differs')
  else:
   need(candidate is not None,'Cannot discard unknown writes without complete new reader')
   payload={}
   for name,row in NINE_GUARD_PAYLOADS.items():
    raw=base64.b64decode(row['base64'],validate=True);need(len(raw)==row['size']and hashed(raw)==row['sha256']==REPAIR_RECOVERY_GUARDS[name],'Recovery guard changed');payload[name]=raw
   need(set(payload)==set(REPAIR_RECOVERY_GUARDS)and len(payload)==4,'All four exact guards required')
   snapshots=operation/'nine-reader-manifests';snapshots.mkdir(exist_ok=True)
   original={}
   for name in ('client-bundle-manifest.json','local-business-manifest.json','release-snapshot.json'):
    p=snapshots/name
    if not p.exists():
     temp=p.with_name(p.name+'.nine-snapshot-'+uuid.uuid4().hex+'.tmp')
     with temp.open('xb')as f:f.write((candidate/name).read_bytes());f.flush();os.fsync(f.fileno())
     os.replace(temp,p)
    original[name]=read(p)
   bundle=original['client-bundle-manifest.json'];rows=bundle['files'];by={r['path']:dict(r)for r in rows}
   need(len(by)==len(rows),'Duplicate recovery manifest members')
   business={r['path']:r for r in original['local-business-manifest.json']['files']}
   need(len(business)==1342 and set(REPAIR_REQUIRED_LEAVES)<=set(by),'Complete nine business reader required')
   for name,row in by.items():
    p=under(candidate,name);need(p.is_file(),'Missing recovery member: '+name)
    actual=sha(p)
    allowed={row['sha256']}|({REPAIR_RECOVERY_GUARDS[name]}if name in payload else set())
    need(actual in allowed and (actual!=row['sha256']or p.stat().st_size==row['size']),'Changed recovery member: '+name)
   for name,h in REPAIR_REQUIRED_LEAVES.items():
    need(by[name]['sha256']==h,'Candidate lost qualified nine source: '+name)
   flags=dict(recovery_only=True,compatible_read_only=False,complete_C3_reader_and_data=True,all_three_guards=True,
       selection_reader_compatible_recovery=True,all_five_selection_readers_retained=True,new_722531_operations_paused=True,
       player_database_restore=False,original_parent_code=False,guarded_paths=sorted(payload),source_business_files=1342,
       source_binding_sha256=REPAIR_SOURCE_SET)
   for name,raw in payload.items():
    p=under(candidate,name);temp=p.with_name(p.name+'.nine-guard-'+uuid.uuid4().hex+'.tmp')
    with temp.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temp,p)
    by[name]=dict(path=name,size=len(raw),sha256=hashed(raw))
   bd=dict(original['local-business-manifest.json']);bd.update(flags,files=[by[n]for n in sorted(business)])
   cb=dict(bundle);cb.update(flags,files=[by[n]for n in sorted(by)],file_count=len(by))
   atomic(candidate/'local-business-manifest.json',bd);atomic(candidate/'client-bundle-manifest.json',cb)
   rs=dict(original['release-snapshot.json']);rs.update(flags,status='nine-reader-compatible-guarded-recovery',local_business_manifest_sha256=sha(candidate/'local-business-manifest.json'));atomic(candidate/'release-snapshot.json',rs)
   guarded=dict(candidate_pointer);guarded.update(flags,manifest_sha256=sha(candidate/'local-business-manifest.json'),verified=False,installed=False,recovery_observation_complete=False)
   j['nine_guarded_candidate']=guarded;j['phase']='nine-reader-guard-ready';atomic(operation/'journal.json',j)
   need(read(pointer_path)==current,'Recovery pointer raced');atomic(pointer_path,guarded)
   observation=operation/('nine-reader-observation-'+uuid.uuid4().hex[:8]);observation.mkdir()
   proof=smoke(candidate,save,observation,120)
   need(proof['seconds']>=120 and {str(p):dbdigest(p)for p in dbs}==state,'Recovery changed player data')
   for name,row in by.items():need(under(candidate,name).stat().st_size==row['size']and sha(under(candidate,name))==row['sha256'],'Recovery tree changed')
   need(read(pointer_path)==guarded,'Guarded current changed')
   atomic(operation/'nine-reader-recovery.json',dict(ok=True,guarded=True,complete_new_reader_retained=True,database_restore=False,observation=proof,normal_startup_blocked=True,current=guarded))
 # Writer barrier closes before any parent restart. Guarded trees stay stopped;
 # a separately qualified forward repair is needed for normal startup.
 if restored:
  restarted=restart(parent,workspace,old_service,operation)
  if restarted:
   deadline=time.monotonic()+45
   while True:
    need(psutil.pid_exists(restarted['pid'])and time.monotonic()<deadline,'Restored parent did not become ready')
    try:
     with socket.create_connection(('127.0.0.1',doc['port']),timeout=1)as s:need(bool(s.recv(64)),'Restored parent not ready')
     break
    except OSError:time.sleep(.25)
  need(read(pointer_path)==parent_pointer,'Restored parent pointer changed')
  atomic(operation/'nine-reader-recovery.json',dict(ok=True,guarded=False,parent_restored_before_writer_admission=True,database_restore=False,observation=parent_proof))
 j['phase']='nine-parent-restored'if restored else'nine-reader-guarded';j['nine_safe_to_release']=True;atomic(operation/'journal.json',j)

def nine_recovery_entry(workspace,repo,target):
 # Only this exact interrupted nine transaction may enter recovery before the
 # generic floor/current-tree checks. Guarded normal updates remain forbidden.
 paths=[workspace/'analysis/coordination-20261015'/n for n in ('active-publication.lock','publication-record.lock')]
 present=[p for p in paths if p.exists()]
 if not present:return None
 identity=read(present[0])
 need(identity.get('schema')==SCHEMA and identity.get('operation')=='local-oneclick-updater'and all(read(p)==identity for p in present),'Unknown or mismatched recovery owner')
 journal=Path(identity['journal'])
 need(journal.is_absolute()and journal.resolve()==journal and journal.name=='journal.json'and journal.is_relative_to(workspace/'state/local-updater'),'Invalid nine recovery journal')
 for p in [journal,*journal.parents]:need(not p.is_symlink()and not p.is_junction(),'Linked nine recovery journal')
 j=read(journal)
 if j.get('nine_recovery_schema')!=1:return None
 need(j.get('schema')==SCHEMA and j.get('token')==identity['token']and j.get('created')==identity['created']and j.get('journal')==str(journal),'Nine recovery identity changed')
 need(j.get('repository')==str(repo)and j.get('target')==target and j.get('nine_source_binding_sha256')==REPAIR_SOURCE_SET,'Nine recovery source/journal binding differs')
 selected=json.loads(blob(repo,target,'channels/current-engine.json')or b'{}')
 need(selected.get('profile')==REPAIR_PROFILE and selected.get('accepted',{}).get('local')==dict(release=REPAIR_RELEASE,formal_manifest_sha256=REPAIR_FORMAL),'Nine recovery selected another cohort')
 raw=blob(repo,target,REPAIR_PROFILE);need(raw is not None and hashed(raw)==REPAIR_PROFILE_HASH,'Nine recovery profile bytes changed')
 current=read(workspace/'releases/local/current.json')
 need(current==j['parent']or current==j.get('candidate')or current==j.get('nine_guarded_candidate'),'Foreign current prevents nine recovery')
 parent=under(workspace,j['parent']['path']);need(parent.is_relative_to(workspace/'releases/local'),'Nine recovery parent escaped')
 need(sha(parent/'local-business-manifest.json')==j['parent']['manifest_sha256'],'Nine recovery parent manifest changed')
 rows=read(parent/'client-bundle-manifest.json')['files'];seen=set()
 for row in rows:
  name=row['path'];need(name not in seen and(not name.startswith('state/')or name=='state/friends-client.example.json'),'Recovery parent manifest contains state/duplicate');seen.add(name)
  p=under(parent,name);need(p.is_file()and p.stat().st_size==row['size']and sha(p)==row['sha256'],'Recovery parent member changed')
 # The psutil loader will use the unchanged retained parent, never a partially
 # guarded candidate. recover rechecks this exact identity and dead birth.
 return parent,identity,j

def recover(workspace,psutil,nine_identity=None,nine_journal=None):
 paths=[workspace/'analysis/coordination-20261015'/n for n in ('active-publication.lock','publication-record.lock')]
 present=[p for p in paths if p.exists()]
 if not present:return
 identity=read(present[0]);need(nine_identity is None or identity==nine_identity,'Nine recovery lock changed before admission');need(identity.get('schema')==SCHEMA and identity.get('operation')=='local-oneclick-updater','其他修复正在发布，请稍后重新点击更新')
 need(all(read(p)==identity for p in present),'发布锁所有者不一致，已保留现状')
 if psutil.pid_exists(identity['pid']):
  try:need(abs(psutil.Process(identity['pid']).create_time()-identity['created'])>.01,'另一个本地更新仍在运行')
  except psutil.NoSuchProcess:pass
 path=Path(identity['journal']).resolve();need(path.is_relative_to(workspace/'state/local-updater')and path.name=='journal.json','中断恢复记录路径无效')
 j=read(path)
 need(nine_identity is None or(j.get('nine_recovery_schema')==1 and nine_journal is not None and j==nine_journal),'Nine recovery journal changed before admission')
 if j.get('nine_recovery_schema')==1:
  need(j.get('schema')==SCHEMA and j.get('token')==identity['token'] and j.get('created')==identity['created'],'Nine recovery owner differs')
  if j.get('phase')=='complete' and j.get('nine_safe_to_release')is True:
   current,active,installed=local(workspace);need(current==j['candidate'],'Completed nine current changed');repair_candidate(active)
  else:nine_raw_settle(workspace,psutil,j)
  for p in present:need(read(p)==identity,'Recovery lock changed');p.unlink()
  return
 need('repair_recovery_schema' not in j and (j.get('candidate')or{}).get('source_release')!=REPAIR_RELEASE,'Managed Repair recovery must use its signed bootstrap; raw updater will not restore its parent')
 need(j.get('schema')==SCHEMA and j.get('token')==identity['token'],'中断恢复记录不匹配');idle(psutil)
 current=read(workspace/'releases/local/current.json');old=j['parent'];parent=under(workspace,old['path'])
 need(sha(parent/'local-business-manifest.json')==old['manifest_sha256'],'中断恢复父版校验失败')
 if j['phase']!='complete':
  candidate=j.get('candidate')
  if candidate and current==candidate:
   active=under(workspace,candidate['path']);stop_owned(active,workspace,psutil,path.parent);atomic(workspace/'releases/local/current.json',old)
  else:need(current==old,'本地版本已由其他操作变更，已保留现状')
  stopped=path.parent/'stopped-service.json'
  if stopped.exists():
   old_service=read(stopped);alive=False
   try:alive=abs(psutil.Process(old_service['pid']).create_time()-old_service['created'])<.01
   except psutil.NoSuchProcess:pass
   if alive and Path(old_service['stop']).exists():
    try:psutil.Process(old_service['pid']).wait(timeout=35);alive=False
    except psutil.NoSuchProcess:alive=False
    except psutil.TimeoutExpired:raise RuntimeError('中断操作的正常停服仍在进行，请稍后重试')
   if not alive:restart(parent,workspace,old_service,path.parent)
  j['phase']='interrupted-code-restored';atomic(path,j)
 for p in present:need(read(p)==identity,'中断恢复锁已变化');p.unlink()
 atomic(path.parent/'recovery.json',dict(ok=True,automatic=True,database_restore=False))

# Exact source floor for the independently qualified Repair cohort. This is
# downgrade prevention only; support fingerprints never prove acceptance.
REPAIR_RELEASE = 'local-accessory-identification-groups-20261030-v1'
REPAIR_FORMAL = '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'
REPAIR_PROFILE = 'channels/accessory-identification-accepted-20261031-v1.json'
REPAIR_PROFILE_HASH = '3f7002d2e2b5601d9ec2225bda47fc80b75646bea2cd22d29e8fcdcb3e9aab32'
REPAIR_SOURCE_ROWS = 'd7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999'
REPAIR_SOURCE_SET = '250a0581df1ca0cb945786c4cfb699b419997b66d24141fa9d02eb444d2ee2f8'
REPAIR_REQUIRED_LEAVES = {'els_server/data/identification_ui.json': 'c3e9be1f22a012b32826fd6ddeaa05bec8688fc6a7cd5b19a9259d860e9a0629', 'els_server/domain/accessory_identification.py': '2e2fc159879ca6810136521cc5519004645c67335f97198ff1b27fc3d151d0ca', 'els_server/domain/artifact_identification.py': '996c5783b362719e17764450bab5b1696e6d20226b59545e4cf597e15b48a89d', 'els_server/domain/boosting_gear_identification.py': '3b9935ee695012bbfac8ea61b9ac06378caae3da766f7a38bc6720532e15a662', 'els_server/domain/couple_farewell_flow.py': '14736e472dd8ed273c0ee16cd9f440d7eb488756656d6ff36fe08d8b6c783507', 'els_server/domain/equipment_instance.py': 'fdb108376b17dfcb182b46eea1ecf090e696dbff8b284456e0f9bb746498bbce', 'els_server/domain/identification_ui.py': '38f6fa5c6f92fa87b388092dfc64917c71616dba464c94f8e73f3a5ea6390f15', 'els_server/domain/local_session.py': '0edccc57a8c8f971a81066aea560b141f78ebe0223f7f14c41ada4bcac77f7a8', 'els_server/domain/relationship_flow.py': '53efb1f8a14b7f830dc08dcb1083907097c322f6b36878c0e698849a2a0b2e8d', 'els_server/domain/relationship_rules.py': 'f3652396d57a04703878d53d8c958283cb53915c7d94263bf38050c806d20716', 'els_server/domain/relationship_skills.py': '899ad73519a856b7402d6c1ba076d99f872f33ddd416647c4d15632a88936e4b', 'els_server/domain/relationship_visual_flow.py': '2bf589b3176035c8acd1d6de13267598ebdc5050709dd14070bcc251db89945f', 'els_server/domain/role_progression.py': '9379f185f237302c783625cde693fabd006866cd7a44af7880a5404738619efd', 'els_server/domain/session_dispatch.py': 'fdc74f164c2274c7f9b73dbea15641f69a2ca9728bc8e517d734be5f5867e2c2', 'els_server/domain/skill_rules.py': '98a63c448b4adbbb596181f54e83d42989a056202081a0f8b56fb844505abe17', 'els_server/protocol/local_messages.py': '7bd882e928b8143bc11438951ce140a514536bda27577a8bd7a6042367815151', 'els_server/protocol/relationship_messages.py': '64b08529362687948886079a45f816af8719ffcfcf54022ed4289453b544842f', 'els_server/storage/boosting_2026_force_equipment.py': '5eb9406d5b51bf15d58c47c2de6657c631079b7c1fc2b91839d827dbe97a8cbe', 'els_server/storage/careers.py': '60d919f36ac47ee724596f9c78d2fe7e689d6d62cbcb50bfecfb97c872e2c3c8', 'els_server/storage/characters.py': 'caa9d0677618854ac77a8f133a7b8014afc5227264b7132e3acae320c4d3209c', 'els_server/storage/couple_closures.py': '5c8920ed4c2f41dcd5a6d7e58d811495c6d070e3f7a10f649f5c7ac2e3339853', 'els_server/storage/identification_ui.py': '9e0668115954a6c5e98fea5e7295ce7bfacf8463ab07a52e4af18459ca700a55', 'els_server/storage/local_state.py': 'e5bdd9c7c9b053d06198a6732f6a7e8bcf4cac301f919f1faf92fd20f099e879', 'els_server/storage/manufacture.py': 'e2c241f9bfdb6eabcc9adf3217b7180b5fd068c627037d7899e106a48ae37de3', 'els_server/storage/master_presets.py': '7d6e688e18858fade9137ed0bbc6169e7a98942107f10f6996c5b6ce08ff241d', 'els_server/storage/ordinary_skill_pages.py': '1e3ebc90ce4543b52110f8337bd61666dbc1355c42989639637f3336cca089cc', 'els_server/storage/relationships.py': '0be8ce976e20571a1be7b0b9dcf02251934645bd2e39d14d3d94f3a40c86e42b', 'els_server/storage/titles.py': 'a4a57a2ab6b304f4f60739a47e4863200151dd4fe74defb5cb8fafe2e670f734', 'tools/client_compatibility_profiles.json': 'f1661177edd96176b2bd0b7e869215ab27e0337e186f77c1bd026248b2ae4a9e', 'tools/native_cache_sync.js': 'e2f86915262ba1ea1e919eb1b33c5f022e1a311bd267569bb02f3aee7368083a', 'tools/native_cache_sync.py': '225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856', 'els_server/domain/raid_reward_items.py': '847a7687d8ddc5a7405536eaa327d4e9bc66f337b9814975284f572e63eee7c0', 'els_server/domain/formal_pve_economy.py': 'd3f1ce62b59b61ab2fef348b510f1592509a41e706aa9868001f1deca95b5f5a', 'els_server/data/additional_magic_stones.json': '4d09c493ac6fde1bc7b5d7be774d09ab853b340f1d5152bca757e100e0e44907', 'els_server/data/select_cubes.json': '03d8b2d2a22a46ab1dfe2b3b5e128433e24f63ef24d6d8ac59d650d31de85077', 'els_server/data/select_cubes.manifest.json': '98052167a60091b7d8e9d7fcfeeac74dd2788e9667d62e129268ebdcf9720e00', 'els_server/data/select_cubes_owned_magic_native.json': '96362633694fbff9101ea02e55a320a84e9b3e60965521c71473cc84fad588cf', 'els_server/domain/additional_magic_stones.py': '20c65a204fec9ebdfe9265195d812e780b67665758841985d58891783944279c', 'els_server/domain/inventory_items.py': 'bb94e23b06684b9343951aee38b2709d3ef5a5cc7bcb92623b4f9e6528be0f9d', 'els_server/domain/select_cubes.py': '786ae0bbf968e7708881b1605f5442a4ed89b4389eba2e3e94184c83661f6ded', 'els_server/protocol/spell_socket_messages.py': '0cb94626a4fd80a087748f8785cf7acdd44134e45323cb92e0cdd46bf186d2a2', 'els_server/storage/fixed_cubes.py': '9d291013c158354df4189ced34097f3531827667b4f56cf4ac86ab852df60a14', 'els_server/data/accessory_identification_groups.json': '7770dc4d7d6de9bac6ad97a22d72fa7fe12774447af8f9fe4decf080cc0db2bc', 'els_server/domain/ordinary_accessories.py': 'cc61fd3839af72444c87983c66d05a9bae1ab39ad181e28bfcba131772e2438d', 'els_server/domain/character_custom.py': 'f6424155e2e9904d7aaa18b93c87ef205a922e5c264d9969f48ae4a8bcdc4968'}
REPAIR_SUPPORT = {'tools/client_compatibility_profiles.json': 'f1661177edd96176b2bd0b7e869215ab27e0337e186f77c1bd026248b2ae4a9e', 'tools/native_cache_sync.js': 'e2f86915262ba1ea1e919eb1b33c5f022e1a311bd267569bb02f3aee7368083a', 'tools/native_cache_sync.py': '225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856'}
REPAIR_RECOVERY_GUARDS = {'els_server/storage/relationships.py': 'ddb601d64ed6100187f945a34b997483f6198c9338fb9010ea032cc927d63e3c', 'els_server/storage/couple_closures.py': '4008884caac32d2e8d6393e15d095416015283c82c179c9a252925d1cc639dbe', 'els_server/storage/identification_ui.py': '9ff48abd45a634a2838a6e9efa1275a7537c655ab5901d66ae4e707c51b30555', 'els_server/storage/fixed_cubes.py': 'eac5378c76e116cdfe6c004b78e32edc509a6a7da437b925fc4d30d8bce60880'}

def repair_bindings():
 need(all(isinstance(v,str)and v for v in (REPAIR_RELEASE,REPAIR_PROFILE))and all(isinstance(v,str)and len(v)==64 and all(c in '0123456789abcdef'for c in v)for v in (REPAIR_FORMAL,REPAIR_PROFILE_HASH,REPAIR_SOURCE_ROWS,REPAIR_SOURCE_SET))and isinstance(REPAIR_REQUIRED_LEAVES,dict)and len(REPAIR_REQUIRED_LEAVES)==45 and isinstance(REPAIR_SUPPORT,dict)and len(REPAIR_SUPPORT)==3 and isinstance(REPAIR_RECOVERY_GUARDS,dict)and len(REPAIR_RECOVERY_GUARDS)==4,'Raw Repair bindings pending; stop before filesystem preparation')

def repair_marker():
 return dict(schema=1,source_release=REPAIR_RELEASE,source_formal_manifest_sha256=REPAIR_FORMAL,profile=REPAIR_PROFILE,profile_sha256=REPAIR_PROFILE_HASH,source_rows_sha256=REPAIR_SOURCE_ROWS,source_set_sha256=REPAIR_SOURCE_SET)

def repair_floor(pointer,parent,rows):
 repair_bindings();by={r['path']:r for r in rows}
 hit=any(name in by and by[name]['sha256']==h for name,h in REPAIR_SUPPORT.items())
 guarded=pointer.get('release')==REPAIR_RELEASE or 'repair_source_floor'in pointer or hit
 if not guarded:return False
 need(not any(name in by and by[name]['sha256']==h and sha(under(parent,name))==h for name,h in REPAIR_RECOVERY_GUARDS.items()),'Guarded C3 recovery cannot resume normal writes through a generic Git update; preserve the compatible reader and guards')
 if 'repair_source_floor'in pointer:need(pointer['repair_source_floor'] in (repair_marker(),{'schema': 1, 'source_release': 'local-owned-stones-nine-leaf-20261030-v1', 'source_formal_manifest_sha256': '965f336f1f5f940746eedf51c1c94f57c60abbdffc50e78c025e1da3d4ff3558', 'profile': 'channels/owned-stones-nine-leaf-accepted-20261030-v1.json', 'profile_sha256': '76bed17ea60a8c8aeeaef387fd5590aec838adecd07b4124d53cbab7a80309b6', 'source_rows_sha256': 'dbfc5f586a692e6acb240a1dd27ff29995893210550f5ecd8e7d3750a6dd0a41', 'source_set_sha256': 'a2b1ff7e286c4de294b9b4a50fd3be0400d3d22248fde686932c3b959b035647'},{'schema': 1, 'source_release': 'local-cache-exact41400-20261030-v1', 'source_formal_manifest_sha256': '7dd7cab0d08b85c9803e0c96d92109d4d5c2d22d729e47c0104d7f8e40d93b35', 'profile': 'channels/cache-exact41400-accepted-20261030-v1.json', 'profile_sha256': '951c6b5fbf13c6f7e9eda825c9d13e3e601b4bf8325f876dce04b572d6f08c2c', 'source_rows_sha256': 'bd405d403efec936c3a78a8a1a6eefb1a48debdbcd2f3c6b6e44b7c804430f6e', 'source_set_sha256': 'b23656c813133e79069eb34ca2653f830a6802eae4861b302070c5d28495d523'},{'schema': 1, 'source_release': 'local-native-shared-repair-20261030-v1', 'source_formal_manifest_sha256': '2291d8c2e24f72209e802de082fda701f623fc87609e201206136f5862ff9fd5', 'profile': 'channels/native-shared-repair-accepted-20261030-v1.json', 'profile_sha256': 'c63fbed4110c2b6a3f597d305c12971690fe78a6d00c4d2ecc285e039fe001ac', 'source_rows_sha256': '3e8430e117e2cc370801c06a7d62f54c10ee3fa4d4357ebccfc4f40231701947', 'source_set_sha256': '8ed8f297ea7f7bbaccb750985bf27302e38ca9ec00afa9f874c03f3cbff38adc'}),'Unknown raw Repair floor; a matching newer updater is required')
 need(all(name in by and by[name]['sha256']==h and sha(under(parent,name))==h for name,h in REPAIR_SUPPORT.items()),'Partial or different Repair support; preserve installed runtime')
 return True

def repair_source(repo,target,pointer,parent,rows):
 guarded=repair_floor(pointer,parent,rows)
 if not guarded:return False
 current=json.loads(blob(repo,target,'channels/current-engine.json')or b'{}');accepted=current.get('accepted',{}).get('local',{})
 need(current.get('profile')==REPAIR_PROFILE and accepted==dict(release=REPAIR_RELEASE,formal_manifest_sha256=REPAIR_FORMAL),'Installed Repair cannot be updated from an older or unknown Git cohort')
 raw=blob(repo,target,REPAIR_PROFILE);need(raw is not None and hashed(raw)==REPAIR_PROFILE_HASH,'Raw Repair exact Git profile differs')
 return True

def repair_candidate(root):
 for name,h in REPAIR_REQUIRED_LEAVES.items():need(under(root,name).is_file()and sha(under(root,name))==h,'Raw update would replace required C3 reader/guard/support: '+name)


def cache_profile_changes(repo,target,parent,installed):
 raw=blob(repo,target,REPAIR_PROFILE)
 need(raw is not None and hashed(raw)==REPAIR_PROFILE_HASH,'Exact nine-leaf profile bytes required')
 profile=json.loads(raw);entries=profile['channels']['local']['files'];by={r['path']:r for r in installed}
 need(len(entries)==1342 and len({r['path']for r in entries})==1342,'Exact LOCAL business row set required')
 # V45/V46 and already-current nine are the only source floors. Older/local
 # differences are never silently overlaid by these nine source locators.
 allowed_delta={'els_server/data/additional_magic_stones.json','els_server/data/select_cubes.json','els_server/data/select_cubes.manifest.json','els_server/data/select_cubes_owned_magic_native.json','els_server/domain/additional_magic_stones.py','els_server/domain/inventory_items.py','els_server/domain/select_cubes.py','els_server/protocol/spell_socket_messages.py','els_server/storage/fixed_cubes.py'}
 allowed_delta |= {'els_server/storage/identification_ui.py', 'els_server/domain/accessory_identification.py', 'els_server/domain/character_custom.py', 'els_server/domain/ordinary_accessories.py', 'els_server/data/accessory_identification_groups.json'}
 added={'els_server/data/select_cubes_owned_magic_native.json','els_server/data/accessory_identification_groups.json'};result={}
 for row in entries:
  name=row['path'];need(name in by or name in added,'Existing LOCAL parent is missing a formal member')
  same=name in by and (by[name]['size'],by[name]['sha256'])==(row['size'],row['sha256'])
  if same:continue
  need(name in allowed_delta,'Unexpected changed channel member; preserve LOCAL differences')
  source=row.get('source',name);under(Path(repo),source)
  data=blob(repo,target,source);need(data is not None and len(data)==row['size']and hashed(data)==row['sha256'],'Pinned archived source blob differs')
  need(row['sha256']==REPAIR_REQUIRED_LEAVES[name],'Unqualified nine-leaf source')
  result[name]=data
 need(not result or set(result)==allowed_delta or set(result)=={'els_server/storage/identification_ui.py', 'els_server/domain/accessory_identification.py', 'els_server/domain/character_custom.py', 'els_server/domain/ordinary_accessories.py', 'els_server/data/accessory_identification_groups.json'},'Partial accessory/nine-leaf upgrade refused')
 return result

def install(request,observation_seconds=120,fault=None):
 repair_bindings()
 workspace=Path(request['workspace']).resolve();repo=Path(request['repository']).resolve();target=request['commit'];client=Path(request['client']).resolve()
 queue=workspace/'analysis/user-issues-01a16dd4-20261024-v1/publish-queue-coordination-20261025-v1/status.json'
 if queue.exists():need(read(queue).get('release_queue_open')is True,'按已批准的维护顺序，正在等待当前修复完成；本地运行版和存档已保留')
 need(client.is_file(),'请选择已核客户端后再更新本地服务端')
 need(len(target)==40 and all(c in '0123456789abcdef'for c in target),'Git 提交号无效')
 need(gtext(repo,'rev-parse','HEAD')==target and not gtext(repo,'status','--porcelain','--untracked-files=all'),'Git 目录已变化，请重新点击更新')
 recovery_entry=nine_recovery_entry(workspace,repo,target)
 if recovery_entry is not None:
  recovery_parent,recovery_identity,recovery_journal=recovery_entry;recover(workspace,psutil_for(recovery_parent),nine_identity=recovery_identity,nine_journal=recovery_journal)
 progress(30,'正在核定本地父版与 Git 增量…');pointer,parent,rows=local(workspace);need(repair_source(repo,target,pointer,parent,rows)is True,'Nine updater requires the exact supported raw floor');psutil=psutil_for(parent);recover(workspace,psutil);pointer,parent,rows=local(workspace);guarded_repair=repair_source(repo,target,pointer,parent,rows);need(guarded_repair is True,'Nine updater cannot use generic legacy merge');idle(psutil)
 operation=workspace/'state/local-updater'/('update-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:10]);operation.mkdir(parents=True)
 j=dict(schema=SCHEMA,token=uuid.uuid4().hex,created=psutil.Process().create_time(),journal=str(operation/'journal.json'),phase='preparing',parent=pointer,repository=str(repo),target=target,player_database_restore=False);atomic(operation/'journal.json',j)
 base=pointer.get('source_git_commit')if pointer.get('source_repository')==str(repo)else None
 if base:need(len(base)==40 and gtext(repo,'merge-base','--is-ancestor',base,target)=='','已安装提交与上游发生分叉')
 else:base=initial_base(repo,target)
 if base==target and pointer.get('source_git_commit')==target:
  if guarded_repair:repair_candidate(parent)
  progress(100,'本地服务端已是此 Git 提交，无需重复安装。');return dict(ok=True,installed=True,already_current=True,release=pointer['release'],commit=target)
 changes=cache_profile_changes(repo,target,parent,rows)
 atomic(operation/'merge-plan.json',dict(base=base,target=target,files=sorted(changes),local_parent=pointer['release']))
 doc,dbs,save=config_paths(parent,workspace)
 candidate=workspace/'releases/local'/('local-git-'+target[:12]+'-'+uuid.uuid4().hex[:10]);need(not candidate.exists(),'候选目录已存在')
 progress(38,'正在构建独立本地候选，保留原配置和资源…');candidate.mkdir()
 try:
  for row in rows:
   src=under(parent,row['path']);dst=under(candidate,row['path']);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
  for name,raw in changes.items():
   dst=under(candidate,name)
   if raw is None:
    if dst.exists():dst.unlink()
   else:dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
  if guarded_repair:repair_candidate(candidate)
  manifests(candidate,parent,pointer,changes,base,target,repo)
  progress(47,'正在自动检查源码和两种启动依赖…');checks(candidate,client,operation)
  progress(55,'正在用存档备份副本验证服务启动…');proof=smoke(candidate,save,operation,min(3,observation_seconds));atomic(operation/'isolated-startup.json',proof)
  progress(70,'正在获取本地安装锁…');old_service=None;restarted=None;promoted=False
  j.update(nine_recovery_schema=1,nine_source_binding_sha256=REPAIR_SOURCE_SET,nine_safe_to_release=False,nine_writer_admission_opened=False);atomic(operation/'journal.json',j)
  with locks(workspace,j):
   if queue.exists():need(read(queue).get('release_queue_open')is True,'维护发布队列尚未开放，本地运行版已保留')
   need(read(workspace/'releases/local/current.json')==pointer,'本地父版已前进，已保留新版，请重新点击更新')
   if guarded_repair:repair_source(repo,target,pointer,parent,rows);repair_candidate(candidate)
   need(gtext(repo,'rev-parse','HEAD')==target and not gtext(repo,'status','--porcelain','--untracked-files=all'),'Git 目录在检查期间发生变化')
   idle(psutil);old_service=stop_owned(parent,workspace,psutil,operation)
   try:
    port_idle(doc['port'])
    with ExitStack()as stack:
     leases(parent,dbs,stack);progress(75,'正在备份账号、存档、代码、配置和任务…')
     backup=workspace/'releases/local/backups'/('before-'+candidate.name);backup.mkdir(parents=True)
     before={}
     for db in dbs:
      dst=backup/'databases'/db.relative_to(workspace);api_backup(db,dst);before[str(db)]=dbdigest(db)
     for name in ['local-business-manifest.json','client-bundle-manifest.json','release-snapshot.json','config/server.toml',*changes]:
      src=under(parent,name)
      if src.is_file():dst=under(backup/'code',name);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
     atomic(backup/'parent-pointer.json',pointer)
     task=command(['powershell','-NoProfile','-NonInteractive','-Command',"Get-ScheduledTask | Where-Object {$_.TaskName -match 'ELS|Elsword'} | Select-Object TaskName,TaskPath,State,Actions,Settings | ConvertTo-Json -Depth 8"],workspace,timeout=30);(backup/'scheduled-tasks.json').write_bytes(task.stdout)
     atomic(operation/'backup.json',dict(ok=True,database_backup_API=True,databases=before,backup=str(backup),old_runtime_retained=str(parent)))
     # Rehash immediately before promotion. Never trust the source checkout's
     # manifest to authorize changes to the installed runtime.
     local(workspace);candidate_rows=read(candidate/'client-bundle-manifest.json')['files']
     for row in candidate_rows:need(sha(under(candidate,row['path']))==row['sha256'],'候选在检查后发生变化')
     result=dict(ok=True,release=candidate.name,channel='local',path=candidate.relative_to(workspace).as_posix(),manifest_sha256=sha(candidate/'local-business-manifest.json'),parent_release=pointer['release'],parent_manifest_sha256=pointer['manifest_sha256'],source_git_commit=target,source_git_base=base,source_repository=str(repo),changed_runtime_files=sorted(changes),backup=str(backup),local_branch_preserved=True,client_delta=0,acceptance=str(operation/'completion.json'))
     if guarded_repair:result['repair_source_floor']=repair_marker()
     promoted_pointer=json.loads(json.dumps(result));j.update(phase='ready-to-promote',candidate=promoted_pointer,nine_database_before=before);atomic(operation/'journal.json',j)
     need(read(workspace/'releases/local/current.json')==pointer,'本地指针发生并发变化')
     progress(86,'正在原子安装本地服务端…');atomic(workspace/'releases/local/current.json',promoted_pointer);promoted=True
     j['phase']='promoted';atomic(operation/'journal.json',j)
     if fault:fault('after-promotion')
     progress(91,'正在核收安装结果和存档保护…')
     for row in candidate_rows:need(sha(under(candidate,row['path']))==row['sha256'],'安装后的候选摘要不匹配')
     observation=operation/'installed-observation';observation.mkdir()
     proof=smoke(candidate,save,observation,observation_seconds,tick=lambda elapsed:progress(93+min(5,int(5*elapsed/max(1,observation_seconds))),'正在观察已安装候选：'+str(elapsed)+' 秒，账号和存档保持保护…'))
     need(all(dbdigest(Path(p))==d for p,d in before.items()),'存档内容在安装期间发生变化')
     need(read(workspace/'releases/local/current.json')==promoted_pointer,'安装指针核收失败')
     atomic(candidate/'local-verification.json',dict(ok=True,isolated_startup=proof,database_backup_count=len(dbs),dual_database_backup_API=len(dbs)==2,player_databases_preserved=True,natural_gameplay=False))
    j['nine_writer_admission_opened']=True;atomic(operation/'journal.json',j)
    restarted=restart(candidate,workspace,old_service,operation)
    if restarted:
     deadline=time.monotonic()+45
     while True:
      need(psutil.pid_exists(restarted['pid'])and time.monotonic()<deadline,'本地服务重启失败')
      try:
       with socket.create_connection(('127.0.0.1',doc['port']),timeout=1)as s:need(bool(s.recv(64)),'本地服务未就绪')
       break
      except OSError:time.sleep(.25)
    result.update(observation_seconds=proof['seconds'],database_restore=False,installed=True,restarted_previous_service=old_service is not None)
    atomic(operation/'completion.json',result);j['phase']='complete';j['nine_safe_to_release']=True;atomic(operation/'journal.json',j)
   except BaseException:
    nine_raw_settle(workspace,psutil,j);raise
  progress(100,'本地服务端更新完成，账号和存档已保留。')
  return result
 except BaseException as error:
  atomic(operation/'failure.json',dict(ok=False,error=str(error),phase=j['phase'],player_database_restore=False,candidate=str(candidate),running_parent_preserved=j['phase']!='promoted'))
  if j.get('nine_safe_to_release')is True and candidate.exists()and read(workspace/'releases/local/current.json').get('path')!=candidate.relative_to(workspace).as_posix():
   need(candidate.resolve().is_relative_to(workspace/'releases/local')and candidate.name.startswith('local-git-'),'候选清理路径无效')
   in_use=False
   for process in psutil.process_iter(['cwd']):
    try:
     if process.info['cwd']and Path(process.info['cwd']).resolve().is_relative_to(candidate):in_use=True
    except psutil.Error:in_use=True
   if not in_use:shutil.rmtree(candidate)
  raise
def main():
 if len(sys.argv)>1 and sys.argv[1]=='--smoke':smoke_main(sys.argv[2:]);return
 parser=argparse.ArgumentParser();parser.add_argument('--request',required=True,type=Path);parser.add_argument('--result',required=True,type=Path);args=parser.parse_args()
 try:result=install(read(args.request));atomic(args.result,result)
 except BaseException as error:
  atomic(args.result,dict(ok=False,error=str(error),player_database_restore=False));progress(0,str(error));raise SystemExit(1)
if __name__=='__main__':main()
