from delivery_common import *
import ast,base64,copy,inspect,os,re,subprocess,zipfile,zlib
D=W/'launcher-v62';S=D/'source';MANAGED='local-git-first-run-ring-wear-20261101-v1'
TARGETS={'els_server/domain/fashion_state.py','els_server/storage/wear_moves.py'}
digest=lambda b:__import__('hashlib').sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def rows(files):return[dict(path=n,size=len(b),sha256=digest(b))for n,b in sorted(files.items())]
def rowhash(value):return digest(json.dumps(sorted(value,key=lambda r:r['path']),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
def one(text,old,new):assert text.count(old)==1,(old,text.count(old));return text.replace(old,new,1)
def put(name,value):
 p=S/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value if isinstance(value,bytes)else value.encode())
handoff=read(W/'preceding-publisher-handoff.json');assert handoff['slot_returned_to_ring']
P=Path(handoff['parent_launcher_build']).parent;old=read(P/'build.json');parent=read(R/'releases/launchers/current.json')
assert parent['V']==old['version']==61 and parent['sha256']==old['exe_sha256']and sha(old['exe'])==old['exe_sha256']
contract=read(W/'publication/release-contract.json')['local'];raw=R/contract['root'];assert read(W/'publication/local-install/qualification.json')['ok']
assert sha(raw/'local-business-manifest.json')==contract['manifest_sha256']
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
key=serialization.load_pem_private_key((Path(os.environ['LOCALAPPDATA'])/'ElsFriends-Publisher/launcher-update-signing.pem').read_bytes(),None)
ref=old['signed_bindings']['signedLOCAL'];eb=Path(ref['manifest']['path']).read_bytes();assert digest(eb)==ref['manifest']['sha256'];env=json.loads(eb);payload=base64.b64decode(env['payload'],validate=True);key.public_key().verify(base64.b64decode(env['signature'],validate=True),payload,padding.PKCS1v15(),hashes.SHA256());definition=json.loads(payload)
archive=Path(ref['archive']['path']);assert sha(archive)==ref['archive']['sha256']==definition['archive']['sha256']
with zipfile.ZipFile(archive)as z:
 names=z.namelist();assert len(names)==len(set(names))==1892;before={n:z.read(n)for n in names}
assert rows(before)==definition['files'];files=dict(before);oldmeta=json.loads(before['local-bootstrap-source.json'])
source=read(R/'analysis/ring-wear-error-20261101-v1/result-v2.json');source_rows={r['path']:r for r in source['runtime_files']}
for rel in TARGETS:
 value=(raw/rel).read_bytes();assert digest(value)==source_rows[rel]['sha256'];files[rel]=value
profile=json.loads(files['tools/client_compatibility_profiles.json']);assert not any(TARGETS&set(p['artifacts'])for p in profile['profiles'])
packed_parent=json.loads(zlib.decompress(base64.b64decode((P/'source/resources/labyrinth-predecessor.txt').read_bytes(),validate=True)));formal=packed_parent['formal_rows'];assert len(formal)==1342 and rowhash(formal)==oldmeta['source_files_sha256']
packed=zlib.compress(enc(dict(envelope_base64=base64.b64encode(eb).decode(),metadata_base64=base64.b64encode(before['local-bootstrap-source.json']).decode(),formal_rows=formal)),9);predtext=base64.b64encode(packed);pred=dict(encoding='embedded-zlib-base64-v61-public-v1',sha256=digest(packed))
meta=copy.deepcopy(oldmeta);meta['release']=MANAGED;meta['upgrade_from']=dict(schema=1,kind='exact-v61-transitive-to-ring-wear-v1',to_runtime_release=MANAGED,to_source_release=oldmeta['source_release'],to_source_formal_manifest_sha256=oldmeta['source_formal_manifest_sha256'],v61_predecessor=pred)
formal_index={r['path']:r for r in formal};meta['support_overrides']=[dict(path=n,source_sha256=r['sha256'],runtime_sha256=digest(files[n]))for n,r in sorted(formal_index.items())if n!='config/server.toml'and digest(files[n])!=r['sha256']]
additions={r['path']for r in oldmeta['support_additions']};meta['support_additions']=[dict(path=n,runtime_sha256=digest(files[n]))for n in sorted(additions)]
files['local-bootstrap-source.json']=enc(meta);assert {n for n in files if files[n]!=before[n]}==TARGETS|{'local-bootstrap-source.json'}
assert not D.exists();S.mkdir(parents=True)
for rel,row in old['source_inventory'].items():
 data=(P/'source'/rel).read_bytes();assert len(data)==row['size']and digest(data)==row['sha256'];put(rel,data)
put('resources/ring-wear-predecessor.txt',predtext)
temp=D/'signedLOCAL.zip'
with zipfile.ZipFile(temp,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
 for n,value in sorted(files.items()):
  info=zipfile.ZipInfo(n,(2026,11,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,value)
target=D/('runtime-'+sha(temp)+'.zip');temp.rename(target);newdef=copy.deepcopy(definition);newdef.update(archive=dict(file=target.name,size=target.stat().st_size,sha256=sha(target)),files=rows(files))
payload=json.dumps(newdef,separators=(',',':')).encode();signed=json.dumps(dict(payload=base64.b64encode(payload).decode(),signature=base64.b64encode(key.sign(payload,padding.PKCS1v15(),hashes.SHA256())).decode()),separators=(',',':')).encode();manifest=D/'signedLOCAL.signed.json';manifest.write_bytes(signed);put('resources/ring-wear-signedLOCAL.signed.json',signed)
binding=dict(manifest=dict(path=str(manifest),sha256=sha(manifest)),archive=dict(path=str(target),sha256=sha(target)))
builder=load('parent_labyrinth_builder',P.parent/'build_launcher_v61.py');code=inspect.getsource(builder.new_bootstrap)
code=code.replace('labyrinth_v60_predecessors','__NEW_HELPER__').replace('quest_gates_v59_predecessors','labyrinth_v60_predecessors').replace('__NEW_HELPER__','ring_wear_v61_predecessors').replace('labyrinth-predecessor.txt','ring-wear-predecessor.txt').replace('V60','V61').replace('len(contracts)==16','len(contracts)==17')
code=code.replace("'v59_predecessor'","'__BASE_FIELD__'").replace("'v60_predecessor'","'v61_predecessor'").replace("'__BASE_FIELD__'","'v60_predecessor'")
ns=dict(builder.__dict__);ns['MANAGED']=MANAGED;exec(compile(code,'<ring predecessor extension>','exec'),ns)
bootstrap=ns['new_bootstrap']((P/'source/resources/labyrinth-local-bootstrap.py').read_text('utf8'),meta,newdef,oldmeta,definition,eb,before,predtext,packed,pred,formal,files);put('resources/ring-wear-local-bootstrap.py',bootstrap)
cohort=(P/'source/LabyrinthRuntimeCohort.cs').read_text('utf8').replace('LabyrinthRuntimeCohort','RingWearRuntimeCohort').replace(oldmeta['release'],MANAGED).replace('ElsFriends.LabyrinthLocal','ElsFriends.RingWearLocal')
for name,value in dict(LocalPayload=binding['archive']['sha256'],LocalEnvelope=binding['manifest']['sha256'],LocalMetadata=digest(files['local-bootstrap-source.json']),BootstrapHash=digest(bootstrap.encode())).items():
 cohort,n=re.subn(r'\b'+name+r'="[a-f0-9]{64}"',name+'="'+value+'"',cohort);assert n==1,name
put('RingWearRuntimeCohort.cs',cohort)
t=(S/'ComponentRuntime.cs').read_text('utf8')
for field in ('RequireLocal','LocalPayload','LocalCount','LocalMetadata','LocalResource','LocalEnvelope'):t=t.replace('LabyrinthRuntimeCohort.'+field,'RingWearRuntimeCohort.'+field)
put('ComponentRuntime.cs',t)
t=(S/'LocalBootstrap.cs').read_text('utf8');t=one(t,'            if(LabyrinthRuntimeCohort.RequireCurrentDirection(pointer,source))return;','            if(RingWearRuntimeCohort.RequireCurrentDirection(pointer,source))return;\n            if(LabyrinthRuntimeCohort.RequireCurrentDirection(pointer,source))return;')
for a,b in [('source.Accessory?LabyrinthRuntimeCohort.ManagedRelease','source.Accessory?RingWearRuntimeCohort.ManagedRelease'),('selection.Accessory?LabyrinthRuntimeCohort.BootstrapResource','selection.Accessory?RingWearRuntimeCohort.BootstrapResource'),('selection.Accessory?LabyrinthRuntimeCohort.BootstrapHash','selection.Accessory?RingWearRuntimeCohort.BootstrapHash')]:t=one(t,a,b)
t=one(t,'            Program.PrivateWrite(script,text);','            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"ring-wear-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.RingWearPredecessor","'+digest(predtext)+'"));\n            Program.PrivateWrite(script,text);');put('LocalBootstrap.cs',t)
put('AutoUpdate.cs',one((S/'AutoUpdate.cs').read_text('utf8'),'public const int Version = 61;','public const int Version = 62;'))
resources=copy.deepcopy(old['resources'])
for name,label in [('ring-wear-signedLOCAL.signed.json','RingWearLocalRuntimeFiles'),('ring-wear-local-bootstrap.py','RingWearLocalBootstrap'),('ring-wear-predecessor.txt','RingWearPredecessor')]:resources.append(dict(path='resources/'+name,name='ElsFriends.'+label,sha256=sha(S/'resources'/name)))
assert all(sha(S/r['path'])==r['sha256']for r in resources)
exe=D/'ElsFriends-V62.exe';compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe';argv=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(exe),'/win32icon:'+str(R/'launcher/assets/launcher.ico'),'/win32manifest:'+str(S/'app.manifest')]+['/resource:'+str(S/r['path'])+','+r['name']for r in resources]+['/reference:'+n for n in ('System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll')]+[str(p)for p in sorted(S.glob('*.cs'))]
q=subprocess.run(argv,capture_output=True,timeout=90,creationflags=0x08000000);(D/'compile.txt').write_bytes(q.stdout+q.stderr);assert q.returncode==0,q.stdout.decode('utf8','replace')[-1600:]
signer=load('ring_update_signer',R/'analysis/launcher-autoupdate-01a1533c-20261019-v1/sign_release.py');latest=signer.sign(exe,62,D/'latest.json')
result=dict(ok=True,version=62,exe=str(exe),exe_sha256=sha(exe),size=exe.stat().st_size,latest=latest,parent=parent,parent_exe_sha256=old['exe_sha256'],signed_bindings=dict(signedLOCAL=binding,signedFriends=old['signed_bindings']['signedFriends']),resources=resources,component_delta=dict(signedLOCAL=sorted(TARGETS|{'local-bootstrap-source.json'}),signedFriends=[]),source_inventory={p.relative_to(S).as_posix():dict(size=p.stat().st_size,sha256=sha(p))for p in S.rglob('*')if p.is_file()},raw_local_source=dict(release=contract['release'],root=str(raw),manifest_sha256=contract['manifest_sha256']),raw_delta=[dict(path=n,size=(raw/n).stat().st_size,sha256=sha(raw/n))for n in sorted(TARGETS)],published=False,original_EXE_KOM_changes=0,new_Hooks=0,player_database_restore=False,complete_three_position_reader_retained=True)
save(D/'build.json',result);print(json.dumps(dict(ok=True,V=62,exe_sha256=result['exe_sha256'],LOCAL_changed=3,Friends_changed=0)))
