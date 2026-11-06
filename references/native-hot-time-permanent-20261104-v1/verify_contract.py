"""Portable archive identity verification; does not claim runtime execution."""
from pathlib import Path
import ast,hashlib,importlib.util,json
H=Path(__file__).resolve().parent;c=json.loads((H/'source-contract.json').read_bytes());count=0
for channel in('online','local'):
 files=c['channels'][channel]['files'];assert len(files)==6
 for name,row in files.items():
  p=H/row['source'];assert p.resolve().is_relative_to(H.resolve())and p.stat().st_size==row['size']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],name
  if p.suffix=='.py':ast.parse(p.read_bytes())
  else:json.loads(p.read_bytes())
  count+=1
 p=H/'source'/channel/'els_server/domain/hot_time.py';spec=importlib.util.spec_from_file_location('archived_hot_time_'+channel,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 assert module.unlimited_fatigue()and module.ordinary_multiplier()==2 and module.policy()['resonance_icon']
for name,pin in c['evidence'].items():assert hashlib.sha256((H/name).read_bytes()).hexdigest()==pin,name
for channel in('online','local'):
 business=json.loads((H/'validation'/('qa-business-'+channel+'.json')).read_bytes());assert business['ok']and business['tests']==7 and business['failures']==business['errors']==0
 for mode in('solo','group'):
  case=json.loads((H/'validation'/('qa-tls-'+channel+'-'+mode+'.json')).read_bytes());assert case['ok']and case['actual_Application_TLS']and case['cleanup']['owned_runtime_removed']and case['cleanup']['active_connections']==0
native=json.loads((H/'validation/native-codec-proof.json').read_bytes());assert native['production_packet']['records']==3 and native['production_packet']['bytes_consumed']==224 and not native['natural_GUI']
public=json.loads((H/'validation/public-protocol-summary.json').read_bytes());assert public['ok']and public['ordinary_multiplier']==2 and public['resonance_multiplier']==10 and public['fatigue_after']==0
delivery=json.loads((H/'validation/delivery-summary.json').read_bytes());assert delivery['online_and_local_installed']and delivery['LOCAL_actual_selected_TLS']and all(v['observation_seconds']>=120 for v in delivery['channels'].values())
print(json.dumps(dict(ok=True,archived_source_files=count,channels=2,exact_hashes_verified=True,recorded_business_and_delivery_evidence_verified=True,runtime_tests_executed=False)))
