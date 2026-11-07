from common import *
import base64,copy,shutil,time
B=read(D/'build.json');TAG='launcher-v103-'+B['exe_sha256'][:16];REPO='641927456/els-launcher-updates'
runner=R/'analysis/github-launcher-updates-20261106-v1/UpdateChecks.exe'
def run(args,name,timeout=150):
 q=subprocess.run(list(map(str,args)),capture_output=True,timeout=timeout,creationflags=0x08000000)
 (P/(name+'.private.txt')).write_bytes(q.stdout+q.stderr)
 assert q.returncode==0,(q.stdout+q.stderr).decode('utf8','replace')[-1400:]
 return q
def check():
 held();qualification=read(W/'public-component-qualification.json')
 assert sha(B['exe'])==B['exe_sha256']==qualification['exe_sha256']and qualification['ok']and qualification['tag']==TAG
 assert read(P/'online-installation-acceptance.json')['ok']and read(P/'local-runtime-acceptance.json')['ok']
 assert read(R/'releases/launchers/current.json')==read(P/'parents.json')['launchers']
def promote():
 check();assert not(P/'launcher-promotion.json').exists()
 notes=P/'published-notes.md';notes.write_text('V103：修复33242正常召唤坐标与隐藏控制器退场；原生发送Hook未发布；面板继续隐藏服务器IP。原游戏EXE/KOM未修改，自然GUI与全部业绩仍待验收。\n','utf8')
 run(['gh','release','edit',TAG,'--repo',REPO,'--prerelease=false','--latest','--title','统一启动器 V103','--notes-file',notes],'promote-v103',60)
 save(P/'launcher-promotion.json',dict(ok=True,tag=TAG,version=103,observation_start=time.time()))
 old_upgrade()

def old_upgrade():
 check();assert read(P/'launcher-promotion.json')['tag']==TAG
 assert not(P/'old-updater-upgrade.json').exists()
 parent=read(P/'parents.json')['launchers'];cache=R/'qa-ship-next-updater-20261107-v1'
 if cache.exists():
  assert read(cache/'owner.json')==dict(thread=OWNER,release=RID)
  failed=P/'old-latest.private.txt'
  if failed.exists():failed.rename(P/'old-latest-attempt1.private.txt')
 else:cache.mkdir();save(cache/'owner.json',dict(thread=OWNER,release=RID))
 run([runner,parent['path'],'latest',cache,P/'old-latest.json'],'old-latest',60);assert read(P/'old-latest.json')['version']==B['version']
 run([runner,parent['path'],'download',cache,D/'latest.json',P/'old-download.json'],'old-download',180)
 assert sha(read(P/'old-download.json')['path'])==B['exe_sha256']
 save(P/'old-updater-upgrade.json',dict(ok=True,from_version=parent['V'],to_version=B['version'],actual_old_updater_download=True,signature_and_SHA256_verified=True))
 print(json.dumps(dict(ok=True,stable_version=B['version'],actual_parent_updater_download=True)))
def observe():
 held();start=read(P/'launcher-promotion.json')['observation_start'];rows=[]
 while True:
  held();run([runner,B['exe'],'latest',P/'latest-metadata-cache',P/'observed-latest.json'],'observed-latest-'+str(len(rows)),60)
  assert read(P/'observed-latest.json')['version']==B['version']
  rows.append(dict(elapsed=time.time()-start,version=103))
  if rows[-1]['elapsed']>=120:break
  time.sleep(min(15,120-rows[-1]['elapsed']))
 save(P/'launcher-observation.json',dict(ok=True,seconds=time.time()-start,samples=rows))
 print(json.dumps(dict(ok=True,launcher_observation_seconds=time.time()-start)))
def install():
 check();assert read(P/'launcher-observation.json')['seconds']>=120 and read(P/'old-updater-upgrade.json')['ok']
 old=read(P/'parents.json')['launchers'];solo=read(R/'releases/launchers/standalone-current.json');assert solo['sha256']==old['sha256']
 backup=P/'launcher-parent';backup.mkdir();save(backup/'current.json',old);save(backup/'standalone-current.json',solo)
 formal=R/'deliverables/艾尔之光统一启动器-V103-整合版.exe';assert not formal.exists();shutil.copy2(B['exe'],formal);assert sha(formal)==B['exe_sha256']
 final=P/'launcher-v103';final.mkdir();shutil.copytree(D/'source',final/'source')
 for n in ('signedFriends.signed.json','runtime-files.json','latest.json'):shutil.copy2(D/n,final/n)
 os.link(B['exe'],final/'ElsFriends-V103.exe')
 build=copy.deepcopy(B);build.update(exe=str(final/'ElsFriends-V103.exe'),published=True,private_candidate=False,qualification_complete=True,release='launcher-santilus-spawn-retirement-20261107-v103')
 build['signed_bindings']['signedFriends']['manifest']['path']=str(final/'signedFriends.signed.json');save(final/'build.json',build)
 quote=lambda x:"'"+str(x).replace("'","''")+"'"
 script=r'''$ErrorActionPreference='Stop';$w=New-Object -ComObject WScript.Shell;$count=0
foreach($name in @('艾尔之光登录器.lnk','艾尔之光单机版.lnk')){
 $p=Join-Path ([Environment]::GetFolderPath('Desktop')) $name;$s=$w.CreateShortcut($p)
 if($s.TargetPath -ne OLD){throw 'Shortcut parent changed'}
 Copy-Item -LiteralPath $p -Destination (Join-Path BACKUP $name)
 $args=$s.Arguments;$icon=$s.IconLocation;$s.TargetPath=NEW;$s.WorkingDirectory=DIR;$s.Save()
 $v=$w.CreateShortcut($p);if($v.TargetPath -ne NEW -or $v.Arguments -ne $args -or $v.IconLocation -ne $icon){throw 'Shortcut readback mismatch'};$count++
};@{ok=$true;shortcuts=$count}|ConvertTo-Json -Compress'''
 for key,value in (('OLD',old['path']),('BACKUP',backup),('NEW',formal),('DIR',formal.parent)):script=script.replace(key,quote(value))
 q=run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],'shortcuts',40)
 shortcuts=json.loads(q.stdout.decode('utf-8-sig'));assert shortcuts['ok']and shortcuts['shortcuts']==2
 select_installed()

