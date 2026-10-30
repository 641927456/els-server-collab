"""Verify server-only career refresh sources without contacting a game or live save."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import plan
read=lambda p:json.loads(p.read_bytes())
F=ROOT/'references/native-master-current-skills-20261028-v1-source-v6';d=read(F/'delta.json');p=read(ROOT/d['parent']);c=read(ROOT/'channels/native-master-current-skills-20261028-v1.json');q=read(F/'manifest.json')
expected={'els_server/protocol/career_messages.py','els_server/domain/local_session.py','els_server/storage/career_shop.py','els_server/storage/careers.py','els_server/domain/quest_flow.py'}
assert q['issue']==607 and q['existing_leaves_per_channel']==5
assert all(q[k]==0 for k in('new_runtime_modules','new_tables','install_DDL','client_files','new_hooks'))
for channel in('online','local'):
 old={r['path']:r for r in p['channels'][channel]['files']};rows={r['path']:r for r in c['channels'][channel]['files']}
 assert rows.keys()==old.keys() and {path for path in rows if rows[path]!=old[path]}==expected
 assert set(d['channels'][channel])==expected
 assert p['channels'][channel].get('retained_client_sources')==c['channels'][channel].get('retained_client_sources')
 for key in('retained_client_support_sources','retained_signed_launcher_sha256','retained_signed_payload_sha256'):
  assert p['channels'][channel].get(key)==c['channels'][channel].get(key)
 assert c['channels'][channel]['parent_release']==p['channels'][channel]['release']
 for path,e in d['channels'][channel].items():
  assert e['before_sha256']==old[path]['sha256'] and all(e[k]==rows[path][k]for k in('source','sha256','size'))
  raw=(ROOT/e['source']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256'];ast.parse(raw)
 plan(ROOT,c,channel)
 source=(ROOT/rows['els_server/protocol/career_messages.py']['source']).read_text('utf8')
 tree=ast.parse(source);f=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='current_skill_notices')
 assert any(isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='encode_event'for n in ast.walk(f))
 assert 'kind=0x446' in source and "struct.pack('>5i',0,21,slots[21],-1,0)"in source
 session=(ROOT/rows['els_server/domain/local_session.py']['source']).read_text('utf8')
 assert 'if result==-1:result=2'in session and 'prepare_refresh=prepare_career_refresh'in session
 assert not any(word in source for word in('Interceptor.','Memory.write','new NativeFunction'))
print(json.dumps(dict(ok=True,existing_server_leaves=5,channels=2,new_client_files=0,new_hooks=0,production_actions=0)))
