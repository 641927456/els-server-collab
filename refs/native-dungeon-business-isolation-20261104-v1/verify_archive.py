"""Verify exact source bytes and unchanged native consumer bodies."""
from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent
m=json.loads((H/'source-manifest.json').read_bytes())
for row in m['files']:
 p=H/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
for row in m['changes']:
 p=H/'source'/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
 p=H/'base'/row['path'];assert (hashlib.sha256(p.read_bytes()).hexdigest()if p.exists()else None)==row['parent_sha256']
t=ast.parse((H/'base/els_server/domain/local_session.py').read_text('utf8'))
c=next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name=='LocalSession')
f=next(n for n in c.body if isinstance(n,ast.FunctionDef)and n.name=='_handle')
new=ast.parse((H/'source/els_server/domain/dungeon_native_actions.py').read_text('utf8'))
for kind,name in ((0x2ce,'spawn'),(0x67,'end'),(0xb3,'loaded')):
 old=next(n for n in f.body if isinstance(n,ast.If)and any(isinstance(v,ast.Constant)and type(v.value)is int and v.value==kind for v in ast.walk(n.test)))
 moved=next(n for n in new.body if isinstance(n,ast.FunctionDef)and n.name==name).body[1]
 assert ast.dump(old)==ast.dump(moved),name
v=json.loads((H/'validation.json').read_bytes());assert v['ok']and sum(len(t['checks'])for t in v['tests'])==38
print(json.dumps(dict(ok=True,exact_files=len(m['files']),runtime_delta=len(m['changes']),native_bodies_unchanged=3,related_checks=38)))
