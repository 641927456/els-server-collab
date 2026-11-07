"""Stage immutable artifacts. Does not promote launcher or change old endpoint."""
from pathlib import Path
import base64,hashlib,json,os,re,subprocess,sys
H=Path(__file__).resolve().parent;D=H/'candidate-r2';REPO='641927456/els-launcher-updates'
read=lambda p:json.loads(Path(p).read_bytes())
def sha(p):
 with Path(p).open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
def run(args,name,timeout=900):
 r=subprocess.run(['gh',*map(str,args)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=timeout);(H/(name+'.private.txt')).write_bytes(r.stdout+r.stderr);assert r.returncode==0,(r.stdout+r.stderr).decode('utf8','replace')[-900:]
b=read(D/'build.json');binding=b['signed_bindings']['signedFriends'];archive=Path(binding['archive']['path']);definition=read(D/'runtime-files.json')
assert sha(archive)==definition['archive']['sha256']==binding['archive']['sha256']
mode=sys.argv[1]
if mode=='runtime':
 tag='runtime-'+binding['archive']['sha256'];notes=H/'runtime-notes.md';notes.write_text('当前已验收的共同运行组件；按启动器内置签名清单核对大小和 SHA256。此发布不更新启动器稳定渠道。\n','utf8')
 existing=subprocess.run(['gh','release','view',tag,'--repo',REPO],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=30)
 if existing.returncode!=0:run(['release','create',tag,'--repo',REPO,'--title','统一运行组件 '+tag[8:24],'--notes-file',notes,'--latest=false'],'runtime-release',60)
 snapshot=subprocess.run(['gh','api','repos/'+REPO+'/releases/tags/'+tag],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=30);assert snapshot.returncode==0
 present={a['name']:a for a in json.loads(snapshot.stdout)['assets']};pending=[]
 for path in [archive,*[D/'assets'/c['file']for c in definition['chunks']]]:
  if path.name not in present:pending.append(path);continue
  asset=present[path.name];assert asset['state']=='uploaded'and asset['size']==path.stat().st_size and asset['digest']=='sha256:'+sha(path)
 if pending:run(['release','upload',tag,'--repo',REPO,*pending],'runtime-upload-r2',1800)
elif mode=='candidate':
 assert read(H/'checks.json')['ok']and sha(b['exe'])==b['exe_sha256']
 release=json.loads(base64.b64decode(read(D/'latest.json')['payload']));file=D/'assets'/release['file']
 if not file.exists():os.link(b['exe'],file)
 notes=H/'candidate-notes.md';notes.write_text('候选 V'+str(b['version'])+'：版本检查与下载迁移到 GitHub Releases，保留 RSA/SHA256 与缓存复用。尚未接管旧启动器入口；待精确 head 审批及公网核收后发布稳定版。游戏服务端和原游戏 EXE/KOM 没有修改。\n','utf8')
 tag='launcher-v'+str(b['version'])+'-'+b['exe_sha256'][:16]
 run(['release','create',tag,'--repo',REPO,'--title','统一启动器 V'+str(b['version'])+' 候选','--notes-file',notes,'--prerelease','--latest=false',file,D/'latest.json'],'candidate-release',300)
elif mode=='cleanup-abandoned':
 from concurrent.futures import ThreadPoolExecutor
 tag='runtime-'+binding['archive']['sha256']
 snapshot=subprocess.run(['gh','api','repos/'+REPO+'/releases/tags/'+tag],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=30);assert snapshot.returncode==0
 release=json.loads(snapshot.stdout);present={a['name']:a for a in release['assets']};remove=[]
 for name,asset in present.items():
  match=re.fullmatch('chunk-'+binding['archive']['sha256']+'-([a-f0-9]{64})\\.zip',name)
  if match:
   short=present['chunk-'+match[1]+'.zip'];assert short['state']=='uploaded'and short['size']==asset['size']and short['digest']==asset['digest']=='sha256:'+match[1]
   remove.append(dict(id=asset['id'],name=name))
 (H/'abandoned-public-assets.json').write_text(json.dumps(dict(release_id=release['id'],assets=remove),indent=2),'utf8')
 def delete(asset):run(['api','--method','DELETE','repos/'+REPO+'/releases/assets/'+str(asset['id'])],'delete-asset-'+str(asset['id']),60)
 with ThreadPoolExecutor(max_workers=4)as pool:list(pool.map(delete,remove))
else:raise SystemExit('runtime|candidate|cleanup-abandoned')
print(json.dumps(dict(ok=True,mode=mode,promoted=False)))
