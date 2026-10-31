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
  for p,inode in held.items():need(p.stat().st_ino==inode and read(p)==identity,'发布锁所有权发生变化');p.unlink()
def recover(workspace,psutil):
 paths=[workspace/'analysis/coordination-20261015'/n for n in ('active-publication.lock','publication-record.lock')]
 present=[p for p in paths if p.exists()]
 if not present:return
 identity=read(present[0]);need(identity.get('schema')==SCHEMA and identity.get('operation')=='local-oneclick-updater','其他修复正在发布，请稍后重新点击更新')
 need(all(read(p)==identity for p in present),'发布锁所有者不一致，已保留现状')
 if psutil.pid_exists(identity['pid']):
  try:need(abs(psutil.Process(identity['pid']).create_time()-identity['created'])>.01,'另一个本地更新仍在运行')
  except psutil.NoSuchProcess:pass
 path=Path(identity['journal']).resolve();need(path.is_relative_to(workspace/'state/local-updater')and path.name=='journal.json','中断恢复记录路径无效')
 j=read(path);need('repair_recovery_schema' not in j and (j.get('candidate')or{}).get('source_release')!=REPAIR_RELEASE,'Managed Repair recovery must use its signed bootstrap; raw updater will not restore its parent')
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
REPAIR_RELEASE = 'local-native-shared-repair-20261030-v1'
REPAIR_FORMAL = '2291d8c2e24f72209e802de082fda701f623fc87609e201206136f5862ff9fd5'
REPAIR_PROFILE = 'channels/native-shared-repair-accepted-20261030-v1.json'
REPAIR_PROFILE_HASH = 'c63fbed4110c2b6a3f597d305c12971690fe78a6d00c4d2ecc285e039fe001ac'
REPAIR_SOURCE_ROWS = '3e8430e117e2cc370801c06a7d62f54c10ee3fa4d4357ebccfc4f40231701947'
REPAIR_SOURCE_SET = '8ed8f297ea7f7bbaccb750985bf27302e38ca9ec00afa9f874c03f3cbff38adc'
REPAIR_REQUIRED_LEAVES = {'els_server/data/identification_ui.json': 'c3e9be1f22a012b32826fd6ddeaa05bec8688fc6a7cd5b19a9259d860e9a0629', 'els_server/domain/accessory_identification.py': 'a977c1985099bdee2d95fa1f58686fc1e098cf9542eb23555d13ac7ed3f45c15', 'els_server/domain/artifact_identification.py': '996c5783b362719e17764450bab5b1696e6d20226b59545e4cf597e15b48a89d', 'els_server/domain/boosting_gear_identification.py': '3b9935ee695012bbfac8ea61b9ac06378caae3da766f7a38bc6720532e15a662', 'els_server/domain/couple_farewell_flow.py': '14736e472dd8ed273c0ee16cd9f440d7eb488756656d6ff36fe08d8b6c783507', 'els_server/domain/equipment_instance.py': 'fdb108376b17dfcb182b46eea1ecf090e696dbff8b284456e0f9bb746498bbce', 'els_server/domain/identification_ui.py': '38f6fa5c6f92fa87b388092dfc64917c71616dba464c94f8e73f3a5ea6390f15', 'els_server/domain/local_session.py': '0edccc57a8c8f971a81066aea560b141f78ebe0223f7f14c41ada4bcac77f7a8', 'els_server/domain/relationship_flow.py': '53efb1f8a14b7f830dc08dcb1083907097c322f6b36878c0e698849a2a0b2e8d', 'els_server/domain/relationship_rules.py': 'f3652396d57a04703878d53d8c958283cb53915c7d94263bf38050c806d20716', 'els_server/domain/relationship_skills.py': '899ad73519a856b7402d6c1ba076d99f872f33ddd416647c4d15632a88936e4b', 'els_server/domain/relationship_visual_flow.py': '2bf589b3176035c8acd1d6de13267598ebdc5050709dd14070bcc251db89945f', 'els_server/domain/role_progression.py': '9379f185f237302c783625cde693fabd006866cd7a44af7880a5404738619efd', 'els_server/domain/session_dispatch.py': 'fdc74f164c2274c7f9b73dbea15641f69a2ca9728bc8e517d734be5f5867e2c2', 'els_server/domain/skill_rules.py': '98a63c448b4adbbb596181f54e83d42989a056202081a0f8b56fb844505abe17', 'els_server/protocol/local_messages.py': '7bd882e928b8143bc11438951ce140a514536bda27577a8bd7a6042367815151', 'els_server/protocol/relationship_messages.py': '64b08529362687948886079a45f816af8719ffcfcf54022ed4289453b544842f', 'els_server/storage/boosting_2026_force_equipment.py': '5eb9406d5b51bf15d58c47c2de6657c631079b7c1fc2b91839d827dbe97a8cbe', 'els_server/storage/careers.py': '60d919f36ac47ee724596f9c78d2fe7e689d6d62cbcb50bfecfb97c872e2c3c8', 'els_server/storage/characters.py': 'caa9d0677618854ac77a8f133a7b8014afc5227264b7132e3acae320c4d3209c', 'els_server/storage/couple_closures.py': '5c8920ed4c2f41dcd5a6d7e58d811495c6d070e3f7a10f649f5c7ac2e3339853', 'els_server/storage/identification_ui.py': '689460ee92bea8c8651061859788050414633026a659d537f319688a8a43a5e8', 'els_server/storage/local_state.py': 'e5bdd9c7c9b053d06198a6732f6a7e8bcf4cac301f919f1faf92fd20f099e879', 'els_server/storage/manufacture.py': 'e2c241f9bfdb6eabcc9adf3217b7180b5fd068c627037d7899e106a48ae37de3', 'els_server/storage/master_presets.py': '7d6e688e18858fade9137ed0bbc6169e7a98942107f10f6996c5b6ce08ff241d', 'els_server/storage/ordinary_skill_pages.py': '1e3ebc90ce4543b52110f8337bd61666dbc1355c42989639637f3336cca089cc', 'els_server/storage/relationships.py': '0be8ce976e20571a1be7b0b9dcf02251934645bd2e39d14d3d94f3a40c86e42b', 'els_server/storage/titles.py': 'a4a57a2ab6b304f4f60739a47e4863200151dd4fe74defb5cb8fafe2e670f734', 'tools/client_compatibility_profiles.json': 'f1661177edd96176b2bd0b7e869215ab27e0337e186f77c1bd026248b2ae4a9e', 'tools/native_cache_sync.js': 'e2f86915262ba1ea1e919eb1b33c5f022e1a311bd267569bb02f3aee7368083a', 'tools/native_cache_sync.py': '225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856'}
REPAIR_SUPPORT = {'tools/client_compatibility_profiles.json': 'f1661177edd96176b2bd0b7e869215ab27e0337e186f77c1bd026248b2ae4a9e', 'tools/native_cache_sync.js': 'e2f86915262ba1ea1e919eb1b33c5f022e1a311bd267569bb02f3aee7368083a', 'tools/native_cache_sync.py': '225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856'}
REPAIR_RECOVERY_GUARDS = {'els_server/storage/relationships.py': 'ddb601d64ed6100187f945a34b997483f6198c9338fb9010ea032cc927d63e3c', 'els_server/storage/couple_closures.py': '4008884caac32d2e8d6393e15d095416015283c82c179c9a252925d1cc639dbe', 'els_server/storage/identification_ui.py': '61572eed9833691e383a90de96813765e76093256b054c3d758fd472f9480f8d'}

