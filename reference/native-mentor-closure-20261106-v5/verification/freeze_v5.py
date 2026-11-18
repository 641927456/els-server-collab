"""Freeze the original720→227 continuation on immutable v4."""
from pathlib import Path
import ast,copy,hashlib,json,os,shutil
W=Path(__file__).resolve().parent;C=W/'candidate-v5';F=W/'full-source-v5'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
base=read(W/'delivery-manifest-v4.json');original=read(W.parent/'duel-wire-v2/delivery-manifest.json')
files={r['path']:r for r in base['files']};old={r['path']:r for r in original['files']}
assert not(W/'candidate-source-binding-v5.json').exists()
F.mkdir(exist_ok=True)
for row in base['files']:
    p=W/'full-source-v4'/row['path'];assert sha(p)==row['sha256'],row['path']
    t=F/row['path'];t.parent.mkdir(parents=True,exist_ok=True)
    if t.exists():assert sha(t)==sha(C/row['path'])if(C/row['path']).is_file()else sha(t)==row['sha256']
    else:os.link(p,t)
changed=[]
for p in sorted((C/'els_server').rglob('*')):
    if not p.is_file():continue
    if p.suffix=='.py':ast.parse(p.read_bytes())
    name=p.relative_to(C).as_posix();digest=sha(p)
    if files.get(name,{}).get('sha256')==digest:continue
    changed.append(name);t=F/name;t.parent.mkdir(parents=True,exist_ok=True)
    if not t.exists()or sha(t)!=digest:
        if t.exists():t.unlink()
        shutil.copyfile(p,t)
    files[name]=dict(path=name,size=p.stat().st_size,sha256=digest)
assert set(changed)=={'els_server/domain/local_session.py','els_server/domain/mentor_summon.py'}
rows=[dict(r,base_sha256=old.get(name,{}).get('sha256'))for name,r in sorted(files.items())if old.get(name,{}).get('sha256')!=r['sha256']]
assert len(rows)==42 and len(files)==1594
manifest=copy.deepcopy(base);manifest.update(release='native-mentor-closure-20261106-v5',path='releases/online/native-mentor-closure-20261106-v5',parent_release=base['release'],parent_manifest_sha256=sha(W/'delivery-manifest-v4.json'),files=[files[k]for k in sorted(files)],file_count=len(files))
save(W/'delivery-manifest-v5.json',manifest)
save(W/'candidate-manifest-v5.json',dict(files=rows,parent_source=str(W/'full-source-v4'),parent_manifest_sha256=sha(W/'delivery-manifest-v4.json'),new_revision_changes=changed))
save(W/'candidate-source-binding-v5.json',dict(ok=True,source_frozen=True,full_source=str(F),manifest_sha256=sha(W/'delivery-manifest-v5.json'),source_delta=42,new_files=16,files=len(files),client_support_delta=0,installed=False,native_Game_mentor_qualified=False,related_verification_pending=True))
print(json.dumps(dict(frozen=True,source_delta=42,files=len(files),changed_from_v4=changed,installed=False)))
