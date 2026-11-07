"""Scoped signed LOCAL distribution. No game service or player DB operations."""
from pathlib import Path
import argparse,base64,copy,hashlib,importlib.util,json,os,shutil,subprocess,time,uuid
R=Path('G:/els');W=Path(__file__).parent;D=W/'launcher-v60';P=D/'publication';P.mkdir(exist_ok=True)
OWNER='01a1943c-ec8b-7bb0-9682-188ec0c84bb8';RELEASE='launcher-activities-startup-20261101-v60-v1';STAGE='C:/ELS-Launcher-Updates/staging/activities-startup-v60-v1';OLD=R/'analysis/all-ground-item-models-20261101-v1/launcher-v59';H=R/'analysis/qa60u'
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
transport=load('transport',R/'analysis/luciel-completion-01a14794-20261017/online-sync-v2/transport.py');jobs=load('jobs60',OLD.parent/'launcher_owned_process.py');jobs.RECEIPTS=P/'processes'
def remote(code,timeout=55):
 q=transport.run(code,timeout=timeout)
 if q.returncode:raise RuntimeError(q.stderr.decode('utf8','replace')[-3000:])
 return json.loads(q.stdout.decode('utf-8-sig'))
def run(args,label,cwd=None,timeout=240):
 q=jobs.run(list(map(str,args)),cwd=cwd,timeout=timeout);(P/(label+'.log')).write_bytes(q.stdout+q.stderr);return q
def definition(build,family):return json.loads(base64.b64decode(read(build['signed_bindings'][family]['manifest']['path'])['payload']))
def held():
 h=read(P/'reservation.json');assert h['identity']['thread']==OWNER
 for n,ino in h['inodes'].items():
  p=R/'analysis/coordination-20261015'/n;assert p.stat().st_ino==ino and read(p)==h['identity']
 for p,v in h['runtime_pins'].items():assert sha(p)==v,('Runtime drift',p)
 return h
def pre():
 b=read(D/'build.json');q=read(D/'qualification.json');assert q['ok']and q['exe_sha256']==b['exe_sha256']and q['build_sha256']==sha(D/'build.json')
 assert b['version']==60 and sha(b['exe'])==b['exe_sha256'];held()
 for family in ('signedLOCAL','signedFriends'):
  for ref in b['signed_bindings'][family].values():assert sha(ref['path'])==ref['sha256']
 return b
def reserve():
 assert not(D/'handoff-requested.json').exists(),'User requested handoff; this chat must not publish'
 assert not(P/'reservation.json').exists();b=read(D/'build.json');assert read(R/'releases/launchers/current.json')==b['parent']
 current=R/read(R/'releases/local/current.json')['path']
 for row in b['raw_delta']:assert sha(current/row['path'])==row['sha256'],'Selected gate dependency drift'
 names=('active-publication.lock','publication-record.lock');paths=[R/'analysis/coordination-20261015'/n for n in names];assert not any(p.exists()for p in paths),'Publication occupied; leave other owner intact'
 identity=dict(thread=OWNER,release=RELEASE,pid=os.getpid(),token=uuid.uuid4().hex,operation='signed LOCAL quest-gate distribution',directory=str(P));made=[]
 try:
  for p in paths:
   with p.open('x',encoding='utf8')as f:json.dump(identity,f)
   made.append(p)
 except BaseException:
  for p in made:
   assert read(p)==identity;p.unlink()
  raise
 runtime={str(R/'releases'/c/'current.json'):sha(R/'releases'/c/'current.json')for c in ('online','local')}
 save(P/'reservation.json',dict(identity=identity,inodes={p.name:p.stat().st_ino for p in paths},runtime_pins=runtime,launcher_parent={n:dict(path=str(R/'releases/launchers'/n),sha256=sha(R/'releases/launchers'/n))for n in ('current.json','standalone-current.json')}));pre();print('Reserved own launcher publication; no service stop',flush=True)