def repair_bindings():
 need(all(isinstance(v,str)and v for v in (REPAIR_RELEASE,REPAIR_PROFILE))and all(isinstance(v,str)and len(v)==64 and all(c in '0123456789abcdef'for c in v)for v in (REPAIR_FORMAL,REPAIR_PROFILE_HASH,REPAIR_SOURCE_ROWS,REPAIR_SOURCE_SET))and isinstance(REPAIR_REQUIRED_LEAVES,dict)and len(REPAIR_REQUIRED_LEAVES)==31 and isinstance(REPAIR_SUPPORT,dict)and len(REPAIR_SUPPORT)==3 and isinstance(REPAIR_RECOVERY_GUARDS,dict)and len(REPAIR_RECOVERY_GUARDS)==3,'Raw Repair bindings pending; stop before filesystem preparation')

def repair_marker():
 return dict(schema=1,source_release=REPAIR_RELEASE,source_formal_manifest_sha256=REPAIR_FORMAL,profile=REPAIR_PROFILE,profile_sha256=REPAIR_PROFILE_HASH,source_rows_sha256=REPAIR_SOURCE_ROWS,source_set_sha256=REPAIR_SOURCE_SET)

def repair_floor(pointer,parent,rows):
 repair_bindings();by={r['path']:r for r in rows}
 hit=any(name in by and by[name]['sha256']==h for name,h in REPAIR_SUPPORT.items())
 guarded=pointer.get('release')==REPAIR_RELEASE or 'repair_source_floor'in pointer or hit
 if not guarded:return False
 need(not any(name in by and by[name]['sha256']==h and sha(under(parent,name))==h for name,h in REPAIR_RECOVERY_GUARDS.items()),'Guarded C3 recovery cannot resume normal writes through a generic Git update; preserve the compatible reader and guards')
 if 'repair_source_floor'in pointer:need(pointer['repair_source_floor']==repair_marker(),'Unknown raw Repair floor; a matching newer updater is required')
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

