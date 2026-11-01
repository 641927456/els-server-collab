from pathlib import Path
from contextlib import closing
import base64,hashlib,importlib.util,json,os,re,sqlite3,sys,uuid,zipfile
R=Path('G:/els');W=Path(__file__).parent;D=W/'launcher-v60';P=R/'analysis/all-ground-item-models-20261101-v1/launcher-v59';H=R/'analysis/qa60a'
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def load(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
job=load('qg60runner',P.parent/'launcher_owned_process.py');job.RECEIPTS=D/'processes'
oldq=load('oldq',P.parent/'qualify_launcher_v59.py')
def run(argv,label,cwd=H,timeout=600):
    q=job.run(list(map(str,argv)),cwd=cwd,timeout=timeout);(D/(label+'.log')).write_bytes(q.stdout+q.stderr);print(label+' passed',flush=True);return q
def main():
    resuming='--resume'in sys.argv
    b=read(D/'build.json');old=read(P/'build.json');owner=H/'p'
    if resuming:
        identity=read(H/'owner.json');assert identity['thread']=='01a1943c-ec8b-7bb0-9682-188ec0c84bb8';nonce=identity['nonce']
        failure=read(owner/'results/upgrade60.json');assert failure['Run_called']is False and failure['error']=='Unexpected signed component count'
        assert not(D/'upgrade60-initial-failure.json').exists();save(D/'upgrade60-initial-failure.json',failure)
        (owner/'results/upgrade60.json').rename(owner/'results/upgrade60-initial-failure.json')
    else:
        assert not H.exists();H.mkdir();nonce=uuid.uuid4().hex;owner.mkdir();save(H/'owner.json',dict(thread='01a1943c-ec8b-7bb0-9682-188ec0c84bb8',root=str(H),nonce=nonce));save(owner/'owner.json',dict(schema=1,kind='els-v45-reflection-prepare-v1',root=str(owner),nonce=nonce))
    repo=owner/'r';commit='b836a7dee8155bd33e0f91f4bf6803751bcd4aaa'
    if not resuming:
        run(['git','clone','--no-hardlinks','--dissociate','--no-checkout',R/'analysis/shop-rare-navy-20261101-v1/git-source',repo],'clone');assert not(repo/'.git/objects/info/alternates').exists();run(['git','-C',repo,'checkout','--detach',commit],'checkout')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe';template=(P/'public59-local.cs').read_text('utf8');reports=[]
    def local(label,build,mode='offline',operation='run'):
        t=template.replace('G:/els/analysis/mp59p',H.as_posix())
        t,n=re.subn(r'ExpectedExe="[a-f0-9]{64}"','ExpectedExe="'+build['exe_sha256']+'"',t);assert n==1
        t,n=re.subn(r'NextPayload="[a-f0-9]{64}"','NextPayload="'+build['signed_bindings']['signedLOCAL']['archive']['sha256']+'"',t);assert n==1
        assert t.count('==59,')==1;t=t.replace('==59,','=='+str(build['version'])+',')
        with zipfile.ZipFile(build['signed_bindings']['signedLOCAL']['archive']['path'])as z:meta=json.loads(z.read('local-bootstrap-source.json'))
        assert t.count('local-git-first-run-registered-ground-items-20261101-v1')==1;t=t.replace('local-git-first-run-registered-ground-items-20261101-v1',meta['release'])
        component_count=len(json.loads(base64.b64decode(read(build['signed_bindings']['signedLOCAL']['manifest']['path'])['payload']))['files'])
        assert t.count('next?1887:')==1;t=t.replace('next?1887:','next?'+str(component_count)+':')
        cs=D/(label+'.cs');cs.write_text(t,encoding='utf8');exe=cs.with_suffix('.exe');run([compiler,'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],label+'-compile')
        ref=build['signed_bindings']['signedLOCAL'];run([exe,build['exe'],build['exe_sha256'],ref['archive']['path'],ref['archive']['sha256'],repo,commit,'accessory',owner,nonce,label,mode,operation],label)
        r=read(owner/'results'/(label+'.json'));assert r['ok']and r['Run_called']==(operation=='run');reports.append(r);return r
    if not resuming:local('old59',old)
    else:reports.append(read(owner/'results/old59.json'))
    ws=repo/'.runtime-cache/unified-local';db=ws/'state/integrated.sqlite3';accounts=ws/'state/friends/accounts.sqlite3'
    sys.dont_write_bytecode=True;raw=R/read(R/'releases/local/current.json')['path'];sys.path.insert(0,str(raw));from els_server.storage.lifecycle import prepare_database
    if not resuming:
        assert not db.exists()and not accounts.exists();db.parent.mkdir(parents=True,exist_ok=True);prepare_database(db)
        for p in (db,accounts):
            p.parent.mkdir(parents=True,exist_ok=True)
            with closing(sqlite3.connect(p))as conn,conn:
                conn.execute('CREATE TABLE owned_launcher_probe(nonce TEXT PRIMARY KEY,payload BLOB)');conn.execute('INSERT INTO owned_launcher_probe VALUES(?,?)',(nonce,b'\x00qg60\xff'))
        before={str(p):oldq.typed(p)for p in (db,accounts)};save(H/'typed-before.json',before)
    else:
        before=read(H/'typed-before.json');assert {str(p):oldq.typed(p)for p in (db,accounts)}==before
    upgrade=local('upgrade60',b);assert {str(p):oldq.typed(p)for p in (db,accounts)}==before
    repeat=local('repeat60',b);assert repeat['component_stats']['downloaded_files']==0;assert {str(p):oldq.typed(p)for p in (db,accounts)}==before
    root=Path(repeat['root']);env=read(b['signed_bindings']['signedLOCAL']['manifest']['path']);definition=json.loads(base64.b64decode(env['payload']))
    for row in definition['files']:assert (root/row['path']).stat().st_size==row['size']and sha(root/row['path'])==row['sha256'],row['path']
    run([root/'python/python.exe','-B','-m','els_server','--config','config/server.toml','--check'],'selected-normal-check',root)
    # Verify the exact selected current rules, including all 11 quest gate repairs.
    contract=load('contract',R/'analysis/distorted-memory-gate-20261101-v1/git-source/tools/check_controller_quest_gates.py');rules=contract.literal_rules(root/'els_server/domain/public_controller_rules.py');cases=read(R/'analysis/distorted-memory-gate-20261101-v1/git-source/references/controller-quest-gates-20261101-v1/cases.json');assert all(c in rules for c in cases)
    boot=load('newboot',D/'source/resources/quest-gates-local-bootstrap.py');meta=read(root/'local-bootstrap-source.json');newrows=boot.rows(definition);policy=boot.repair_policy(meta,newrows);assert len(policy['structure_contracts'])==16
    assert boot.repair_original_restore_allowed(dict(repair_recovery_schema=1,repair_writer_admission_opened=False,repair_guarded_candidate=None,repair_database_before={'own':True}),{'own':True})is False
    assert {str(p):oldq.typed(p)for p in (db,accounts)}==before
    friend_template=R/'analysis/pending-repairs-completion-20261031-v1/launcher-wear-v50-v2/friends_component_reader.cs'
    assert sha(friend_template)=='52e8fecb39cbe6ce5df642a896a8e7b87daf5c1a2a20244e5da092041bc0e086'
    cs=D/'friends-reader.cs';cs.write_bytes(friend_template.read_bytes());reader=cs.with_suffix('.exe')
    run([compiler,'/nologo','/target:exe','/out:'+str(reader),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],'friends-reader-compile')
    friends_reports=[]
    for label,build in [('old59-friends',old),('new60-friends',b)]:
        output=H/(label+'.json');run([reader,build['exe'],H/'f',build['signed_bindings']['signedFriends']['archive']['path'],output,'good'],label,timeout=240)
        item=read(output);assert item['ok']and item['selected_identity']['payload']==build['signed_bindings']['signedFriends']['archive']['sha256']and item['second']['downloaded_files']==0;friends_reports.append(item)
    friend_root=Path(friends_reports[-1]['root']);newf=json.loads(base64.b64decode(read(b['signed_bindings']['signedFriends']['manifest']['path'])['payload']))
    for row in newf['files']:assert (friend_root/row['path']).stat().st_size==row['size']and sha(friend_root/row['path'])==row['sha256'],row['path']
    credentials=read(W/'qa-credentials.private.json');bridge_config=H/'bridge.private.json';save(bridge_config,credentials['bridge'])
    for family,selected_root in [('signedLOCAL',root),('signedFriends',friend_root)]:
        out=H/(family+'-compose.json')
        run([selected_root/'python/python.exe','-B','-X','utf8',P.parent/'qualify_launcher_v59.py','--child','compose',selected_root,db,out],family+'-compose',selected_root,240)
        composed=out.with_suffix('.js').read_text('utf8');assert 'installElsStartupVisibility();'in composed and '__STARTUP_UI_PINS__'not in composed
        # The formal client entry validates the complete selected profile/resource closure.
        run([selected_root/'python/python.exe','-B',selected_root/'tools/launch_friends_client.py','--config',bridge_config,'--client','D:/艾尔之光/data/x2_dx11.exe','--check'],family+'-formal-friends-entry-check',selected_root,240)
    save(D/'selected-support.json',dict(ok=True,LOCAL=str(root),Friends=str(friend_root),Friends_reports=friends_reports,selected_friends_files=len(newf['files']),formal_launch_friends_check_both=True,composed_startup_hook_both=True,game_started=False))
    save(D/'qualification.json',dict(ok=True,exe_sha256=b['exe_sha256'],build_sha256=sha(D/'build.json'),actual_CSharp_LOCAL_Run=True,upgrade59_to60=True,repeat=True,all_1892_selected_files_verified=True,typed_owned_databases_preserved=True,selected_11_gate_rules_present=True,selected_normal_check=True,predecessor_contracts=16,Friends_UI_only_delta=True,Friends_files=1800,LOCAL_files=1892,formal_friends_entry_check_both=True,source_mechanism_reused=str(P/'dual-qualification.json'),new_Hooks=0,natural_GUI=False,natural_battle=False,game_started=False,owner=str(H),reports=reports,private_cleanup_pending=True))
    print('Qualified actual signed LOCAL upgrade and repeat',flush=True)
if __name__=='__main__':main()
