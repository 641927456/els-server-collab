"""Build the existing signed launcher with this reviewed support closure."""
from pathlib import Path
import ast,base64,copy,hashlib,importlib.util,json,os,re,subprocess,zipfile,zlib
R=Path('G:/els');W=Path(__file__).resolve().parent;P=R/'analysis/launcher-ground-fashion-signsync-20261101-v1/launcher-v58'
SOURCEREPO=R/'analysis/ground-model-repair-20261101-v1/git-source';A=SOURCEREPO/'references/registered-ground-items-20261101-v1'
D=W/'launcher-v59';S=D/'source';MANAGED='local-git-first-run-registered-ground-items-20261101-v1';PROFILE='tools/client_compatibility_profiles.json'
MODE={'config/server.toml','config/friends-server.toml','state/friends-client.example.json','tools/launch_client.py','tools/launch_friends_client.py','tools/launch_integrated_local.py','tools/local_fresh_state.py','local-bootstrap-source.json'}
sha=lambda b:hashlib.sha256(b).hexdigest();read=lambda p:json.loads(Path(p).read_bytes());enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def one(t,a,b):assert t.count(a)==1,(a[:80],t.count(a));return t.replace(a,b,1)
def scalar(t,values):
    lines=t.splitlines(True);nodes=[n for n in ast.parse(t).body if isinstance(n,ast.Assign)and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)and n.targets[0].id in values]
    assert{n.targets[0].id for n in nodes}==set(values)
    for n in reversed(nodes):lines[n.lineno-1:n.end_lineno]=[n.targets[0].id+' = '+repr(values[n.targets[0].id])+'\n']
    return''.join(lines)
def rows(d):return{r['path']:{k:r[k]for k in('path','size','sha256')}for r in d['files']}
def file_rows(f):return[dict(path=n,size=len(b),sha256=sha(b))for n,b in sorted(f.items())]
def rowhash(f):return sha(json.dumps(sorted(f,key=lambda r:r['path']),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
def put(n,b):p=S/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b if isinstance(b,bytes)else b.encode())
def new_bootstrap(t,meta,definition,oldmeta,olddef,eb,oldfiles,predtext,packed,pred,formal,newfiles):
    oldkey=tuple(oldmeta[k]for k in('release','source_release','source_formal_manifest_sha256'))
    helper='''def registered_ground_v58_predecessors(entry):
    import base64,zlib
    need(entry==PRED,'Exact V58 predecessor required')
    text=no_links(Path(__file__).resolve().with_name('registered-ground-predecessor.txt')).read_bytes()
    need(len(text)==TEXT_SIZE and hashlib.sha256(text).hexdigest()==TEXT_SHA,'V58 predecessor resource changed')
    packed=base64.b64decode(text,validate=True);need(hashlib.sha256(packed).hexdigest()==PACK_SHA,'V58 packed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(packed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V58 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V58 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()==ENVELOPE_SHA and hashlib.sha256(mb).hexdigest()==META_SHA,'V58 predecessor identity')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==OLD_COUNT and signed['archive']['sha256']==ARCHIVE_SHA,'V58 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']==FORMAL_SHA,'V58 source rows changed')
    key=tuple(old_meta[k]for k in('release','source_release','source_formal_manifest_sha256'));need(key==OLD_KEY,'V58 source key changed')
    contracts=ground_fashion_v57_predecessors(old_meta['upgrade_from']['v57_predecessor'])
    need(len(contracts)==14 and key not in contracts,'V58 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

'''
    values=dict(PRED=pred,TEXT_SIZE=len(predtext),TEXT_SHA=sha(predtext),PACK_SHA=sha(packed),ENVELOPE_SHA=sha(eb),META_SHA=sha(oldfiles['local-bootstrap-source.json']),OLD_COUNT=len(olddef['files']),ARCHIVE_SHA=olddef['archive']['sha256'],FORMAL_SHA=oldmeta['source_files_sha256'],OLD_KEY=oldkey)
    for token,value in values.items():helper=re.sub(r'\b'+token+r'\b',lambda m:repr(value),helper)
    t=one(t,'def repair_policy(metadata,new_rows):',helper+'def repair_policy(metadata,new_rows):')
    t=one(t,"'v57_predecessor'} and type(p['schema'])","'v58_predecessor'} and type(p['schema'])")
    t=one(t,"contracts=ground_fashion_v57_predecessors(p['v57_predecessor'])","contracts=registered_ground_v58_predecessors(p['v58_predecessor'])")
    constants={n.targets[0].id:ast.literal_eval(n.value)for n in ast.parse(t).body if isinstance(n,ast.Assign)and isinstance(n.targets[0],ast.Name)and n.targets[0].id in('OVERRIDES','ADDITIONS','REPAIR_RECOVERY_GUARD_PAYLOADS')}
    for n in constants['REPAIR_RECOVERY_GUARD_PAYLOADS']:assert newfiles[n]==oldfiles[n],('Existing guarded source changed',n)
    count=len(definition['files'])
    t=scalar(t,dict(OVERRIDES=constants['OVERRIDES']|{r['path']for r in meta['support_overrides']},ADDITIONS=constants['ADDITIONS']|{r['path']for r in meta['support_additions']},
        REPAIR_RUNTIME_RELEASE=MANAGED,REPAIR_RUNTIME_COUNT=count,REPAIR_RUNTIME_WITHOUT_METADATA=rowhash([r for r in definition['files']if r['path']!='local-bootstrap-source.json']),
        REPAIR_OVERRIDES=meta['support_overrides'],REPAIR_ADDITIONS=meta['support_additions'],REPAIR_POLICY_KIND=meta['upgrade_from']['kind']))
    tree=ast.parse(t);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='managed_is_old');part=ast.get_source_segment(t,node)
    line=next(x for x in part.splitlines()if x.strip().startswith('return key in '));t=one(t,line,line+'+['+repr(oldkey)+']')
    t=one(t,'need(len(new_rows)=='+str(len(olddef['files']))+' and len(formal)==1342','need(len(new_rows)=='+str(count)+' and len(formal)==1342')
    t=one(t,"need(len(installed)=="+str(len(olddef['files'])+2)+",'Signed LOCAL recovery must retain generated config and marker')","need(len(installed)=="+str(count+2)+",'Signed LOCAL recovery must retain generated config and marker')")
    assert 'def repair_original_restore_allowed(j,current_state):'in t and 'return False'in t
    ast.parse(t);return t