def select_installed():
 check();old=read(P/'parents.json')['launchers'];solo=read(R/'releases/launchers/standalone-current.json')
 backup=P/'launcher-parent';formal=R/'deliverables/艾尔之光统一启动器-V103-整合版.exe';final=P/'launcher-v103'
 assert read(backup/'current.json')==old and read(backup/'standalone-current.json')==solo
 assert solo['sha256']==old['sha256'] and sha(formal)==B['exe_sha256']
 assert read(final/'build.json')['exe_sha256']==B['exe_sha256'] and sha(final/'ElsFriends-V103.exe')==B['exe_sha256']
 for row in B['source_inventory'].items():assert sha(final/'source'/row[0])==row[1]['sha256']
 for name in ('signedFriends.signed.json','runtime-files.json','latest.json'):assert sha(final/name)==sha(D/name)
 quote=lambda x:"'"+str(x).replace("'","''")+"'"
 verify=r'''$ErrorActionPreference='Stop';$w=New-Object -ComObject WScript.Shell;$count=0
foreach($name in @('艾尔之光登录器.lnk','艾尔之光单机版.lnk')){
 $current=$w.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) $name))
 $before=$w.CreateShortcut((Join-Path BACKUP $name))
 if($current.TargetPath -ne NEW -or $current.Arguments -ne $before.Arguments -or $current.IconLocation -ne $before.IconLocation){throw 'Installed shortcut identity changed'};$count++
};@{ok=$true;shortcuts=$count}|ConvertTo-Json -Compress'''
 for key,value in (('BACKUP',backup),('NEW',formal)):verify=verify.replace(key,quote(value))
 verification=run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',base64.b64encode(verify.encode('utf-16le')).decode()],'shortcuts-readback',40)
 assert json.loads(verification.stdout.decode('utf-8-sig'))==dict(ok=True,shortcuts=2)
 new=copy.deepcopy(old)
 for key in list(new):
  if key.startswith('source_')or key.startswith('current_support_source')or key.startswith('current_delta_'):new.pop(key,None)
 payload=B['signed_bindings']['signedFriends']['archive']['sha256']
 new.update(build_receipt=str(final/'build.json'),release='launcher-santilus-spawn-retirement-20261107-v103',V=103,path=str(formal),sha256=B['exe_sha256'],size=B['size'],
  parent_release=old['release'],update_source=str(final/'source'),installation_receipt=str(P/'launcher-installation.json'),
  payload_sha256=payload,local_payload_sha256=payload,shared_runtime_archive_sha256=payload,runtime_manifest=str(final/'signedFriends.signed.json'),local_runtime_manifest=str(final/'signedFriends.signed.json'),
  payload_files_verified=B['payload_files'],actual_payload_ZIP_members=B['payload_files'],runtime_components_verified=B['payload_files'],local_runtime_files=B['payload_files'],LOCAL_signed_files_verified=B['payload_files'],
  unified_runtime=True,same_signed_definition_for_both_targets=True,Git_merge=True,current_delta_Git_merge=True,source_Git_merged=True,source_submission_pending=False,source_PR=plan['source_PR'],source_head=plan['source_head'],current_delta_PR=plan['source_PR'],current_delta_head=plan['source_head'],source_archive=plan['launcher_source_archive'],server_source_archive=plan['source_archive'],source_Git_submitted=True,
  current_support_delta=[r['path']for r in read(plan['candidate_manifest'])['files']],public_parent_to_V103_EXE_download_verified=True,upgrade_from_version=old['V'],
  local_runtime_release=read(R/'releases/local/current.json')['release'],normal_next_start_required=True,natural_GUI=False,natural_battle=False)
 for name,parent in (('current.json',old),('standalone-current.json',solo)):
  path=R/'releases/launchers'/name;assert read(path)==parent;tmp=path.with_name(name+'.quest-admission.next');save(tmp,new);os.replace(tmp,path)
 save(P/'launcher-installation.json',dict(ok=True,release=new['release'],version=103,exe_sha256=B['exe_sha256'],
  observation_seconds=read(P/'launcher-observation.json')['seconds'],anonymous_download=True,old_updater_upgrade=True,
  desktop_shortcuts=2,original_EXE_KOM_changes=0,player_database_restore=False))
 print(json.dumps(dict(ok=True,launcher_current=103,desktop_shortcuts=2)))
if __name__=='__main__':globals()[sys.argv[1]]()
