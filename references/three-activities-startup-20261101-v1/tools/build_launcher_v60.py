"""Signed LOCAL carrier update; original EXE/KOM and Friends payload unchanged."""
from pathlib import Path
import ast,base64,copy,hashlib,importlib.util,inspect,json,os,re,subprocess,zipfile,zlib
R=Path('G:/els');W=Path(__file__).parent;P=R/'analysis/all-ground-item-models-20261101-v1/launcher-v59';D=W/'launcher-v60';S=D/'source'
MANAGED='local-git-first-run-activities-startup-20261101-v1'
PROFILE='tools/client_compatibility_profiles.json'
ORIGINAL=R/'analysis/distorted-memory-gate-20261101-v1'
UI=R/'analysis/startup-ui-hide-20261101-v1'
DELTA=set(json.loads((W/'publication/release-contract.json').read_bytes())['local']['delta'][i]['path']for i in range(14))
DELTA|={r['path']for r in json.loads((R/'analysis/shop-rare-navy-20261101-v1/publication/release-contract.json').read_bytes())['local']['delta']}
DELTA|={'els_server/domain/public_controller_rules.py','els_server/domain/story_controller_retirements.py','els_server/domain/friends_story_retirements.py','els_server/domain/field_travel.py','els_server/protocol/field_boss_messages.py'}
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def one(t,a,b):assert t.count(a)==1,(a,t.count(a));return t.replace(a,b,1)
def load(name,path):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
def put(n,b):
    p=S/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b if isinstance(b,bytes)else b.encode())
