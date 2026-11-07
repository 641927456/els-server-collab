from delivery_common import *
from contextlib import closing
import base64,os,re,sqlite3,subprocess,sys,uuid,zipfile
D=W/'launcher-v62';H=R/'analysis/qa60u';owner=H/'p';repo=owner/'r';commit='b836a7dee8155bd33e0f91f4bf6803751bcd4aaa'
identity=read(H/'owner.json');assert identity['thread']==OWNER;nonce=identity['nonce'];assert read(owner/'owner.json')['nonce']==nonce
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()==commit
assert not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'])
# Reuse this chat's already-owned source/cache workspace; preserve all V60 proofs.
save(D/'private-workspace-binding.json',dict(root=str(H),owner=OWNER,nonce=nonce,reused_existing_owned_cache=True,prior_results_preserved=True))
parent_build=Path(read(W/'preceding-publisher-handoff.json')['parent_launcher_build']);old=read(parent_build);b=read(D/'build.json');assert old['version']==61 and b['version']==62
qtool=load('ring_typed_sqlite',R/'analysis/all-ground-item-models-20261101-v1/qualify_launcher_v59.py')
jobs=load('ring_owned_process',R/'analysis/all-ground-item-models-20261101-v1/launcher_owned_process.py');jobs.RECEIPTS=D/'processes'
compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
def run(argv,label,cwd=H,timeout=600):
 q=jobs.run(list(map(str,argv)),cwd=cwd,timeout=timeout);(D/(label+'.log')).write_bytes(q.stdout+q.stderr);print(label+' passed',flush=True)
