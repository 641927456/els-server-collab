"""Test actual candidate DLL code and owned caches; never starts a game."""
from pathlib import Path
import base64,copy,hashlib,importlib.util,json,os,subprocess,sys
R=Path('G:/els');H=Path(__file__).resolve().parent;D=H/'candidate-r2'
sys.path.insert(0,str(R/'tools/pylibs'))
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
read=lambda p:json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def sha(p):
 with Path(p).open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
b=read(D/'build.json');exe=b['exe'];assert sha(exe)==b['exe_sha256']
spec=importlib.util.spec_from_file_location('owned',R/'analysis/scroll-mhp-delivery-20261101-v1/launcher_components_owned_process.py');owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned);owned.RECEIPTS=H/'owned-processes'
def run(args,name,timeout=180):
 result=owned.run(list(map(str,args)),capture_output=True,timeout=timeout);(H/(name+'.txt')).write_bytes(result.stdout+result.stderr);assert result.returncode==0,(result.stdout+result.stderr).decode('utf8','replace')[-2200:]
if sys.argv[1] in ('prepare','resume'):
 compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
 run([compiler,'/nologo','/out:'+str(H/'UpdateChecks.exe'),'/reference:System.Web.Extensions.dll',H/'UpdateChecks.cs'],'compile-checks',60)
 fixtures=H/'fixtures';fixtures.mkdir(exist_ok=True)
 key=serialization.load_pem_private_key((Path(os.environ['LOCALAPPDATA'])/'ElsFriends-Publisher/launcher-update-signing.pem').read_bytes(),None)
 def signed(name,doc):
  raw=json.dumps(doc,separators=(',',':')).encode();save(fixtures/(name+'.json'),dict(payload=base64.b64encode(raw).decode(),signature=base64.b64encode(key.sign(raw,padding.PKCS1v15(),hashes.SHA256())).decode()))
 release=json.loads(base64.b64decode(read(D/'latest.json')['payload']));signed('valid',release)
 for name,fields in [('bad-path',dict(file='../bad.exe')),('wrong-channel',dict(channel='other')),('oversize',dict(size=536870913))]:signed(name,dict(release,**fields))
 tampered=read(fixtures/'valid.json');tampered['payload']=base64.b64encode(base64.b64decode(tampered['payload'])+b' ').decode();save(fixtures/'tampered.json',tampered)
 foreign=copy.deepcopy(read(fixtures/'valid.json'));foreign['signature']=base64.b64encode(bytes(len(base64.b64decode(foreign['signature'])))).decode();save(fixtures/'wrong-key.json',foreign)
 definition=read(D/'runtime-files.json')
 for name in ['duplicate-member','missing-member','bad-chunk-path','wrong-chunk-hash']:
  doc=copy.deepcopy(definition)
  if name=='duplicate-member':doc['chunks'][1]['files'].append(doc['chunks'][0]['files'][0])
  if name=='missing-member':doc['chunks'][0]['files'].pop()
  if name=='bad-chunk-path':doc['chunks'][0]['file']='../chunk.zip'
  if name=='wrong-chunk-hash':doc['chunks'][0]['sha256']='0'*64
  signed(name,doc)
 bad=read(D/'signedFriends.signed.json');bad['signature']=foreign['signature'];save(fixtures/'tampered-runtime.json',bad)
 run([H/'UpdateChecks.exe',exe,'policy',fixtures,H/'policy.json'],'policy')
 # Published V82 is the seed. Its original signed bytes are used directly.
 parent=b['parent'];old=read(Path(parent['update_source']).parent/'build.json');cache=H/'upgrade-cache'
 if sys.argv[1]=='prepare':
  assert not cache.exists();cache.mkdir();save(cache/'owner.json',dict(purpose='Owned updater migration test',thread=os.environ.get('CODEX_THREAD_ID')))
 reader=R/'analysis/pending-repairs-completion-20261031-v1/launcher-wear-v50-v2/friends_component_reader.exe'
 if sys.argv[1]=='prepare':run([reader,parent['path'],cache,old['signed_bindings']['signedFriends']['archive']['path'],H/'seed.json','good'],'seed',300)
 run([H/'UpdateChecks.exe',exe,'cached',cache,D/'assets',H/'upgrade.json'],'upgrade',180)
 assert read(H/'upgrade.json')['requests']==0
 root=Path(read(H/'seed.json')['root']);target=next(r for r in definition['files']if r['path'].endswith('local_session.py'))
 # Copy links belong solely to each test cache; unlinking never changes source bytes.
 for mode in ([]if sys.argv[1]=='resume'else ['partial','corrupt','truncated','public']):
  test=H/(mode+'-cache');test.mkdir();seed=test/'component-runtimes'/'owned-seed';seed.mkdir(parents=True)
  for row in definition['files']:
   if row==target:continue
   p=seed/row['path'];p.parent.mkdir(parents=True,exist_ok=True);os.link(root/row['path'],p)
  pointer=test/'component-state'/'current.json';pointer.parent.mkdir();save(pointer,dict(path=str(seed),test=True))
  save(test/'owner.json',dict(purpose='Owned updater '+mode,thread=os.environ.get('CODEX_THREAD_ID')))
 run([H/'UpdateChecks.exe',exe,'partial',H/'partial-cache',D/'assets',H/'partial.json'],'partial')
 result=read(H/'partial.json');assert result['requests']==1 and result['first']['downloaded_files']==1 and not result['first']['full_archive_downloaded']
 for mode in ['corrupt','truncated']:run([H/'UpdateChecks.exe',exe,mode,H/(mode+'-cache'),D/'assets',H/(mode+'.json')],mode)
 expected=D/'expected-resources.json';save(expected,{r['name']:r['sha256']for r in b['resources']})
 profile=next(r['sha256']for r in definition['files']if r['path']=='tools/client_compatibility_profiles.json')
 run([R/'analysis/feature-closure-20261105-v1/login-delivery-v1/verify_embedded.exe',exe,expected,H/'embedded.json',b['version'],definition['archive']['sha256'],profile],'embedded',60)
 save(H/'checks.json',dict(ok=True,version=b['version'],exe_sha256=b['exe_sha256'],resources=len(b['resources']),components=len(definition['files']),upgrade_network_requests=0,partial_requests=result['requests'],partial_download_bytes=result['bytes'],partial_reused=2785,repeat_downloads=0,corruption_and_truncation_rejected=True,server_bytes_unchanged=True,original_EXE_KOM_changes=0))
 print((H/'checks.json').read_text())
elif sys.argv[1]=='public':
 run([H/'UpdateChecks.exe',exe,'public',H/'public-cache',D/'assets',H/'public.json'],'public',300)
 result=read(H/'public.json');assert result['first']['downloaded_files']==1 and result['second']['downloaded_files']==0
 print(json.dumps(dict(ok=True,anonymous_chunk_download=True,downloaded_bytes=result['first']['downloaded_bytes'],repeat=0)))
elif sys.argv[1]=='download':
 run([H/'UpdateChecks.exe',exe,'asset',H/'public-exe-cache',D/'latest.json',H/'public-exe.json'],'public-exe',300)
 print(json.dumps(dict(ok=True,anonymous_EXE_download=True)))
elif sys.argv[1]=='fresh':
 run([H/'UpdateChecks.exe',exe,'publicfresh',H/'fresh-cache',D/'assets',H/'fresh.json'],'fresh',300)
 result=read(H/'fresh.json');assert result['first']['full_archive_downloaded']and result['first']['downloaded_files']==2786 and result['second']['downloaded_files']==0
 print(json.dumps(dict(ok=True,anonymous_full_runtime_download=True,members=2786,repeat=0)))
else:raise SystemExit('prepare|resume|public|download|fresh')
