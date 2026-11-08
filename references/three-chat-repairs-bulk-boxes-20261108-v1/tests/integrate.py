"""Three-way integrate the four authorized candidates against actual V113."""
from pathlib import Path
import hashlib,json,subprocess,sys
R=Path('G:/els');H=Path(__file__).resolve().parent;C=H/'integrated-source';C.mkdir(exist_ok=True);read=lambda p:json.loads(Path(p).read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest();parents=read(H/'parents.json');BASE=R/parents['online']['path']
assert sha((BASE/'rollup-manifest.json').read_bytes())==parents['online']['manifest_sha256']
sources=[]
def add(name,path,entries,root,parent):
 for relative,before,after in entries:sources.append(dict(candidate=name,path=relative,before=before,after=after,source=root/relative,parent=parent))
p=R/'analysis/pet-auto-cooldown-20261108-v1';m=read(p/'candidate.json');add('pet-cooldown',p,[(r['path'],r['before_sha256'],r['sha256'])for r in m['files']],p/'source',R/'releases/online'/m['parent'])
p=R/'analysis/stackable-box-final-20261108-v1/local-policy-v1';m=read(p/'candidate.json');add('bulk-boxes',p,[(r['path'],r['parent_sha256'],r['sha256'])for r in m['files']],p/'source',Path(m['parent']['path']))
p=R/'analysis/plegas-consumables-20261108-v1';m=read(p/'candidate-manifest.json');add('giant-consumables',p,[(r['path'],r['parent_sha256'],r['sha256'])for r in m['files']],p/'candidate',Path(m['parent']['parent_path']))
p=R/'analysis/plegas-pillar-20261108-v1';m=read(p/'candidate-manifest.json');pins=read(p/'parent-pins.json');add('portrait-pillar',p,[(name,pins['files'][name],m['files']['candidate/'+name]['sha256'])for name in m['production_delta']],p/'candidate',Path(pins['runtime']))
conflicts=[];rows=[];temp=H/'merge-inputs';temp.mkdir(exist_ok=True)
for entry in sources:
 relative=entry['path'];candidate=entry['source'].read_bytes();assert sha(candidate)==entry['after'],relative
 parent_path=entry['parent']/relative;old=parent_path.read_bytes()if parent_path.exists()else b'';assert(sha(old)if parent_path.exists()else None)==entry['before'],relative
 target=C/relative;current=target.read_bytes()if target.exists()else(BASE/relative).read_bytes()if(BASE/relative).exists()else b''
 target.parent.mkdir(parents=True,exist_ok=True)
 if current==old:merged=candidate;method='exact-parent'
 elif current==candidate:merged=current;method='already-present'
 elif not old and not current:merged=candidate;method='new'
 else:
  paths=[temp/(entry['candidate']+'-'+suffix)for suffix in('current','base','candidate')]
  for path,raw in zip(paths,(current,old,candidate)):path.write_bytes(raw)
  result=subprocess.run(['git','merge-file','-p','--diff3',*[str(p)for p in paths]],capture_output=True)
  if result.returncode:
   conflict=target.with_suffix(target.suffix+'.conflict');conflict.write_bytes(result.stdout);conflicts.append(dict(path=relative,candidate=entry['candidate'],conflict=str(conflict),code=result.returncode));continue
  merged=result.stdout;method='three-way-clean'
 target.write_bytes(merged);rows.append(dict(candidate=entry['candidate'],path=relative,method=method,parent_sha256=sha(current)if current else None,source_sha256=entry['after'],sha256=sha(merged)))
# Rebind the actual merged script identities, retaining all unrelated V113 pins.
profile_path=C/'tools/client_compatibility_profiles.json'
if not any(r['path']=='tools/client_compatibility_profiles.json'for r in conflicts):
 data=read(profile_path)
 for profile in data['profiles']:
  if profile['id']!='cn-dx11-6c6b5180':continue
  for relative in list(profile['artifacts']):
   path=C/relative
   if path.exists():profile['artifacts'][relative]=sha(path.read_bytes())
  for relative in('tools/native_hit_count_obstacles.py','tools/native_hit_count_obstacles.js'):
   profile['artifacts'][relative]=sha((C/relative).read_bytes())
 profile_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
report=dict(ok=not conflicts,parent=parents['online']['release'],input_leaves=len(sources),unique_paths=len({r['path']for r in sources}),merges=rows,conflicts=conflicts,source=str(C))
(H/'merge-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(dict(ok=report['ok'],leaves=len(sources),conflicts=conflicts),ensure_ascii=False))
