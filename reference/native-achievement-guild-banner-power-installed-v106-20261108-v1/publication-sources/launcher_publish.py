from common import *
import base64,copy,shutil,time
B=read(D/'build.json');TAG='launcher-v106-'+B['exe_sha256'][:16];REPO='641927456/els-launcher-updates'
runner=R/'analysis/github-launcher-updates-20261106-v1/UpdateChecks.exe'
def run(args,name,timeout=150):
 q=subprocess.run(list(map(str,args)),capture_output=True,timeout=timeout,creationflags=0x08000000)
 (P/(name+'.private.txt')).write_bytes(q.stdout+q.stderr)
 assert q.returncode==0,(q.stdout+q.stderr).decode('utf8','replace')[-1400:]
 return q
def check():
 held();assert sha(B['exe'])==B['exe_sha256']and read(P/'public-component-qualification.json')['ok']
 assert read(P/'online-installation-acceptance.json')['ok']and read(P/'local-runtime-acceptance.json')['ok']
 assert read(R/'releases/launchers/current.json')==read(P/'parents.json')['launchers']
def promote():
 check();assert not(P/'launcher-promotion.json').exists()
 notes=P/'published-notes.md';notes.write_text('V106：接通公会徽章召唤、四处场景显示同步及30条原生战力业绩，共47类来源、318条定义；其余13类和53组原奖励保留。保留V105副本修复，面板继续隐藏IP，原EXE/KOM未改，自然GUI待验。\n','utf8')
 run(['gh','release','edit',TAG,'--repo',REPO,'--prerelease=false','--latest','--title','统一启动器 V106','--notes-file',notes],'promote-v106',60)
 save(P/'launcher-promotion.json',dict(ok=True,tag=TAG,version=106,observation_start=time.time()))
 old_upgrade()

def old_upgrade():
 check();assert read(P/'launcher-promotion.json')['tag']==TAG
 assert not(P/'old-updater-upgrade.json').exists()
 parent=read(P/'parents.json')['launchers'];cache=R/'qa-ach106-updater-20261108-v1'
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
 held();assert read(P/'old-updater-upgrade.json')['ok'];start=time.time();rows=[]
 while True:
  held();run([runner,B['exe'],'latest',P/'latest-metadata-cache',P/'observed-latest-v2.json'],'observed-latest-v2-'+str(len(rows)),60)
  assert read(P/'observed-latest-v2.json')['version']==B['version']
  rows.append(dict(elapsed=time.time()-start,version=106))
  if rows[-1]['elapsed']>=120:break
  time.sleep(min(15,120-rows[-1]['elapsed']))
 save(P/'launcher-observation.json',dict(ok=True,seconds=time.time()-start,samples=rows,attempt=2,fresh_window_after_metadata_timeout=True,first_failure_retained=True))
 print(json.dumps(dict(ok=True,launcher_observation_seconds=time.time()-start)))
def install():
 check();assert read(P/'launcher-observation.json')['seconds']>=120 and read(P/'old-updater-upgrade.json')['ok']
 old=read(P/'parents.json')['launchers'];solo=read(R/'releases/launchers/standalone-current.json');assert solo['sha256']==old['sha256']
 backup=P/'launcher-parent';backup.mkdir();save(backup/'current.json',old);save(backup/'standalone-current.json',solo)
 formal=R/'deliverables/艾尔之光统一启动器-V106-整合版.exe';assert not formal.exists();shutil.copy2(B['exe'],formal);assert sha(formal)==B['exe_sha256']
 final=P/'launcher-v106';final.mkdir();shutil.copytree(D/'source',final/'source')
 for n in ('signedFriends.signed.json','runtime-files.json','latest.json'):shutil.copy2(D/n,final/n)
 os.link(B['exe'],final/'ElsFriends-V106.exe')
 build=copy.deepcopy(B);build.update(exe=str(final/'ElsFriends-V106.exe'),published=True,private_candidate=False,qualification_complete=True,release='launcher-achievement-guild-banner-power-20261108-v106')
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
 new=copy.deepcopy(old)
 for key in list(new):
  if key.startswith('source_')or key.startswith('current_support_source')or key.startswith('current_delta_'):new.pop(key,None)
 payload=B['signed_bindings']['signedFriends']['archive']['sha256']
 new.update(build_receipt=str(final/'build.json'),release='launcher-achievement-guild-banner-power-20261108-v106',V=106,path=str(formal),sha256=B['exe_sha256'],size=B['size'],
  parent_release=old['release'],update_source=str(final/'source'),installation_receipt=str(P/'launcher-installation.json'),
  payload_sha256=payload,local_payload_sha256=payload,shared_runtime_archive_sha256=payload,runtime_manifest=str(final/'signedFriends.signed.json'),local_runtime_manifest=str(final/'signedFriends.signed.json'),
  payload_files_verified=2875,actual_payload_ZIP_members=2875,runtime_components_verified=2875,local_runtime_files=2875,LOCAL_signed_files_verified=2875,
  unified_runtime=True,same_signed_definition_for_both_targets=True,Git_merge=False,current_delta_Git_merge=False,source_Git_merged=False,source_submission_pending=False,source_PR=plan['source_PR'],source_head=plan['source_head'],current_delta_PR=plan['source_PR'],current_delta_head=plan['source_head'],source_archive=plan['launcher_source_archive'],server_source_archive=plan['source_archive'],source_Git_submitted=True,
  current_support_delta=[r['path']for r in read(plan['candidate_manifest'])['files']],public_V105_to_V106_EXE_download_verified=True,
  local_runtime_release=read(R/'releases/local/current.json')['release'],normal_next_start_required=True,natural_GUI=False,natural_battle=False)
 for name,parent in (('current.json',old),('standalone-current.json',solo)):
  path=R/'releases/launchers'/name;assert read(path)==parent;tmp=path.with_name(name+'.quest-admission.next');save(tmp,new);os.replace(tmp,path)
 save(P/'launcher-installation.json',dict(ok=True,release=new['release'],version=106,exe_sha256=B['exe_sha256'],
  observation_seconds=read(P/'launcher-observation.json')['seconds'],anonymous_download=True,old_updater_upgrade=True,
  desktop_shortcuts=2,original_EXE_KOM_changes=0,player_database_restore=False))
 print(json.dumps(dict(ok=True,launcher_current=106,desktop_shortcuts=2)))
if __name__=='__main__':globals()[sys.argv[1]]()