def main():
    old=read(P/'build.json');parent=read(R/'releases/launchers/current.json');assert parent['V']==58 and parent['sha256']==old['exe_sha256']
    delivery=read(W/'delivery-v1/actual-installed-readback.json');assert delivery['ok']
    review=read(W/'independent-review/review.json');assert review['result']=='PASS'and review['assessed_head']=='730fd8c99846e218687f1ce7d69b1f45c3dca5c5'
    point=read(R/'releases/local/current.json');assert point['release']=='local-registered-ground-items-20261101-v1';root=R/point['path']
    raw=rows(read(root/'client-bundle-manifest.json'));business=rows(read(root/'local-business-manifest.json'));assert len(raw)==1887
    rawfiles={n:(root/n).read_bytes()for n in raw};assert rows({'files':file_rows(rawfiles)})==raw
    assert all(raw[n]==r for n,r in business.items())
    contract=read(W/'delivery-v1/publication/release-contract.json');delta=contract['local']['delta'];assert len(delta)==7
    for d in delta:assert raw[d['path']]=={k:d[k]for k in('path','size','sha256')}
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key=serialization.load_pem_private_key((Path(os.environ['LOCALAPPDATA'])/'ElsFriends-Publisher/launcher-update-signing.pem').read_bytes(),None)
    def load(binding):
        eb=Path(binding['manifest']['path']).read_bytes();assert sha(eb)==binding['manifest']['sha256'];env=json.loads(eb);pb=base64.b64decode(env['payload'],validate=True)
        key.public_key().verify(base64.b64decode(env['signature'],validate=True),pb,padding.PKCS1v15(),hashes.SHA256());definition=json.loads(pb)
        archive=Path(binding['archive']['path']);assert sha(archive.read_bytes())==binding['archive']['sha256']==definition['archive']['sha256']
        with zipfile.ZipFile(archive)as z:files={n:z.read(n)for n in z.namelist()};assert len(z.namelist())==len(files)
        assert rows({'files':file_rows(files)})==rows(definition);return eb,definition,files
    oldenv,olddef,oldlocal=load(old['signed_bindings']['signedLOCAL']);oldmeta=json.loads(oldlocal['local-bootstrap-source.json'])
    formal=json.loads(zlib.decompress(base64.b64decode((P/'source/resources/map-stages-predecessor.txt').read_bytes(),validate=True)))['formal_rows']
    assert len(formal)==1342 and rowhash(formal)==oldmeta['source_files_sha256'];formal_index=rows({'files':formal})
    inherited={'els_server/storage/mail_attachments.py','els_server/storage/item_instances.py','els_server/protocol/mail_notifications_2026.py'}
    changed={n for n in rawfiles if n in oldlocal and n not in MODE|{PROFILE}and rawfiles[n]!=oldlocal[n]}
    assert changed=={d['path']for d in delta if d['parent_sha256']is not None and d['path']!=PROFILE}|inherited,changed
    assert(set(raw)-set(oldlocal))-MODE=={'tools/native_ground_models.py','tools/native_ground_models.js'}
    packed=zlib.compress(enc(dict(envelope_base64=base64.b64encode(oldenv).decode(),metadata_base64=base64.b64encode(oldlocal['local-bootstrap-source.json']).decode(),formal_rows=formal)),9)
    predtext=base64.b64encode(packed);pred=dict(encoding='embedded-zlib-base64-v58-public-v1',sha256=sha(packed))
    meta=copy.deepcopy(oldmeta);meta['release']=MANAGED
    meta['upgrade_from']=dict(schema=1,kind='exact-v58-transitive-to-registered-ground-v1',to_runtime_release=MANAGED,to_source_release=oldmeta['source_release'],to_source_formal_manifest_sha256=oldmeta['source_formal_manifest_sha256'],v58_predecessor=pred)
    assert not D.exists();S.mkdir(parents=True)
    for n,row in old['source_inventory'].items():b=(P/'source'/n).read_bytes();assert len(b)==row['size']and sha(b)==row['sha256'];put(n,b)
    put('resources/registered-ground-predecessor.txt',predtext)
    support=['tools/native_cache_sync.py','tools/native_ground_models.py','tools/native_ground_models.js'];bindings={};definitions={};changes={};composition={}
    before_sha=next(r['before_sha256']for r in read(A/'source-contract.json')['files']if r['path']=='tools/native_cache_sync.py')
    for family in('signedLOCAL','signedFriends'):
        eb,definition,files=load(old['signed_bindings'][family]);before=dict(files)
        assert sha(before['tools/native_cache_sync.py'])==before_sha
        if family=='signedLOCAL':
            for n,b in rawfiles.items():
                if n in MODE|{PROFILE}:continue
                if n.lower().endswith(('.exe','.dll','.kom')):assert before.get(n)==b,('Binary change',n)
                files[n]=b
        else:
            for n in support:files[n]=(A/'source/support/common'/n).read_bytes()
        profile=json.loads(files[PROFILE]);found=0
        for row in profile['profiles']:
            for n in row.get('artifacts',{}):assert n in files;row['artifacts'][n]=sha(files[n])
            if row['id']=='cn-dx11-6c6b5180':
                found+=1
                for n in support:row['artifacts'][n]=sha(files[n])
        assert found==1;files[PROFILE]=enc(profile)
        for n in MODE-{'local-bootstrap-source.json'}:assert files.get(n)==before.get(n),(family,n)
        if family=='signedLOCAL':
            meta['support_overrides']=[dict(path=n,source_sha256=r['sha256'],runtime_sha256=sha(files[n]))for n,r in sorted(formal_index.items())if n!='config/server.toml'and sha(files[n])!=r['sha256']]
            additions=({r['path']for r in oldmeta['support_additions']}|set(business)|set(support)|{n for n in raw if n not in before})-set(formal_index)-MODE
            additions|={r['path']for r in oldmeta['support_additions']}
            meta['support_additions']=[dict(path=n,runtime_sha256=sha(files[n]))for n in sorted(additions)]
            files['local-bootstrap-source.json']=enc(meta);final_local=files
        else:assert{n for n,b in files.items()if b!=before.get(n)}==set(support)|{PROFILE}
        assert len(files)==(1887 if family=='signedLOCAL'else 1798)
        temp=D/(family+'.zip')
        with zipfile.ZipFile(temp,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
            for n,b in sorted(files.items()):zi=zipfile.ZipInfo(n,(2026,11,1,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o100644<<16;z.writestr(zi,b)
        archive=D/('runtime-'+sha(temp.read_bytes())+'.zip');temp.rename(archive)
        definition.update(archive=dict(file=archive.name,size=archive.stat().st_size,sha256=sha(archive.read_bytes())),files=file_rows(files))
        pb=json.dumps(definition,separators=(',',':')).encode();signed=json.dumps(dict(payload=base64.b64encode(pb).decode(),signature=base64.b64encode(key.sign(pb,padding.PKCS1v15(),hashes.SHA256())).decode()),separators=(',',':')).encode()
        ep=D/(family+'.signed.json');ep.write_bytes(signed);put('resources/registered-ground-'+family+'.signed.json',signed)
        bindings[family]=dict(manifest=dict(path=str(ep),sha256=sha(signed)),archive=dict(path=str(archive),sha256=sha(archive.read_bytes())))
        definitions[family]=definition;changes[family]=[n for n,b in files.items()if b!=before.get(n)]
        composition[family]=dict(preserved_mode_files=sorted(n for n in MODE if n in before),client_dependency_delta=support+[PROFILE],family_own_profile_rebound=True)
    bootstrap=new_bootstrap((P/'source/resources/ground-fashion-local-bootstrap.py').read_text('utf8'),meta,definitions['signedLOCAL'],oldmeta,olddef,oldenv,oldlocal,predtext,packed,pred,formal,final_local)
    put('resources/registered-ground-local-bootstrap.py',bootstrap)
    cohort=(P/'source/GroundFashionRuntimeCohort.cs').read_text('utf8').replace('GroundFashionRuntimeCohort','RegisteredGroundRuntimeCohort').replace('ElsFriends.GroundFashion','ElsFriends.RegisteredGround').replace('ElsFriends.MapStagesFriendsRuntimeFiles','ElsFriends.RegisteredGroundFriendsRuntimeFiles').replace(oldmeta['release'],MANAGED)
    cohort=one(cohort,'LocalCount=1885,FriendsCount=1796','LocalCount=1887,FriendsCount=1798')
    values=dict(LocalPayload=bindings['signedLOCAL']['archive']['sha256'],LocalEnvelope=bindings['signedLOCAL']['manifest']['sha256'],LocalMetadata=sha(final_local['local-bootstrap-source.json']),BootstrapHash=sha(bootstrap.encode()),FriendsPayload=bindings['signedFriends']['archive']['sha256'],FriendsEnvelope=bindings['signedFriends']['manifest']['sha256'],FriendsProfileHash=next(r['sha256']for r in definitions['signedFriends']['files']if r['path']==PROFILE))
    for n,v in values.items():cohort,count=re.subn(r'\b'+n+r'="[a-f0-9]{64}"',n+'="'+v+'"',cohort);assert count==1,n
    put('RegisteredGroundRuntimeCohort.cs',cohort)
    p=S/'ComponentRuntime.cs';put('ComponentRuntime.cs',p.read_text('utf8').replace('GroundFashionRuntimeCohort','RegisteredGroundRuntimeCohort').replace('SelectGroundFashionFriendsDefinition','SelectRegisteredGroundFriendsDefinition'))
    p=S/'LocalBootstrap.cs';t=p.read_text('utf8');t=one(t,'            if(GroundFashionRuntimeCohort.RequireCurrentDirection(pointer,source))return;','            if(RegisteredGroundRuntimeCohort.RequireCurrentDirection(pointer,source))return;\n            if(GroundFashionRuntimeCohort.RequireCurrentDirection(pointer,source))return;')
    for a,b in[('source.Accessory?GroundFashionRuntimeCohort.ManagedRelease','source.Accessory?RegisteredGroundRuntimeCohort.ManagedRelease'),('selection.Accessory?GroundFashionRuntimeCohort.BootstrapResource','selection.Accessory?RegisteredGroundRuntimeCohort.BootstrapResource'),('selection.Accessory?GroundFashionRuntimeCohort.BootstrapHash','selection.Accessory?RegisteredGroundRuntimeCohort.BootstrapHash')]:t=one(t,a,b)
    t=one(t,'            Program.PrivateWrite(script,text);','            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"registered-ground-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.RegisteredGroundPredecessor","'+sha(predtext)+'"));\n            Program.PrivateWrite(script,text);');put('LocalBootstrap.cs',t)
    put('AutoUpdate.cs',one((S/'AutoUpdate.cs').read_text('utf8'),'public const int Version = 58;','public const int Version = 59;'))
    resources=copy.deepcopy(old['resources'])
    for name,label in[('registered-ground-signedLOCAL.signed.json','RegisteredGroundLocalRuntimeFiles'),('registered-ground-signedFriends.signed.json','RegisteredGroundFriendsRuntimeFiles'),('registered-ground-local-bootstrap.py','RegisteredGroundLocalBootstrap'),('registered-ground-predecessor.txt','RegisteredGroundPredecessor')]:resources.append(dict(path='resources/'+name,name='ElsFriends.'+label,sha256=sha((S/'resources'/name).read_bytes())))
    for r in resources:assert sha((S/r['path']).read_bytes())==r['sha256']
    exe=D/'ElsFriends-V59.exe';compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    argv=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(exe),'/win32icon:'+str(R/'launcher/assets/launcher.ico'),'/win32manifest:'+str(S/'app.manifest')]+['/resource:'+str(S/r['path'])+','+r['name']for r in resources]+['/reference:'+n for n in('System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll')]+[str(p)for p in sorted(S.glob('*.cs'))]
    q=subprocess.run(argv,capture_output=True,timeout=90,creationflags=0x08000000);(D/'compile.txt').write_bytes(q.stdout+q.stderr);assert q.returncode==0,q.stdout.decode(errors='replace')[-2000:]
    spec=importlib.util.spec_from_file_location('registered_signer',R/'analysis/launcher-autoupdate-01a1533c-20261019-v1/sign_release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);latest=m.sign(exe,59,D/'latest.json')
    launcher_contract=dict(ready_for_launcher_build=True,delta=[{k:rows(definitions['signedLOCAL'])[d['path']][k]for k in('path','size','sha256')}for d in delta],raw_local_delta=delta,
        actual_delivery_evidence=dict(path=str(W/'delivery-v1/actual-installed-readback.json'),sha256=sha((W/'delivery-v1/actual-installed-readback.json').read_bytes())),
        actual_raw_current=dict(path=str(R/'releases/local/current.json'),sha256=sha((R/'releases/local/current.json').read_bytes())),independent_review=review)
    (W/'launcher-contract.json').write_bytes(enc(launcher_contract))
    result=dict(ok=True,version=59,exe=str(exe),exe_sha256=sha(exe.read_bytes()),size=exe.stat().st_size,latest=latest,signed_bindings=bindings,resources=resources,component_delta=changes,parent=parent,parent_exe_sha256=old['exe_sha256'],
        source_inventory={p.relative_to(S).as_posix():dict(size=p.stat().st_size,sha256=sha(p.read_bytes()))for p in S.rglob('*')if p.is_file()},published=False,original_EXE_KOM_changes=0,Git_merge=False,source_candidate_PR=724,source_candidate_head='730fd8c99846e218687f1ce7d69b1f45c3dca5c5',
        raw_business_file_count=len(business),historical_Git_source_count=len(formal),actual_signed_LOCAL_count=1887,actual_signed_Friends_count=1798,composition=composition,channel_contract=dict(path=str(W/'launcher-contract.json'),sha256=sha((W/'launcher-contract.json').read_bytes())),
        recovery_policy='Inherited complete new readers and four exact guards; no bare parent or DB restore',independent_review=dict(path=str(W/'independent-review/review.json'),sha256=sha((W/'independent-review/review.json').read_bytes())),actual_loading_verified=False)
    (D/'build.json').write_bytes(enc(result));print(json.dumps(dict(ok=True,V=59,exe_sha256=result['exe_sha256'],LOCAL=1887,Friends=1798)))

if __name__=='__main__':main()
