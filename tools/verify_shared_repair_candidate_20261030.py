"""Verify only the unselected shared repair source candidate and family maps."""
from pathlib import Path
import json,hashlib,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools'))
from materialize_formal_runtime import load_manifest,plan
NAME='native-shared-repair-20261030-v1'
REF=ROOT/'references'/NAME
def read(p):return json.loads(p.read_bytes())
def main():
 profile=load_manifest(ROOT/'channels'/f'{NAME}.json')
 selected=read(ROOT/'channels/current-engine.json')
 assert selected['profile']in('channels/server-structure-accepted-20261029-v1.json','channels/native-shared-repair-accepted-20261030-v1.json')
 if selected['profile']=='channels/native-shared-repair-accepted-20261030-v1.json':
  from tools.verify_shared_repair_inheritance_20261030 import verified_shared_repair_predecessor
  accepted=load_manifest(ROOT/'channels/current-engine.json',ROOT)
  for mode in('online','local'):
   row=next(r for r in accepted['channels'][mode]['files']if r['path']=='els_server/storage/seal_quests.py')
   verified_shared_repair_predecessor(accepted,mode,row,ROOT/row['source'],root=ROOT)
 assert profile['candidate']is True and profile['actual_dual_delivery_verified']is False
 assert profile['delta_business_files']=={'online':28,'local':28}
 assert profile['delta_source_files']=={'online':28,'local':31}
 assert profile['new_schema']is True and profile['new_schema_definitions']==5
 assert profile['install_DDL_statements']==0 and profile['new_hooks']==3
 parent=read(ROOT/profile['parent']);delta=read(REF/'delta.json');qualified=read(REF/'qualification.json')
 result={}
 for channel,count in [('online',28),('local',31)]:
  rows={r['path']:r for r in profile['channels'][channel]['files']}
  previous={r['path']:r for r in parent['channels'][channel]['files']}
  changes={p for p in rows.keys()|previous.keys()if rows.get(p)!=previous.get(p)}
  assert changes==set(delta['channels'][channel])and len(changes)==count
  assert len(rows)==(1315 if channel=='online' else 1340)
  assert len(set(rows)-set(previous))==8
  if channel=='local':
   new_support=(ROOT/rows['tools/native_cache_sync.js']['source']).read_text(encoding='utf-8-sig')
   old_support=(ROOT/previous['tools/native_cache_sync.js']['source']).read_text(encoding='utf-8-sig')
   for site in profile['new_hook_sites']:
    marker='Interceptor.attach(module.base.add('+site+')'
    assert marker in new_support and marker not in old_support
  assert not any(p.endswith(('dead_dragon_identification.py','dead_dragon_identification.json'))for p in rows)
  sources=plan(ROOT,profile,channel)
  for row,source in sources:
   if source is not None and source.suffix in('.py','.pyw'):
    compile(source.read_text(encoding='utf-8-sig'),str(source),'exec')
  result[channel]={'files':len(rows),'delta':len(changes),'source_files':sum(s is not None for _,s in sources),'unmaterialized_locked_assets':sum(s is None for _,s in sources)}
 families={}
 for family,expected,known in [('rawLOCAL',1794,1794),('signedFriends',1779,1779),('signedLOCAL',1794,1794)]:
  index=read(REF/'families'/f'{family}.json');rows=index['rows']
  assert len(rows)==known and index['expected_final_count']==expected
  assert len({r['path'].casefold()for r in rows})==len(rows)
  for row in rows:
   source=row['source']
   if source['kind']=='repository-source':
    b=(ROOT/source['path']).read_bytes()
    assert len(b)==row['size']and hashlib.sha256(b).hexdigest()==row['sha256']
   elif source['kind']=='generated-unsigned-metadata':
    assert family=='signedLOCAL'and row['path']=='local-bootstrap-source.json'
    assert source['sha256']==row['sha256']=='2adb90a9bd462e004fa7b8861fa3f9af91161ba383f778f85843f915a2010daa'
    assert row['size']==3789766
    assert source['prospective_profile_sha256']==qualified['prospective_accepted_profile_sha256']
   else:assert source['kind']=='frozen-family-member'
  support={r['path']:r['sha256']for r in rows if r['path'].startswith('tools/native_cache_sync.')}
  assert support=={'tools/native_cache_sync.js':'e2f86915262ba1ea1e919eb1b33c5f022e1a311bd267569bb02f3aee7368083a','tools/native_cache_sync.py':'225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856'}
  assert index['installable']is False and index['exact_new_package_created']is False
  families[family]={'known':known,'expected':expected,'pending':index['pending']}
 assert qualified['publication_qualified']is False and qualified['installed']is False
 print(json.dumps({'ok':True,'channels':result,'families':families,'source_preparation_only':True,'selected':selected['profile']=='channels/native-shared-repair-accepted-20261030-v1.json','runtime_execution':False,'production_actions':False},ensure_ascii=True))
if __name__=='__main__':main()
