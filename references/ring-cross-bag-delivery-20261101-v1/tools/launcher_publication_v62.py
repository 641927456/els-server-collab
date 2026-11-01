"""ROOT-run V62 phase using the existing ROOT dual-delivery reservation.
Stages: stage, qualify_public (reuse unchanged V61 Friends proof), qualify_local, promote (old61 download62/current120), cleanup_stage.
Adopt exact shared reservation identity/inodes; server/raw currents stay unchanged. No service stop or public QA actor.
All build/q/runtime-pins refs are actual late-bound inputs; this SOURCE has not run.
"""
from pathlib import Path
import argparse, base64, copy, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time, uuid, stat

R=Path('G:/els'); W=Path(__file__).resolve().parent
OWNER='01a1943c-ec8b-7bb0-9682-188ec0c84bb8'; RELEASE='launcher-ring-wear-20261101-v62-v1'
STAGE='C:/ELS-Launcher-Updates/staging/ring-wear-v62-v1'
PARENT_BUILD=None
H=R/'analysis/ring62p'
D=P=DELIVERY=ARGS=None
from launcher_owned_process import run as owned_run
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
save=lambda p,v:Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
s=importlib.util.spec_from_file_location('login_publication_transport',R/'analysis/luciel-completion-01a14794-20261017/online-sync-v2/transport.py')
transport=importlib.util.module_from_spec(s);s.loader.exec_module(transport)

def remote(code,timeout=55):
    q=transport.run(code,timeout=timeout)
    if q.returncode:raise RuntimeError(q.stderr.decode('utf8','replace')[-2200:])
    return json.loads(q.stdout.decode('utf-8-sig'))

def held():
    h=read(P/'reservation.json');assert h['identity']['thread']==OWNER
    source=h['shared_reservation'];assert sha(source['path'])==source['sha256']
    original=read(source['path']);assert original['identity']==h['identity']and original['inodes']==h['inodes']
    for name,inode in h['inodes'].items():
        p=R/'analysis/coordination-20261015'/name
        assert p.stat().st_ino==inode and read(p)==h['identity']
    assert all(sha(ref['path'])==ref['sha256']for ref in h['runtime_pins'])
    return h

def definition_rows(build,family):
    ref=build['signed_bindings'][family]['manifest'];assert sha(ref['path'])==ref['sha256']
    d=json.loads(base64.b64decode(read(ref['path'])['payload'],validate=True))
    assert d['archive']['sha256']==build['signed_bindings'][family]['archive']['sha256']
    return {r['path']:r for r in d['files']}

def expected_delta(build,family):
    old=definition_rows(read(PARENT_BUILD),family);new=definition_rows(build,family)
    reused=sum(n in old and old[n]['sha256']==v['sha256'] and old[n]['size']==v['size'] for n,v in new.items())
    return len(new)-reused,reused

def preconditions():
    held();assert sha(ARGS.build)==ARGS.build_sha
    b=read(ARGS.build);assert b['ok']and b['version']==62 and sha(b['exe'])==b['exe_sha256']
    assert sha(ARGS.qualification)==ARGS.qualification_sha
    q=read(ARGS.qualification);assert q['ok']and q['exe_sha256']==b['exe_sha256']and q['build_sha256']==ARGS.build_sha
    for name in ('actual_CSharp_LOCAL_Run','upgrade61_to62','repeat','all_1892_selected_files_verified','typed_owned_databases_preserved','complete_new_three_position_readers_retained_in_guarded_tree','recovery_original_restore_disallowed','Friends_payload_unchanged','Friends_default_selector_current','Friends_repeat_zero_downloads'):assert q[name]is True,name
    assert q['predecessor_contracts']==18 and q['new_Hooks']==0
    assert expected_delta(b,'signedLOCAL')==(3,1889)and expected_delta(b,'signedFriends')==(0,1800)
    parent=read(R/'releases/launchers/current.json');assert parent==b['parent']and parent['V']==61
    assert read(R/'releases/launchers/standalone-current.json')['sha256']==parent['sha256']
    assert read(PARENT_BUILD)['exe_sha256']==parent['sha256']and sha(parent['path'])==parent['sha256']
    for ref in held()['launcher_parent_pins']:assert sha(ref['path'])==ref['sha256']
    for binding in b['signed_bindings'].values():
        for ref in binding.values():assert sha(ref['path'])==ref['sha256']
    return b