def stage():
 b=pre();h=held();assert all(sha(r['path'])==r['sha256']for r in h['launcher_parent'].values());assert read(R/'releases/launchers/current.json')==b['parent'];assert not(P/'stage.json').exists()
 inputs={b['latest']['file']:Path(b['exe'])}
 for family in ('signedLOCAL','signedFriends'):
  a=Path(b['signed_bindings'][family]['archive']['path']);inputs[a.name]=a
 pins={n:dict(size=p.stat().st_size,sha256=sha(p))for n,p in inputs.items()}
 remote("from pathlib import Path;import json;p=Path("+repr(STAGE)+");assert not p.exists();p.mkdir();print(json.dumps(dict(ok=True)))")
 for n,p in inputs.items():
  q=transport.scp(p,'Administrator@134.175.57.52:'+STAGE+'/'+n);assert q.returncode==0,q.stderr.decode(errors='replace');print('Uploaded '+n,flush=True)
 old=read(OLD/'build.json');oldhash={r['sha256']for family in ('signedLOCAL','signedFriends')for r in definition(old,family)['files']};adds={}
 for family in ('signedLOCAL','signedFriends'):
  d=definition(b,family)
  for r in d['files']:
   if r['sha256']not in oldhash:adds.setdefault(r['sha256'],dict(archive=d['archive']['file'],entry=r['path'],size=r['size']))
 assert len(adds)>4
 save(D/'index-additions.json',adds);q=transport.scp(D/'index-additions.json','Administrator@134.175.57.52:'+STAGE+'/index-additions.json');assert q.returncode==0
 code=r"""
from pathlib import Path
import base64,hashlib,json,os,shutil
R=Path('C:/ELS-Launcher-Updates');S=Path(STAGE);pins=PINS
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={n:dict(sha256=sha(R/n),size=(R/n).stat().st_size)for n in ('allowlist.json','components-index.json','public/latest.json')}
oldlatest=json.loads(base64.b64decode(json.loads((R/'public/latest.json').read_bytes())['payload']));assert oldlatest['version']==59 and oldlatest['sha256']==PARENT
backup=R/'backups/activities-startup-v60-v1';assert not backup.exists();backup.mkdir()
for n in before:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/n,p)
for n,row in pins.items():
 s=S/n;t=R/'public'/n;assert s.resolve()==s and t.resolve()==t and s.is_relative_to(S)
 assert s.stat().st_size==row['size']and sha(s)==row['sha256'];assert not t.exists();os.rename(s,t)
index=json.loads((R/'components-index.json').read_bytes());old=dict(index)
for k,v in json.loads((S/'index-additions.json').read_bytes()).items():
 if k in index:assert index[k]['size']==v['size']
 else:index[k]=v
assert all(index[k]==v for k,v in old.items())
allow=json.loads((R/'allowlist.json').read_bytes());oldallow=list(allow)
for n in pins:
 if n not in allow:allow.append(n)
for n,v in [('components-index.json',index),('allowlist.json',allow)]:
 t=S/(n+'.next');t.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8');os.replace(t,R/n)
assert sha(R/'public/latest.json')==before['public/latest.json']['sha256']
print(json.dumps(dict(ok=True,backup=str(backup),before=before,index_before=len(old),index_after=len(index),old_entries_preserved=True,latest_unchanged=True)))
""".replace('STAGE',repr(STAGE)).replace('PINS',repr(pins)).replace('PARENT',repr(b['parent']['sha256']))
 save(P/'stage.json',remote(code));print('Immutable public files staged; latest unchanged',flush=True)
