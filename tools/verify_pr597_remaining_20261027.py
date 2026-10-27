"""Verify the selected remaining597 source delta, actual parent and evidence."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import plan
read=lambda p:json.loads(Path(p).read_bytes())
F=ROOT/'references/pr597-remaining-20261027-v2';d=read(F/'delta.json');p=read(ROOT/d['parent']);c=read(ROOT/'channels/server-pr597-remaining-20261027-v2.json');q=read(F/'qualified-validation.json');audit=read(F/'PR597-remaining-adjudication.json')
assert q['ok']and q['client_changes']==q['new_hooks']==q['new_tables']==q['install_DDL']==0 and q['new_runtime_modules']==1
assert not q['player_database_restore']and q['original_PR597_not_merged']
assert audit['reviewed_paths']==54 and audit['all_original_hunks_classified']and len(audit['files'])==54
new={'els_server/domain/devildom1_raid2_controllers.py'}
expected=new|{'els_server/domain/dungeon_flow.py','els_server/domain/dungeon_routes.py','els_server/domain/local_session.py','els_server/storage/seal_quests.py','els_server/storage/skill_unlocks.py'}
for mode in ('online-friends','local-local','local-friends'):
 v=q['private'][mode];assert v['ok']and v['private_saves_removed']and v['raid_sql_counts']['formal_raid_phases']==3 and not v['natural_GUI']
for channel in ('online','local'):
 old={r['path']:r for r in p['channels'][channel]['files']};rows={r['path']:r for r in c['channels'][channel]['files']}
 assert set(rows)-set(old)==new and not set(old)-set(rows)
 assert set(d['channels'][channel])==expected
 assert {path for path in old if rows[path]!=old[path]}==expected-new
 for path,e in d['channels'][channel].items():
  assert e['before_sha256']==(old.get(path)or{}).get('sha256')
  assert all(rows[path][key]==e[key]for key in ('source','sha256','size'))
  raw=(ROOT/e['source']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256'];ast.parse(raw)
 assert rows['els_server/domain/skill_rules.py']==old['els_server/domain/skill_rules.py']
 assert rows['els_server/domain/skill_rules.py']['sha256']=='559e7315871317f61502d943e1bf4913c74064724986015f0ba225e52e820e8d'
 for support in p['channels'][channel].get('retained_client_sources',[]):assert support in c['channels'][channel]['retained_client_sources']
 v=q['regressions'][channel];assert v['ok']and len(v['suites'])==34 and v['total']==245
 n=q['native_quest'][channel];assert n['ok']and [x['active']for x in n['checks']]==[1,0,0]
 plan(ROOT,c,channel)
accepted=ROOT/'channels/pr597-remaining-accepted-20261027-v2.json'
if accepted.exists():
 a=read(accepted);receipt=read(F/'accepted-delivery.json')
 assert receipt['ok']and receipt['installed']and not a['candidate']and a['actual_dual_delivery_verified']
 for channel in ('online','local'):
  assert a['channels'][channel]['files']==c['channels'][channel]['files']
  assert a['channels'][channel]['formal_manifest_sha256']==receipt['channels'][channel]['manifest_sha256']
  assert receipt['channels'][channel]['delta_files']==6 and receipt['channels'][channel]['observation_seconds']>=120
  plan(ROOT,a,channel)
print(json.dumps(dict(ok=True,paths_adjudicated=54,existing_server_leaves=5,new_server_modules=1,private_modes=3,client_changes=0,new_hooks=0,accepted_delivery_recorded=accepted.exists())))