def file_rows(files):return [dict(path=n,size=len(b),sha256=sha(b))for n,b in sorted(files.items())]
def rowhash(rows):return sha(json.dumps(sorted(rows,key=lambda r:r['path']),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
def main():
    old=read(P/'build.json');parent=read(R/'releases/launchers/current.json');assert parent['V']==59 and parent['sha256']==old['exe_sha256']
    contract=read(W/'publication/release-contract.json')['local'];point=read(R/'releases/local/current.json');assert point['release']==contract['parent']['release'];raw=R/contract['root']
    # Keep latest three-file gate implementation together; other raw/signed mode differences stay untouched.
    assert read(W/'publication/local-install/qualification.json')['ok']
    assert read(W/'startup-independent-review.json')['result']=='PASS'
    readback=read(R/'analysis/elrian-sanctum-door-20261101-v1/delivery-v1/actual-installed-readback.json');assert readback['ok']
    business={r['path']:r for r in read(raw/'local-business-manifest.json')['files']}
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key=serialization.load_pem_private_key((Path(os.environ['LOCALAPPDATA'])/'ElsFriends-Publisher/launcher-update-signing.pem').read_bytes(),None)
    ref=old['signed_bindings']['signedLOCAL'];eb=Path(ref['manifest']['path']).read_bytes();assert sha(eb)==ref['manifest']['sha256'];env=json.loads(eb);pb=base64.b64decode(env['payload'],validate=True)
    key.public_key().verify(base64.b64decode(env['signature'],validate=True),pb,padding.PKCS1v15(),hashes.SHA256());definition=json.loads(pb)
    archive=Path(ref['archive']['path']);assert sha(archive.read_bytes())==ref['archive']['sha256']==definition['archive']['sha256']
    with zipfile.ZipFile(archive)as z:files={n:z.read(n)for n in z.namelist()};assert len(z.namelist())==len(files)==1887
    assert file_rows(files)==definition['files'];before=dict(files);oldmeta=json.loads(files['local-bootstrap-source.json'])
    for n in DELTA:
        b=(raw/n).read_bytes();assert business[n]==dict(path=n,size=len(b),sha256=sha(b));files[n]=b
    verifier=load('contract',ORIGINAL/'git-source/tools/check_controller_quest_gates.py');rules=verifier.literal_rules(raw/'els_server/domain/public_controller_rules.py');cases=read(ORIGINAL/'git-source/references/controller-quest-gates-20261101-v1/cases.json');assert all(c in rules for c in cases)
    # Formal Git source identity remains the existing reviewed cohort.
    predecessor=json.loads(zlib.decompress(base64.b64decode((P/'source/resources/registered-ground-predecessor.txt').read_bytes(),validate=True)))
    formal=predecessor['formal_rows'];assert len(formal)==1342 and rowhash(formal)==oldmeta['source_files_sha256']
    packed=zlib.compress(enc(dict(envelope_base64=base64.b64encode(eb).decode(),metadata_base64=base64.b64encode(before['local-bootstrap-source.json']).decode(),formal_rows=formal)),9)
    predtext=base64.b64encode(packed);pred=dict(encoding='embedded-zlib-base64-v59-public-v1',sha256=sha(packed))
    meta=copy.deepcopy(oldmeta);meta['release']=MANAGED;meta['upgrade_from']=dict(schema=1,kind='exact-v59-transitive-to-quest-gates-v1',to_runtime_release=MANAGED,to_source_release=oldmeta['source_release'],to_source_formal_manifest_sha256=oldmeta['source_formal_manifest_sha256'],v59_predecessor=pred)
    for row in read(UI/'update-delta-manifest.json')['modes']['local']['files']:
        data=(UI/'update-delta/local'/row['path']).read_bytes();assert sha(data)==row['sha256'];files[row['path']]=data
    profile=json.loads(files[PROFILE])
    for entry in profile['profiles']:
        for path in entry.get('artifacts',{}):assert path in files;entry['artifacts'][path]=sha(files[path])
    files[PROFILE]=enc(profile)
    formal_index={r['path']:r for r in formal}
    meta['support_overrides']=[dict(path=n,source_sha256=r['sha256'],runtime_sha256=sha(files[n]))for n,r in sorted(formal_index.items())if n!='config/server.toml'and sha(files[n])!=r['sha256']]
    additions={r['path']for r in oldmeta['support_additions']}|(set(files)-set(before))
    additions-=set(formal_index)|{'local-bootstrap-source.json'}
    meta['support_additions']=[dict(path=n,runtime_sha256=sha(files[n]))for n in sorted(additions)]
    assert DELTA<={r['path']for r in meta['support_overrides']+meta['support_additions']}
    files['local-bootstrap-source.json']=enc(meta)
    changed={n for n in files if files[n]!=before.get(n)}
    assert changed==DELTA|{'local-bootstrap-source.json'}|{r['path']for r in read(UI/'update-delta-manifest.json')['modes']['local']['files']},changed
    assert len(files)==1892
    assert not D.exists();S.mkdir(parents=True)
    for n,row in old['source_inventory'].items():
        b=(P/'source'/n).read_bytes();assert len(b)==row['size']and sha(b)==row['sha256'];put(n,b)
    put('resources/quest-gates-predecessor.txt',predtext)
    tmp=D/'signedLOCAL.zip'
    with zipfile.ZipFile(tmp,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for n,b in sorted(files.items()):
            zi=zipfile.ZipInfo(n,(2026,11,1,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o100644<<16;z.writestr(zi,b)
    target=D/('runtime-'+sha(tmp.read_bytes())+'.zip');tmp.rename(target)
    newdef=copy.deepcopy(definition);newdef.update(archive=dict(file=target.name,size=target.stat().st_size,sha256=sha(target.read_bytes())),files=file_rows(files))
    pb=json.dumps(newdef,separators=(',',':')).encode();signed=json.dumps(dict(payload=base64.b64encode(pb).decode(),signature=base64.b64encode(key.sign(pb,padding.PKCS1v15(),hashes.SHA256())).decode()),separators=(',',':')).encode();ep=D/'signedLOCAL.signed.json';ep.write_bytes(signed);put('resources/quest-gates-signedLOCAL.signed.json',signed)
    binding=dict(manifest=dict(path=str(ep),sha256=sha(signed)),archive=dict(path=str(target),sha256=sha(target.read_bytes())))
    friends_ref=old['signed_bindings']['signedFriends']
    feb=Path(friends_ref['manifest']['path']).read_bytes();assert sha(feb)==friends_ref['manifest']['sha256']
    fe=json.loads(feb);fpb=base64.b64decode(fe['payload'],validate=True);key.public_key().verify(base64.b64decode(fe['signature'],validate=True),fpb,padding.PKCS1v15(),hashes.SHA256());fd=json.loads(fpb)
    fa=Path(friends_ref['archive']['path']);assert sha(fa.read_bytes())==friends_ref['archive']['sha256']
    with zipfile.ZipFile(fa)as z:friends={n:z.read(n)for n in z.namelist()}
    assert file_rows(friends)==fd['files'];oldfriends=dict(friends)
    for row in read(UI/'update-delta-manifest.json')['modes']['friends']['files']:
        data=(UI/'update-delta/friends'/row['path']).read_bytes();assert sha(data)==row['sha256'];friends[row['path']]=data
    assert {n for n in friends if friends[n]!=oldfriends.get(n)}=={r['path']for r in read(UI/'update-delta-manifest.json')['modes']['friends']['files']}
    assert len(friends)==1800
    tmp=D/'signedFriends.zip'
    with zipfile.ZipFile(tmp,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for n,b in sorted(friends.items()):
            zi=zipfile.ZipInfo(n,(2026,11,1,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o100644<<16;z.writestr(zi,b)
    ft=D/('runtime-'+sha(tmp.read_bytes())+'.zip');tmp.rename(ft)
    fd.update(archive=dict(file=ft.name,size=ft.stat().st_size,sha256=sha(ft.read_bytes())),files=file_rows(friends))
    fpb=json.dumps(fd,separators=(',',':')).encode();fsigned=json.dumps(dict(payload=base64.b64encode(fpb).decode(),signature=base64.b64encode(key.sign(fpb,padding.PKCS1v15(),hashes.SHA256())).decode()),separators=(',',':')).encode()
    fm=D/'signedFriends.signed.json';fm.write_bytes(fsigned);put('resources/quest-gates-signedFriends.signed.json',fsigned)
    friend_binding=dict(manifest=dict(path=str(fm),sha256=sha(fsigned)),archive=dict(path=str(ft),sha256=sha(ft.read_bytes())))
    oldbuilder=load('builder59',P.parent/'build_launcher_v59.py')
    code=inspect.getsource(oldbuilder.new_bootstrap)
    code=code.replace('registered_ground_v58_predecessors','quest_gates_v59_predecessors').replace('ground_fashion_v57_predecessors','registered_ground_v58_predecessors').replace("old_meta['upgrade_from']['v57_predecessor']","old_meta['upgrade_from']['v58_predecessor']")
    code=code.replace('len(contracts)==14','len(contracts)==15').replace('registered-ground-predecessor.txt','quest-gates-predecessor.txt').replace('V58','V59')
    code=code.replace('"\'v57_predecessor\'} and type(p[\'schema\'])","\'v58_predecessor\'} and type(p[\'schema\'])"','"\'v58_predecessor\'} and type(p[\'schema\'])","\'v59_predecessor\'} and type(p[\'schema\'])"')
    # Rewrite the two exact old-policy call-site literals after updating helper implementation.
    code=code.replace('"contracts=registered_ground_v58_predecessors(p[\'v57_predecessor\'])","contracts=quest_gates_v59_predecessors(p[\'v58_predecessor\'])"','"contracts=registered_ground_v58_predecessors(p[\'v58_predecessor\'])","contracts=quest_gates_v59_predecessors(p[\'v59_predecessor\'])"')
    ns=dict(oldbuilder.__dict__);ns.update(MANAGED=MANAGED);exec(code,ns)
    bootstrap=ns['new_bootstrap']((P/'source/resources/registered-ground-local-bootstrap.py').read_text('utf8'),meta,newdef,oldmeta,definition,eb,before,predtext,packed,pred,formal,files)
    put('resources/quest-gates-local-bootstrap.py',bootstrap)
    cohort=(P/'source/RegisteredGroundRuntimeCohort.cs').read_text('utf8').replace('RegisteredGroundRuntimeCohort','QuestGatesRuntimeCohort').replace(oldmeta['release'],MANAGED).replace('ElsFriends.RegisteredGroundLocal','ElsFriends.QuestGatesLocal')
    values=dict(LocalPayload=binding['archive']['sha256'],LocalEnvelope=binding['manifest']['sha256'],LocalMetadata=sha(files['local-bootstrap-source.json']),BootstrapHash=sha(bootstrap.encode()),FriendsPayload=friend_binding['archive']['sha256'],FriendsEnvelope=friend_binding['manifest']['sha256'],FriendsProfileHash=sha(friends[PROFILE]))
    for n,v in values.items():cohort,count=re.subn(r'\b'+n+r'="[a-f0-9]{64}"',n+'="'+v+'"',cohort);assert count==1,n
    cohort=cohort.replace('LocalCount=1887,FriendsCount=1798','LocalCount=1892,FriendsCount=1800').replace('ElsFriends.RegisteredGroundFriendsRuntimeFiles','ElsFriends.QuestGatesFriendsRuntimeFiles')
    put('QuestGatesRuntimeCohort.cs',cohort)
    # Keep Friends definition and every support byte on V59.
    p=S/'ComponentRuntime.cs';t=p.read_text('utf8')
    for field in ('RequireLocal','LocalPayload','LocalCount','LocalMetadata','LocalResource','LocalEnvelope'):t=t.replace('RegisteredGroundRuntimeCohort.'+field,'QuestGatesRuntimeCohort.'+field)
    start=t.index('        static RuntimeDefinition SelectRegisteredGroundFriendsDefinition()');end=t.index('        static RuntimeDefinition SelectShopFriendsDefinition()',start)
    part=t[start:end].replace('RegisteredGroundRuntimeCohort.','QuestGatesRuntimeCohort.')
    t=t[:start]+part+t[end:]
    put('ComponentRuntime.cs',t)
    t=(S/'LocalBootstrap.cs').read_text('utf8');t=one(t,'            if(RegisteredGroundRuntimeCohort.RequireCurrentDirection(pointer,source))return;','            if(QuestGatesRuntimeCohort.RequireCurrentDirection(pointer,source))return;\n            if(RegisteredGroundRuntimeCohort.RequireCurrentDirection(pointer,source))return;')
    for a,b in [('source.Accessory?RegisteredGroundRuntimeCohort.ManagedRelease','source.Accessory?QuestGatesRuntimeCohort.ManagedRelease'),('selection.Accessory?RegisteredGroundRuntimeCohort.BootstrapResource','selection.Accessory?QuestGatesRuntimeCohort.BootstrapResource'),('selection.Accessory?RegisteredGroundRuntimeCohort.BootstrapHash','selection.Accessory?QuestGatesRuntimeCohort.BootstrapHash')]:t=one(t,a,b)
    t=one(t,'            Program.PrivateWrite(script,text);','            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"quest-gates-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.QuestGatesPredecessor","'+sha(predtext)+'"));\n            Program.PrivateWrite(script,text);');put('LocalBootstrap.cs',t)
    put('AutoUpdate.cs',one((S/'AutoUpdate.cs').read_text('utf8'),'public const int Version = 59;','public const int Version = 60;'))
    resources=copy.deepcopy(old['resources'])
    for name,label in [('quest-gates-signedFriends.signed.json','QuestGatesFriendsRuntimeFiles'),('quest-gates-signedLOCAL.signed.json','QuestGatesLocalRuntimeFiles'),('quest-gates-local-bootstrap.py','QuestGatesLocalBootstrap'),('quest-gates-predecessor.txt','QuestGatesPredecessor')]:resources.append(dict(path='resources/'+name,name='ElsFriends.'+label,sha256=sha((S/'resources'/name).read_bytes())))
    for row in resources:assert sha((S/row['path']).read_bytes())==row['sha256']
    exe=D/'ElsFriends-V60.exe';compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    argv=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(exe),'/win32icon:'+str(R/'launcher/assets/launcher.ico'),'/win32manifest:'+str(S/'app.manifest')]+['/resource:'+str(S/r['path'])+','+r['name']for r in resources]+['/reference:'+n for n in('System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll')]+[str(p)for p in sorted(S.glob('*.cs'))]
    q=subprocess.run(argv,capture_output=True,timeout=90,creationflags=0x08000000);(D/'compile.txt').write_bytes(q.stdout+q.stderr);assert q.returncode==0,q.stdout.decode(errors='replace')[-2000:]
    signer=load('signer',R/'analysis/launcher-autoupdate-01a1533c-20261019-v1/sign_release.py');latest=signer.sign(exe,60,D/'latest.json')
    result=dict(ok=True,version=60,exe=str(exe),exe_sha256=sha(exe.read_bytes()),size=exe.stat().st_size,latest=latest,parent=parent,parent_exe_sha256=old['exe_sha256'],signed_bindings=dict(signedLOCAL=binding,signedFriends=friend_binding),resources=resources,component_delta=dict(signedLOCAL=sorted(changed),signedFriends=sorted(n for n in friends if friends[n]!=oldfriends.get(n))),source_inventory={p.relative_to(S).as_posix():dict(size=p.stat().st_size,sha256=sha(p.read_bytes()))for p in S.rglob('*')if p.is_file()},raw_local_pointer=dict(path=str(R/'releases/local/current.json'),sha256=sha((R/'releases/local/current.json').read_bytes())),raw_delta=[business[n]for n in sorted(DELTA)],published=False,original_EXE_KOM_changes=0,new_Hooks=1,independent_Hook_review=dict(path=str(W/'startup-independent-review.json'),sha256=sha((W/'startup-independent-review.json').read_bytes())),player_database_changes=0)
    (D/'build.json').write_bytes(enc(result));print(json.dumps(dict(ok=True,exe_sha256=result['exe_sha256'],LOCAL_changed=len(changed),Friends_changed=4)))
if __name__=='__main__':main()
