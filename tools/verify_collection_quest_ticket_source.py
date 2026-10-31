"""Check exact installed delta binding and channel differences without owner data."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];REF=ROOT/'references/collection-quest-ticket-20261031-v1'
def load(p):return json.loads(p.read_bytes())
def main():
 contract=load(REF/'source-contract.json');seen=set();by_channel={}
 assert contract['format']==1 and contract['issue']==657
 assert not contract['root_runtime_changed']and not contract['materializer_selection_changed']and not contract['historical_frozen_inputs_changed']
 assert contract['new_lazy_tables']==['character_search_collection_synergy_time']and contract['install_DDL']==0 and not contract['client_changes']
 for channel in ('online','local'):
  branch=contract['channels'][channel];rows=branch['files'];by_channel[channel]={r['path']:r for r in rows}
  assert len(rows)==12 and len(by_channel[channel])==12 and sum(r['parent_sha256']is None for r in rows)==5
  for row in rows:
   source=ROOT/row['source'];assert source.resolve().is_relative_to((REF/'source').resolve())
   raw=source.read_bytes();assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
   ast.parse(raw)if source.suffix=='.py'else json.loads(raw);seen.add(row['source'])
  patch=ROOT/branch['patch']['path'];assert patch.resolve().is_relative_to((REF/'patches').resolve())
  assert hashlib.sha256(patch.read_bytes()).hexdigest()==branch['patch']['sha256']
 assert len(seen)==contract['unique_source_files']
 different={p for p,r in by_channel['online'].items()if r['sha256']!=by_channel['local'][p]['sha256']}
 assert different=={'els_server/domain/session_dispatch.py','els_server/domain/acquisition_policy.py'}
 for channel in ('online','local'):
  rows=by_channel[channel]
  data=load(ROOT/rows['els_server/data/retained_native_consumables.json']['source'])
  assert not data['new_sources']and not data['consumption_enabled']
  dispatch=(ROOT/rows['els_server/domain/session_dispatch.py']['source']).read_text('utf8')
  assert 'el_search_collection_flow'in dispatch
  quest=(ROOT/rows['els_server/domain/quest_flow.py']['source']).read_text('utf8');assert 'restore_on_arrival'in quest
 evidence=load(REF/'validation-summary.json')
 assert evidence['public_TLS']['ok']and evidence['local_business']['ok']
 assert min(evidence['online_observation_seconds'],evidence['local_observation_seconds'])>=120
 assert not evidence['player_database_restore']and not evidence['public_TLS']['natural_GUI']
 print(json.dumps(dict(ok=True,channels=2,unique_source_files=len(seen),delta_files_each=12,root_runtime_changed=False)))
if __name__=='__main__':main()