def qualify_local():
    b=preconditions();old=read(PARENT_BUILD);owner=H/'p';assert H.exists() and not owner.exists();owner.mkdir();nonce=uuid.uuid4().hex
    save(owner/'owner.json',dict(schema=1,kind='els-v45-reflection-prepare-v1',root=str(owner),nonce=nonce,thread=OWNER))
    repo=owner/'r';source=R/'analysis/character-login-stall-20261031-v1/git-source'
    def run(argv,log=None,timeout=240):
        q=owned_run(list(map(str,argv)),capture_output=True,timeout=timeout,creationflags=0x08000000)
        if log:Path(log).write_bytes(q.stdout+q.stderr)
        assert q.returncode==0,(q.stdout+q.stderr).decode(errors='replace')[-2200:];return q
    commit='b836a7dee8155bd33e0f91f4bf6803751bcd4aaa'
    run(['git','clone','--no-hardlinks','--dissociate','--no-checkout',source,repo]);assert not(repo/'.git/objects/info/alternates').exists();run(['git','-C',repo,'checkout','--detach',commit])
    t=(R/'analysis/group-dungeon-wear-20261031-v1/v7/v56-public-local-template.cs').read_text('utf8').replace('G:/els/analysis/gw56p',H.as_posix());reports=[]
    for label,build,mode in [('old61-public-seed',old,'offline'),('public62',b,'public'),('public62-repeat',b,'public')]:
        s=t
        s,n=re.subn(r'ExpectedExe="[a-f0-9]{64}"','ExpectedExe="'+build['exe_sha256']+'"',s);assert n==1
        s,n=re.subn(r'NextPayload="[a-f0-9]{64}"','NextPayload="'+build['signed_bindings']['signedLOCAL']['archive']['sha256']+'"',s);assert n==1
        assert s.count('==55,')==1;s=s.replace('==55,','=='+str(build['version'])+',')
        assert s.count('next?1877:')==1;s=s.replace('next?1877:','next?'+str(len(definition_rows(build,'signedLOCAL')))+':')
        import zipfile
        with zipfile.ZipFile(build['signed_bindings']['signedLOCAL']['archive']['path'])as z:managed=json.loads(z.read('local-bootstrap-source.json'))['release']
        assert s.count('local-git-first-run-quest-exp-native-20261101-v1')==1;s=s.replace('local-git-first-run-quest-exp-native-20261101-v1',managed)
        cs=D/(label+'-local.cs');assert not cs.exists();cs.write_text(s,encoding='utf8');exe=cs.with_suffix('.exe')
        compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        run([compiler,'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],D/(label+'-compile.txt'))
        binding=build['signed_bindings']['signedLOCAL']
        run([exe,build['exe'],build['exe_sha256'],binding['archive']['path'],binding['archive']['sha256'],repo,commit,'accessory',owner,nonce,label,mode,'components'],D/(label+'-local.txt'))
        v=read(owner/'results'/(label+'.json'));assert v['ok'] and not v['Run_called'] and not v['save_touched'];reports.append(v)
    expected=expected_delta(b,'signedLOCAL');first=reports[1]['component_stats'];repeat=reports[2]['component_stats']
    assert reports[1]['network'] and (first['downloaded_files'],first['reused_files'])==expected
    assert repeat['downloaded_files']==0 and repeat['reused_files']==len(definition_rows(b,'signedLOCAL'))
    save(D/'public-local-qualification.json',dict(ok=True,exe_sha256=b['exe_sha256'],public_pinned_TLS_and_signatures=True,component_count=len(definition_rows(b,'signedLOCAL')),LOCAL_changed=expected[0],LOCAL_reused=expected[1],repeat_downloads=0,all_signed_files_verified=True,actual_CSharp_upgrade_and_repeat_reused=read(ARGS.qualification)['actual_CSharp_LOCAL_Run'],reports=reports,game_started=False))

def cleanup_stage():
    held();assert read(P/'installation.json')['ok']
    stage=read(P/'server-stage.json');indexsha=sha(D/'index-additions.json')
    code="from pathlib import Path;import hashlib,json;S=Path("+repr(STAGE)+");p=S/'index-additions.json';assert S.is_dir() and not S.is_symlink();assert list(S.iterdir())==[p];assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()=="+repr(indexsha)+";p.unlink();S.rmdir();print(json.dumps(dict(ok=True,stage=str(S),absent=not S.exists(),removed_files=1)))"
    result=remote(code);save(P/'launcher-stage-cleanup.json',result)
    save(P/'launcher-cleanup-handoff.json',dict(ok=True,remote_stage_cleaned=True,reservation_retained=True,lock_release_owner='dual-delivery release only; launcher closeout retains same identity/inodes',QA_root=str(H),QA_cache_candidates=[str(H/n)for n in ('component-packages','component-runtimes','p/component-cache/component-packages','p/component-cache/component-runtimes','updater')],retain=['owner.json','p/owner.json','p/results','p/r',str(D),str(P)],QA_cache_deleted=False))

def stage():
    b=preconditions();assert not(P/'server-stage.json').exists(),'Preserve prior stage'
    parent=read(R/'releases/launchers/current.json');assert parent==b['parent']
    h=held();assert h['identity']['thread']==OWNER
    assert read(R/'releases/launchers/current.json')==parent
    save(P/'launcher-parent.json',parent)
    exe=Path(b['exe']);inputs={b['latest']['file']:exe}
    for family in ('signedLOCAL',):
        binding=b['signed_bindings'][family];archive=Path(binding['archive']['path']);inputs[archive.name]=archive
    pins={n:dict(size=p.stat().st_size,sha256=sha(p)) for n,p in inputs.items()}
    friends=b['signed_bindings']['signedFriends']['archive'];remote("from pathlib import Path;import hashlib,json;R=Path('C:/ELS-Launcher-Updates');p=R/'public'/"+repr(Path(friends['path']).name)+";assert p.name in json.loads((R/'allowlist.json').read_bytes());assert p.stat().st_size=="+repr(Path(friends['path']).stat().st_size)+";assert hashlib.sha256(p.read_bytes()).hexdigest()=="+repr(friends['sha256'])+";print(json.dumps(dict(ok=True,Friends_original_archive_unchanged=True,size=p.stat().st_size)))")
    remote("from pathlib import Path;import json;p=Path("+repr(STAGE)+");assert not p.exists();p.mkdir(parents=True);print(json.dumps(dict(ok=True)))")
    for name,path in inputs.items():
        z=transport.scp(path,'Administrator@134.175.57.52:'+STAGE+'/'+name)
        assert z.returncode==0,z.stderr.decode(errors='replace');print('Uploaded immutable '+name,flush=True)
    oldhashes={r['sha256']for family in ('signedLOCAL','signedFriends')for r in definition_rows(read(PARENT_BUILD),family).values()}
    additions={}
    for family in ('signedLOCAL',):
        binding=b['signed_bindings'][family];definition=json.loads(base64.b64decode(read(binding['manifest']['path'])['payload']))
        for row in definition['files']:
            if row['sha256']in oldhashes:continue
            additions.setdefault(row['sha256'],dict(archive=definition['archive']['file'],entry=row['path'],size=row['size']))
    expected_hashes={r['sha256']for r in definition_rows(b,'signedLOCAL').values()}-oldhashes
    assert set(additions)==expected_hashes
    save(D/'index-additions.json',additions)
    z=transport.scp(D/'index-additions.json','Administrator@134.175.57.52:'+STAGE+'/index-additions.json');assert z.returncode==0,z.stderr
    code=r'''
from pathlib import Path
import hashlib,json,os,shutil,base64
R=Path('C:/ELS-Launcher-Updates');S=Path(STAGE);pins=PINS
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={n:dict(sha256=sha(R/n),size=(R/n).stat().st_size) for n in ('allowlist.json','components-index.json','public/latest.json')}
latest=json.loads((R/'public/latest.json').read_bytes())
remote_parent=json.loads(base64.b64decode(latest['payload']));assert remote_parent['version']==61 and remote_parent['sha256']==PARENT_EXE
backup=R/'backups/ring-wear-v62-v1';assert not backup.exists();backup.mkdir()
for n in before:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/n,p)
for name,row in pins.items():
 source=S/name;target=R/'public'/name
 assert source.resolve()==source and target.resolve()==target and source.is_relative_to(S)
 assert source.stat().st_size==row['size'] and sha(source)==row['sha256']
 if target.exists():
  assert target.stat().st_size==row['size']and sha(target)==row['sha256'];source.unlink()
 else:os.rename(source,target)
index=json.loads((R/'components-index.json').read_bytes());old=dict(index)
for key,row in json.loads((S/'index-additions.json').read_bytes()).items():
 if key in index:assert index[key]['size']==row['size']
 else:index[key]=row
assert all(index[k]==v for k,v in old.items())
allowed=json.loads((R/'allowlist.json').read_bytes());old_allowed=list(allowed)
for name in pins:
 if name not in allowed:allowed.append(name)
for name,value in (('components-index.json',index),('allowlist.json',allowed)):
 temp=S/(name+'.next');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');os.replace(temp,R/name)
assert sha(R/'public/latest.json')==before['public/latest.json']['sha256']
print(json.dumps(dict(ok=True,backup=str(backup),before=before,index_before=len(old),index_after=len(index),old_entries_preserved=True,latest_unchanged=True)))
'''.replace('STAGE',repr(STAGE)).replace('PINS',repr(pins)).replace('PARENT_EXE',repr(b['parent']['sha256']))
    result=remote(code);save(P/'server-stage.json',result);print(json.dumps(result),flush=True)

def qualify_public():
    b=preconditions();assert not H.exists();H.mkdir()
    save(H/'owner.json',dict(thread=OWNER,purpose='Public LOCAL ring delta selector; no game'))
    q=read(ARGS.qualification)
    save(D/'public-component-qualification.json',dict(ok=True,exe_sha256=b['exe_sha256'],Friends_bytes_exactly_V61=True,Friends_retested=False,reused_current_offline_friends_qualification=dict(path=str(ARGS.qualification),sha256=sha(ARGS.qualification)),game_started=False))


def promote():
    b=preconditions();h=held();q=read(D/'public-component-qualification.json');lq=read(D/'public-local-qualification.json');assert lq['ok'] and lq['exe_sha256']==b['exe_sha256']
    assert q['ok'] and q['exe_sha256']==b['exe_sha256']
    parent=read(R/'releases/launchers/current.json');solo=read(R/'releases/launchers/standalone-current.json')
    assert parent==read(P/'launcher-parent.json') and parent==b['parent'] and solo['sha256']==parent['sha256']
    backup=R/'releases/launchers/backups'/('before-'+RELEASE);assert not backup.exists();backup.mkdir()
    for name in ('current.json','standalone-current.json'):shutil.copy2(R/'releases/launchers'/name,backup/name)
    z=transport.scp(D/'latest.json','Administrator@134.175.57.52:'+STAGE+'/latest62.json');assert z.returncode==0,z.stderr
    before=read(P/'server-stage.json')['before']['public/latest.json']['sha256'];newsha=sha(D/'latest.json')
    code="from pathlib import Path;import json,hashlib,os;R=Path('C:/ELS-Launcher-Updates');p=R/'public/latest.json';s=Path("+repr(STAGE+"/latest62.json")+");sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert sha(p)=="+repr(before)+";assert sha(s)=="+repr(newsha)+";os.replace(s,p);print(json.dumps(dict(ok=True,latest_sha256=sha(p))))"
    result=remote(code);save(P/'public-metadata.json',result);print('Public signed V62 metadata promoted',flush=True)
    # Run the actual old updater's pinned HTTPS + signature + EXE download path.
    cs=r'''using System;using System.IO;using System.Reflection;using System.Web.Script.Serialization;
class DownloadUpdate { static int Main(string[] a){try{var flags=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static;var asm=Assembly.LoadFile(Path.GetFullPath(a[0]));asm.GetType("ElsFriends.Program").GetField("DataRoot",flags).SetValue(null,a[1]);var t=asm.GetType("ElsFriends.AutoUpdate");var r=t.GetMethod("Latest",flags).Invoke(null,null);var rt=r.GetType();int version=(int)rt.GetField("Version").GetValue(r);if(version!=62)throw new Exception("Wrong update version");var target=(string)t.GetMethod("Download",flags).Invoke(null,new object[]{r,new Action<int>(n=>{})});if(!(bool)t.GetMethod("ValidFile",flags).Invoke(null,new object[]{target,r}))throw new Exception("Downloaded update verification failed");File.WriteAllText(a[2],new JavaScriptSerializer().Serialize(new{ok=true,old_version=61,version=version,download=target,downloaded_from_public=true,TLS_pin_verified=true,signature_verified=true,EXE_verified=true,launcher_Main_called=false}));return 0;}catch(Exception e){Console.Error.WriteLine(e);return 1;}}}'''
    (H/'updater').mkdir()
    source=D/'old61_download62.cs';source.write_text(cs,encoding='utf8');exe=D/'old61_download62.exe'
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    x=owned_run([str(compiler),'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll',str(source)],capture_output=True,timeout=60,creationflags=0x08000000)
    assert x.returncode==0,x.stdout.decode(errors='replace')[-1400:]
    out=D/'old61-public-download62.json'
    x=owned_run([str(exe),parent['path'],str(H/'updater'),str(out)],capture_output=True,timeout=120,creationflags=0x08000000)
    (D/'old61-public-download62.txt').write_bytes(x.stdout+x.stderr);assert x.returncode==0,x.stderr.decode(errors='replace')[-1800:]
    proof=read(out);assert proof['ok'] and sha(proof['download'])==b['exe_sha256']
    formal=R/'deliverables/艾尔之光统一启动器-V62.exe';assert not formal.exists();shutil.copy2(b['exe'],formal);assert sha(formal)==b['exe_sha256']
    ps=r'''$ErrorActionPreference='Stop';[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);$w=New-Object -ComObject WScript.Shell;$out=@();foreach($n in @('艾尔之光登录器.lnk','艾尔之光单机版.lnk')){$p=Join-Path ([Environment]::GetFolderPath('Desktop')) $n;$s=$w.CreateShortcut($p);if($s.TargetPath -ne OLD){throw 'Shortcut target drift'};Copy-Item -LiteralPath $p -Destination (Join-Path BACKUP $n);$args=$s.Arguments;$icon=$s.IconLocation;$s.TargetPath=NEW;$s.WorkingDirectory=DIR;$s.Save();$v=$w.CreateShortcut($p);if($v.TargetPath -ne NEW -or $v.Arguments -ne $args -or $v.IconLocation -ne $icon){throw 'Shortcut readback mismatch'};$out+=@{path=$p;target=$v.TargetPath;arguments=$v.Arguments;icon=$v.IconLocation}};$out|ConvertTo-Json -Compress'''
    quote=lambda v:"'"+str(v).replace("'","''")+"'"
    for key,value in (('OLD',parent['path']),('BACKUP',backup),('NEW',formal),('DIR',formal.parent)):ps=ps.replace(key,quote(value))
    x=owned_run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(ps.encode('utf-16le')).decode()],capture_output=True,timeout=40,creationflags=0x08000000)
    assert x.returncode==0,x.stderr.decode(errors='replace')[-1800:];save(P/'desktop-shortcuts.json',json.loads(x.stdout.decode('utf-8-sig')))
    receipt=P/'installation.json';new=copy.deepcopy(parent)
    new.update(release=RELEASE,V=62,path=str(formal),sha256=b['exe_sha256'],size=formal.stat().st_size,parent_release=parent['release'],
        update_source=str(D/'source'),Git_merge=False,current_delta_Git_merge=False,installation_receipt=str(receipt),payload_sha256=b['signed_bindings']['signedFriends']['archive']['sha256'],runtime_manifest=b['signed_bindings']['signedFriends']['manifest']['path'],
        support_existing_changes=len(set(b['component_delta']['signedFriends']) & set(definition_rows(read(PARENT_BUILD),'signedFriends'))),support_new_files=len(set(definition_rows(b,'signedFriends'))-set(definition_rows(read(PARENT_BUILD),'signedFriends'))),current_support_delta=b['component_delta']['signedFriends'],local_runtime_manifest=b['signed_bindings']['signedLOCAL']['manifest']['path'],local_payload_sha256=b['signed_bindings']['signedLOCAL']['archive']['sha256'],current_support_source_PRs=[],current_support_source_heads={},current_support_source_PR=None,current_support_source_head=None,
        source_contract=str(W/'publication/release-contract.json'),public_V61_to_V62_EXE_download_verified=True,interactive_character_entry_native_only=True,
        new_native_support_modules=[],normal_next_start_required=True,natural_login_verified=False,LOCAL_binding_unchanged=False,online_server_unchanged=True)
    new.update(total_embedded_resources=len(b['resources']),payload_files_verified=len(definition_rows(b,'signedFriends')),actual_payload_ZIP_members=len(definition_rows(b,'signedFriends')),runtime_components_verified=len(definition_rows(b,'signedFriends')),local_runtime_files=len(definition_rows(b,'signedLOCAL')),LOCAL_signed_files_verified=len(definition_rows(b,'signedLOCAL')),ring_wear_readers_signed_synchronization=True)
    new.pop('new_native_Hooks',None)
    newsolo=copy.deepcopy(solo);newsolo.update(local_payload_sha256=b['signed_bindings']['signedLOCAL']['archive']['sha256'],local_runtime_manifest=b['signed_bindings']['signedLOCAL']['manifest']['path'],release=RELEASE,V=62,path=str(formal),sha256=b['exe_sha256'],installation_receipt=str(receipt),LOCAL_binding_unchanged=False)
    for path,value,old in ((R/'releases/launchers/current.json',new,parent),(R/'releases/launchers/standalone-current.json',newsolo,solo)):
        assert read(path)==old;tmp=path.with_name(path.name+'.mp61-next');assert not tmp.exists();save(tmp,value);os.replace(tmp,path)
    start=time.monotonic();checks=[]
    while time.monotonic()-start<120:
        time.sleep(min(25,120-(time.monotonic()-start)))
        v=remote("from pathlib import Path;import hashlib,json;p=Path('C:/ELS-Launcher-Updates/public/latest.json');print(json.dumps(dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest())))")
        held();assert read(R/'releases/launchers/current.json')==new and read(R/'releases/launchers/standalone-current.json')==newsolo
        assert v['sha256']==newsha;checks.append(dict(seconds=round(time.monotonic()-start,2),latest_sha256=v['sha256']))
        print('Signed update observation '+str(checks[-1]['seconds'])+' seconds',flush=True)
    result=dict(ok=True,release=RELEASE,V=62,path=str(formal),sha256=b['exe_sha256'],public_old61_downloaded_verified62=True,
        public_signed_LOCAL_components_verified=True,public_changed_components=expected_delta(b,'signedLOCAL')[0],public_reused_components=expected_delta(b,'signedLOCAL')[1],repeat_downloads=0,Friends_bytes_exactly_V61=True,Friends_actual_success_reused=True,
        desktop_shortcuts_updated=True,LOCAL_binding_unchanged=False,game_server_unchanged=True,player_database_changes=0,
        original_EXE_KOM_changes=0,new_native_support_modules=[],observation_seconds=time.monotonic()-start,observation=checks,
        actual_game_login_verified=False,actual_game_login_pending='Public five-ring purchase, bidirectional replacement, cold restore and original native decoder verified; no natural GUI claim',
        normal_next_start_required=True,whole_goal_complete=False)
    held();result.update(reservation_retained_for_launcher_closeout=True,qualification_sha256=sha(ARGS.qualification),runtime_pins=held()['runtime_pins'],build_sha256=sha(ARGS.build))
    save(receipt,result);print(json.dumps(result),flush=True)