def install(request,observation_seconds=120,fault=None):
 repair_bindings()
 workspace=Path(request['workspace']).resolve();repo=Path(request['repository']).resolve();target=request['commit'];client=Path(request['client']).resolve()
 queue=workspace/'analysis/user-issues-01a16dd4-20261024-v1/publish-queue-coordination-20261025-v1/status.json'
 if queue.exists():need(read(queue).get('release_queue_open')is True,'按已批准的维护顺序，正在等待当前修复完成；本地运行版和存档已保留')
 need(client.is_file(),'请选择已核客户端后再更新本地服务端')
 need(len(target)==40 and all(c in '0123456789abcdef'for c in target),'Git 提交号无效')
 need(gtext(repo,'rev-parse','HEAD')==target and not gtext(repo,'status','--porcelain','--untracked-files=all'),'Git 目录已变化，请重新点击更新')
 progress(30,'正在核定本地父版与 Git 增量…');pointer,parent,rows=local(workspace);repair_source(repo,target,pointer,parent,rows);psutil=psutil_for(parent);recover(workspace,psutil);pointer,parent,rows=local(workspace);guarded_repair=repair_source(repo,target,pointer,parent,rows);idle(psutil)
 operation=workspace/'state/local-updater'/('update-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:10]);operation.mkdir(parents=True)
 j=dict(schema=SCHEMA,token=uuid.uuid4().hex,created=psutil.Process().create_time(),journal=str(operation/'journal.json'),phase='preparing',parent=pointer,repository=str(repo),target=target,player_database_restore=False);atomic(operation/'journal.json',j)
 base=pointer.get('source_git_commit')if pointer.get('source_repository')==str(repo)else None
 if base:need(len(base)==40 and gtext(repo,'merge-base','--is-ancestor',base,target)=='','已安装提交与上游发生分叉')
 else:base=initial_base(repo,target)
 if base==target and pointer.get('source_git_commit')==target:
  progress(100,'本地服务端已是此 Git 提交，无需重复安装。');return dict(ok=True,installed=True,already_current=True,release=pointer['release'],commit=target)
 changes=merge_changes(repo,base,target,parent,operation)
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
     j.update(phase='ready-to-promote',candidate=result);atomic(operation/'journal.json',j)
     need(read(workspace/'releases/local/current.json')==pointer,'本地指针发生并发变化')
     progress(86,'正在原子安装本地服务端…');atomic(workspace/'releases/local/current.json',result);promoted=True
     j['phase']='promoted';atomic(operation/'journal.json',j)
     if fault:fault('after-promotion')
     progress(91,'正在核收安装结果和存档保护…')
     for row in candidate_rows:need(sha(under(candidate,row['path']))==row['sha256'],'安装后的候选摘要不匹配')
     observation=operation/'installed-observation';observation.mkdir()
     proof=smoke(candidate,save,observation,observation_seconds,tick=lambda elapsed:progress(93+min(5,int(5*elapsed/max(1,observation_seconds))),'正在观察已安装候选：'+str(elapsed)+' 秒，账号和存档保持保护…'))
     need(all(dbdigest(Path(p))==d for p,d in before.items()),'存档内容在安装期间发生变化')
     need(read(workspace/'releases/local/current.json')==result,'安装指针核收失败')
     atomic(candidate/'local-verification.json',dict(ok=True,isolated_startup=proof,database_backup_count=len(dbs),dual_database_backup_API=len(dbs)==2,player_databases_preserved=True,natural_gameplay=False))
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
    atomic(operation/'completion.json',result);j['phase']='complete';atomic(operation/'journal.json',j)
   except BaseException:
    if restarted:
     Path(restarted['stop']).write_text(SCHEMA,'utf8')
     try:psutil.Process(restarted['pid']).wait(timeout=35)
     except psutil.NoSuchProcess:pass
    if promoted:
     need(read(workspace/'releases/local/current.json').get('release')==candidate.name,'外部已更新本地指针，不能覆盖恢复');atomic(workspace/'releases/local/current.json',pointer)
    restart(parent,workspace,old_service,operation);j['phase']='code-restored';atomic(operation/'journal.json',j);raise
  progress(100,'本地服务端更新完成，账号和存档已保留。')
  return result
 except BaseException as error:
  atomic(operation/'failure.json',dict(ok=False,error=str(error),phase=j['phase'],player_database_restore=False,candidate=str(candidate),running_parent_preserved=j['phase']!='promoted'))
  if candidate.exists()and read(workspace/'releases/local/current.json').get('path')!=candidate.relative_to(workspace).as_posix():
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