def qualify_public():
 b=pre();assert read(P/'stage.json')['ok'];assert not H.exists();H.mkdir();owner=H/'p';owner.mkdir();nonce=uuid.uuid4().hex;save(H/'owner.json',dict(thread=OWNER,root=str(H),nonce=nonce));save(owner/'owner.json',dict(schema=1,kind='els-v45-reflection-prepare-v1',root=str(owner),nonce=nonce))
 repo=owner/'r';commit='b836a7dee8155bd33e0f91f4bf6803751bcd4aaa';run(['git','clone','--no-hardlinks','--dissociate','--no-checkout',W/'git-source',repo],'public-clone',timeout=180);run(['git','-C',repo,'checkout','--detach',commit],'public-checkout')
 template=(OLD/'public59-local.cs').read_text('utf8');reports=[];compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
 for label,build,mode in [('old59-public-seed',read(OLD/'build.json'),'offline'),('public60',b,'public'),('public60-repeat',b,'public')]:
  import re,zipfile
  t=template.replace('G:/els/analysis/mp59p',H.as_posix());t,n=re.subn(r'ExpectedExe="[a-f0-9]{64}"','ExpectedExe="'+build['exe_sha256']+'"',t);assert n==1;t,n=re.subn(r'NextPayload="[a-f0-9]{64}"','NextPayload="'+build['signed_bindings']['signedLOCAL']['archive']['sha256']+'"',t);assert n==1
  assert t.count('==59,')==1;t=t.replace('==59,','=='+str(build['version'])+',')
  assert t.count('next?1887:')==1;t=t.replace('next?1887:','next?'+str(len(definition(build,'signedLOCAL')['files']))+':')
  with zipfile.ZipFile(build['signed_bindings']['signedLOCAL']['archive']['path'])as z:meta=json.loads(z.read('local-bootstrap-source.json'))
  assert t.count('local-git-first-run-registered-ground-items-20261101-v1')==1;t=t.replace('local-git-first-run-registered-ground-items-20261101-v1',meta['release'])
  cs=D/(label+'.cs');cs.write_text(t,encoding='utf8');exe=cs.with_suffix('.exe');run([compiler,'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],label+'-compile')
  ref=build['signed_bindings']['signedLOCAL'];run([exe,build['exe'],build['exe_sha256'],ref['archive']['path'],ref['archive']['sha256'],repo,commit,'accessory',owner,nonce,label,mode,'components'],label,timeout=300);r=read(owner/'results'/(label+'.json'));assert r['ok']and not r['Run_called']and not r['save_touched'];reports.append(r);print(label+' passed',flush=True)
 assert reports[1]['component_stats']['downloaded_files']==32 and reports[1]['component_stats']['reused_files']==1860
 assert reports[2]['component_stats']['downloaded_files']==0 and reports[2]['component_stats']['reused_files']==1892
 template=(R/'analysis/pending-repairs-completion-20261031-v1/launcher-wear-v50-v2/friends_component_reader.cs').read_text('utf8')
 template=template.replace('if(mode=="good")throw','if(mode=="good"||mode=="public")throw').replace('if(mode!="good"){','if(mode!="good"&&mode!="public"){')
 anchor='c.GetField("TestTransport",flags).SetValue(null,transport);';assert template.count(anchor)==1;template=template.replace(anchor,'if(mode!="public")'+anchor)
 cs=D/'public-friends-reader.cs';cs.write_text(template,'utf8');reader=cs.with_suffix('.exe');run([compiler,'/nologo','/target:exe','/out:'+str(reader),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],'public-friends-compile')
 freports=[]
 for label,build,mode in [('old59-friends-seed',read(OLD/'build.json'),'good'),('public60-friends',b,'public')]:
  out=H/(label+'.json');run([reader,build['exe'],H/'f',build['signed_bindings']['signedFriends']['archive']['path'],out,mode],label,timeout=240);result=read(out);assert result['ok']and result['selected_identity']['payload']==build['signed_bindings']['signedFriends']['archive']['sha256']and result['second']['downloaded_files']==0;freports.append(result)
 assert freports[1]['first']['downloaded_files']==4 and freports[1]['first']['reused_files']==1796
 save(P/'public-friends-qualification.json',dict(ok=True,actual_default_CSharp_selector=True,pinned_TLS_and_signatures=True,changed_downloads=4,reused=1796,repeat_downloads=0,reports=freports,game_started=False))
 save(P/'public-qualification.json',dict(ok=True,exe_sha256=b['exe_sha256'],pinned_TLS_and_signatures=True,actual_CSharp_selector=True,changed_downloads=32,reused=1860,repeat_downloads=0,reports=reports,game_started=False))
def promote():
 b=pre();q=read(P/'public-qualification.json');assert q['ok']and q['exe_sha256']==b['exe_sha256'];h=held();assert all(sha(r['path'])==r['sha256']for r in h['launcher_parent'].values())
 parent=read(R/'releases/launchers/current.json');solo=read(R/'releases/launchers/standalone-current.json');assert parent==b['parent']and solo['sha256']==parent['sha256']
 backup=R/'releases/launchers/backups'/('before-'+RELEASE);assert not backup.exists();backup.mkdir()
 for n in ('current.json','standalone-current.json'):shutil.copy2(R/'releases/launchers'/n,backup/n)
 z=transport.scp(D/'latest.json','Administrator@134.175.57.52:'+STAGE+'/latest60.json');assert z.returncode==0
 before=read(P/'stage.json')['before']['public/latest.json']['sha256'];after=sha(D/'latest.json')
 remote("from pathlib import Path;import hashlib,json,os;R=Path('C:/ELS-Launcher-Updates');p=R/'public/latest.json';s=Path("+repr(STAGE+'/latest60.json')+");sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert sha(p)=="+repr(before)+";assert sha(s)=="+repr(after)+";os.replace(s,p);print(json.dumps(dict(ok=True,sha256=sha(p))))")
 # Existing V59 updater performs public pinned TLS, signature and EXE checks.
 t=(OLD/'old58_download59.cs').read_text('utf8').replace('version!=59','version!=60').replace('old_version=58','old_version=59');cs=D/'old59_download60.cs';cs.write_text(t,encoding='utf8');exe=cs.with_suffix('.exe');compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe';run([compiler,'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll',cs],'download-compile')
 (H/'updater').mkdir();run([exe,parent['path'],H/'updater',P/'public-download.json'],'download60',timeout=120);proof=read(P/'public-download.json');assert proof['ok']and proof['version']==60 and sha(proof['download'])==b['exe_sha256']
 formal=R/'deliverables/艾尔之光统一启动器-V60.exe';assert not formal.exists();shutil.copy2(b['exe'],formal)
 new=copy.deepcopy(parent);new.update(release=RELEASE,V=60,path=str(formal),sha256=b['exe_sha256'],size=formal.stat().st_size,parent_release=parent['release'],update_source=str(D/'source'),installation_receipt=str(P/'installation.json'),local_runtime_manifest=b['signed_bindings']['signedLOCAL']['manifest']['path'],local_payload_sha256=b['signed_bindings']['signedLOCAL']['archive']['sha256'],LOCAL_binding_unchanged=False,public_V59_to_V60_EXE_download_verified=True,runtime_manifest=b['signed_bindings']['signedFriends']['manifest']['path'],payload_sha256=b['signed_bindings']['signedFriends']['archive']['sha256'],payload_files_verified=1800,actual_payload_ZIP_members=1800,runtime_components_verified=1800,local_runtime_files=1892,UI_support_signed_both=True,Boost_LOCAL_signed=True,shop_rare_navy_signed_LOCAL=True,quest_gate_signed_LOCAL=True,normal_next_start_required=True,online_server_unchanged=True,quest_gate_business_source_PR=730,quest_gate_business_source_head='2256433920a446dafbc10b3b8e4844d6771668af',source_contract=str(D/'build.json'),source_contract_sha256=sha(D/'build.json'),Git_merge=False,current_delta_Git_merge=False)
 newsolo=copy.deepcopy(solo);newsolo.update(release=RELEASE,V=60,path=str(formal),sha256=b['exe_sha256'],local_runtime_manifest=new['local_runtime_manifest'],local_payload_sha256=new['local_payload_sha256'],installation_receipt=new['installation_receipt'],LOCAL_binding_unchanged=False,quest_gate_signed_LOCAL=True)
 for item in (new,newsolo):
  item['local_runtime_files']=1892;item['local_runtime_release']='local-git-first-run-activities-startup-20261101-v1';item['source_contract']=str(D/'build.json');item['source_contract_sha256']=sha(D/'build.json')
  for key in ('current_support_source_PR','current_support_source_head'):
   if item.get(key)is not None:item['inherited_'+key]=item[key]
   item[key]=None
  item['current_delta_Git_merge']=False
 # Only launcher shortcuts, preserve arguments/icons; never start or stop a game.
 ps=r"""$ErrorActionPreference='Stop';[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);$w=New-Object -ComObject WScript.Shell;$out=@();foreach($n in @('艾尔之光登录器.lnk','艾尔之光单机版.lnk')){$p=Join-Path ([Environment]::GetFolderPath('Desktop')) $n;$s=$w.CreateShortcut($p);if($s.TargetPath -ne OLD){throw 'Shortcut target drift'};Copy-Item -LiteralPath $p -Destination (Join-Path BACKUP $n);$args=$s.Arguments;$icon=$s.IconLocation;$s.TargetPath=NEW;$s.WorkingDirectory=DIR;$s.Save();$v=$w.CreateShortcut($p);if($v.TargetPath -ne NEW -or $v.Arguments -ne $args -or $v.IconLocation -ne $icon){throw 'Shortcut mismatch'};$out+=@{path=$p;target=$v.TargetPath;arguments=$v.Arguments;icon=$v.IconLocation}};$out|ConvertTo-Json -Compress"""
 quote=lambda v:"'"+str(v).replace("'","''")+"'"
 for k,v in [('OLD',parent['path']),('BACKUP',backup),('NEW',formal),('DIR',formal.parent)]:ps=ps.replace(k,quote(v))
 q=run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(ps.encode('utf-16le')).decode()],'shortcuts');save(P/'shortcuts.json',json.loads(q.stdout.decode('utf-8-sig')))
 for path,v,old in [(R/'releases/launchers/current.json',new,parent),(R/'releases/launchers/standalone-current.json',newsolo,solo)]:
  assert read(path)==old;tmp=path.with_name(path.name+'.qg60-next');assert not tmp.exists();save(tmp,v);os.replace(tmp,path)
 start=time.monotonic();checks=[]
 while time.monotonic()-start<120:
  time.sleep(min(25,120-(time.monotonic()-start)));held();assert read(R/'releases/launchers/current.json')==new and read(R/'releases/launchers/standalone-current.json')==newsolo
  result=remote("from pathlib import Path;import json,hashlib;p=Path('C:/ELS-Launcher-Updates/public/latest.json');print(json.dumps(dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest())))");assert result['sha256']==after;checks.append(dict(seconds=round(time.monotonic()-start,2),latest_sha256=after));print('Observation '+str(checks[-1]['seconds']),flush=True)
 save(P/'installation.json',dict(ok=True,release=RELEASE,V=60,sha256=b['exe_sha256'],public_V59_downloaded_V60=True,public_signed_LOCAL_delta=32,public_signed_Friends_delta=4,repeat_downloads=0,Friends_UI_only_delta=True,typed_owned_save_preserved=True,existing_LOCAL_upgrade_Run=True,existing_upgrade_pending_normal_game_exit=False,fresh_LOCAL_Run_verified=False,fresh_install_mechanism_reused=True,upgrade_mechanism_reused=True,normal_next_start_required=True,observation_seconds=time.monotonic()-start,observation=checks,game_server_unchanged=True,original_EXE_KOM_changes=0,player_database_changes=0,natural_GUI=False,natural_battle=False))
 print('V60 published and observed',flush=True)
def adopt():
 assert not(P/'reservation.json').exists()
 h=read(W/'publication/reservation.json');assert h['identity']['thread']==OWNER
 for n,ino in h['inodes'].items():
  f=R/'analysis/coordination-20261015'/n;assert f.stat().st_ino==ino and read(f)==h['identity']
 assert read(R/'releases/online/current.json')['release']=='three-activities-integrated-20261101-v1'
 assert read(R/'releases/local/current.json')['release']=='local-three-activities-integrated-20261101-v1'
 b=read(D/'build.json');assert read(R/'releases/launchers/current.json')==b['parent']
 assert read(W/'public-ui-trial-2/result.json')['ok']
 save(P/'reservation.json',dict(identity=h['identity'],inodes=h['inodes'],runtime_pins={str(R/'releases'/c/'current.json'):sha(R/'releases'/c/'current.json')for c in ('online','local')},launcher_parent={n:dict(path=str(R/'releases/launchers'/n),sha256=sha(R/'releases/launchers'/n))for n in ('current.json','standalone-current.json')}))
 pre();print('Existing own publication lease adopted; server unchanged',flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['adopt','stage','qualify_public','promote']);args=ap.parse_args();globals()[args.action]()