def adopt():
    assert not(P/'reservation.json').exists()
    source=W/'publication/reservation.json';shared=read(source)
    assert shared['identity']['thread']==OWNER and shared['identity']['release']=='ring-wear-cross-bag-20261101-v1'
    assert set(shared['inodes'])=={'active-publication.lock','publication-record.lock'}
    for name,inode in shared['inodes'].items():
        p=R/'analysis/coordination-20261015'/name;assert p.stat().st_ino==inode and read(p)==shared['identity']
    b=read(ARGS.build);point=read(R/'releases/local/current.json');assert point['release']==b['raw_local_source']['release']and point['manifest_sha256']==b['raw_local_source']['manifest_sha256']
    paths=[R/'releases/online/current.json',R/'releases/local/current.json']
    pins=[dict(path=str(p),sha256=sha(p))for p in paths]
    launcher_pins=[dict(path=str(R/'releases/launchers'/n),sha256=sha(R/'releases/launchers'/n))for n in ('current.json','standalone-current.json')]
    save(P/'reservation.json',dict(identity=shared['identity'],inodes=shared['inodes'],shared_reservation=dict(path=str(source),sha256=sha(source)),runtime_pins=pins,launcher_parent_pins=launcher_pins,phase='launcher62-after-dual-installed',owns_lock_release=False))
    preconditions();print(json.dumps(dict(ok=True,shared_reservation_adopted=True,no_new_locks=True)))


def closeout():
    held();assert read(P/'installation.json')['ok']and read(P/'installation.json')['observation_seconds']>=120
    assert read(P/'launcher-stage-cleanup.json')['ok']
    save(P/'closeout.json',dict(ok=True,own_locks_released=False,shared_reservation_retained=True,public_cache_retained_for_exact_owner_cleanup=True,service_changes=0,public_accounts_created=0))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('stage',choices=['adopt','stage','qualify_public','qualify_local','promote','cleanup_stage','closeout'])
    for name in ('build','qualification'):ap.add_argument('--'+name,type=Path,required=True)
    for name in ('build-sha','qualification-sha'):ap.add_argument('--'+name,required=True)
    ARGS=ap.parse_args();D=ARGS.build.resolve().parent;P=D/'publication';P.mkdir(exist_ok=True)
    PARENT_BUILD=Path(read(W/'preceding-publisher-handoff.json')['parent_launcher_build'])
    import launcher_owned_process;launcher_owned_process.RECEIPTS=P/'processes'
    assert ARGS.build.name=='build.json' and D.is_relative_to(W)
    globals()[ARGS.stage]()