def definition(build,family):return json.loads(base64.b64decode(read(build['signed_bindings'][family]['manifest']['path'])['payload']))
template=(R/'analysis/all-ground-item-models-20261101-v1/launcher-v59/public59-local.cs').read_text('utf8');reports=[]
def local(label,build):
 text=template.replace('G:/els/analysis/mp59p',H.as_posix());text,n=re.subn(r'ExpectedExe="[a-f0-9]{64}"','ExpectedExe="'+build['exe_sha256']+'"',text);assert n==1
 text,n=re.subn(r'NextPayload="[a-f0-9]{64}"','NextPayload="'+build['signed_bindings']['signedLOCAL']['archive']['sha256']+'"',text);assert n==1
 assert text.count('==59,')==1;text=text.replace('==59,','=='+str(build['version'])+',');assert text.count('next?1887:')==1;text=text.replace('next?1887:','next?1892:')
 with zipfile.ZipFile(build['signed_bindings']['signedLOCAL']['archive']['path'])as z:meta=json.loads(z.read('local-bootstrap-source.json'))
 assert text.count('local-git-first-run-registered-ground-items-20261101-v1')==1;text=text.replace('local-git-first-run-registered-ground-items-20261101-v1',meta['release'])
 cs=D/(label+'.cs');cs.write_text(text,'utf8');exe=cs.with_suffix('.exe');run([compiler,'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],label+'-compile',timeout=90)
 ref=build['signed_bindings']['signedLOCAL'];run([exe,build['exe'],build['exe_sha256'],ref['archive']['path'],ref['archive']['sha256'],repo,commit,'accessory',owner,nonce,label,'offline','run'],label)
 result=read(owner/'results'/(label+'.json'));assert result['ok']and result['Run_called']and result['component_files']==1892;reports.append(result);return result
local('ring-seed61',old)
ws=repo/'.runtime-cache/unified-local';db=ws/'state/integrated.sqlite3';accounts=ws/'state/friends/accounts.sqlite3';assert not db.exists()and not accounts.exists();db.parent.mkdir(parents=True,exist_ok=True)
sys.dont_write_bytecode=True;actual=R/read(R/'releases/local/current.json')['path'];sys.path.insert(0,str(actual));from els_server.storage.lifecycle import prepare_database
prepare_database(db)
for p in (db,accounts):
 p.parent.mkdir(parents=True,exist_ok=True)
 with closing(sqlite3.connect(p))as conn,conn:conn.execute('CREATE TABLE owned_ring_launcher_probe(nonce TEXT PRIMARY KEY,payload BLOB)');conn.execute('INSERT INTO owned_ring_launcher_probe VALUES(?,?)',(nonce,b'\x00ring62\xff'))
before={str(p):qtool.typed(p)for p in (db,accounts)};save(D/'typed-private-before.json',before)
upgrade=local('ring-upgrade62',b);assert {str(p):qtool.typed(p)for p in (db,accounts)}==before
repeat=local('ring-repeat62',b);assert repeat['component_stats']['downloaded_files']==0 and {str(p):qtool.typed(p)for p in (db,accounts)}==before
root=Path(repeat['root']);newdef=definition(b,'signedLOCAL')
for row in newdef['files']:assert (root/row['path']).stat().st_size==row['size']and sha(root/row['path'])==row['sha256'],row['path']
for row in read(R/'analysis/ring-wear-error-20261101-v1/result-v2.json')['runtime_files']:assert sha(root/row['path'])==row['sha256']
run([root/'python/python.exe','-B','-m','els_server','--config','config/server.toml','--check'],'ring-selected-normal-check',root,240)
expected=next(r['sha256']for r in b['resources']if r['name']=='ElsFriends.RingWearLocalBootstrap');scripts=[p for p in (owner/'component-cache/local-bootstrap').glob('*/local_bootstrap.py')if sha(p)==expected];assert scripts
boot=load('ring_actual_extracted_bootstrap',scripts[-1]);meta=read(root/'local-bootstrap-source.json');newrows=boot.rows(newdef);policy=boot.repair_policy(meta,newrows);assert len(policy['structure_contracts'])==18
assert boot.repair_original_restore_allowed(dict(repair_recovery_schema=1,repair_writer_admission_opened=False,repair_guarded_candidate=None,repair_database_before={'own':True}),{'own':True})is False
profile=boot.git_json(repo,commit,meta['profile']);formal=boot.rows({'files':profile['channels']['local']['files']});guard_ws=H/'ring62-guard';assert not guard_ws.exists();(guard_ws/'releases/local').mkdir(parents=True)
j=dict(target=commit,token=nonce,journal=str(guard_ws/'journal.json'));updater=boot.managed_updater();guarded,pointer,docs,installed=boot.repair_guarded_tree(root,guard_ws,meta,newrows,formal,{r['path']for r in meta['support_additions']},j,updater)
assert len(installed)==1894 and pointer['recovery_only']and not pointer['player_database_restore']
for rel in ('els_server/domain/fashion_state.py','els_server/storage/wear_moves.py'):assert sha(guarded/rel)==newrows[rel]['sha256']
for kind in ('manifest','archive'):assert b['signed_bindings']['signedFriends'][kind]['sha256']==old['signed_bindings']['signedFriends'][kind]['sha256']
friend_template=R/'analysis/pending-repairs-completion-20261031-v1/launcher-wear-v50-v2/friends_component_reader.cs';assert sha(friend_template)=='52e8fecb39cbe6ce5df642a896a8e7b87daf5c1a2a20244e5da092041bc0e086'
cs=D/'ring-friends-reader.cs';cs.write_bytes(friend_template.read_bytes());exe=cs.with_suffix('.exe');run([compiler,'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],'ring-friends-compile',timeout=90)
out=H/'ring62-friends.json';run([exe,b['exe'],H/'f',b['signed_bindings']['signedFriends']['archive']['path'],out,'good'],'ring-friends62',timeout=240);friends=read(out);assert friends['ok']and friends['selected_identity']['payload']==b['signed_bindings']['signedFriends']['archive']['sha256']and friends['second']['downloaded_files']==0
assert {str(p):qtool.typed(p)for p in (db,accounts)}==before
save(D/'qualification.json',dict(ok=True,exe_sha256=b['exe_sha256'],build_sha256=sha(D/'build.json'),actual_CSharp_LOCAL_Run=True,upgrade61_to62=True,repeat=True,all_1892_selected_files_verified=True,typed_owned_databases_preserved=True,complete_new_three_position_readers_retained_in_guarded_tree=True,recovery_original_restore_disallowed=True,predecessor_contracts=18,Friends_payload_unchanged=True,Friends_default_selector_current=True,Friends_repeat_zero_downloads=True,new_Hooks=0,natural_GUI=False,natural_battle=False,game_started=False,owner=str(H),reports=reports))
print(json.dumps(dict(ok=True,actual61_to62_upgrade=True,repeat_zero_downloads=True,new_readers_retained_on_recovery=True,game_started=False)))
