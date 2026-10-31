"""Verify the independent candidate against current accepted parents; never install."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import plan
folder=ROOT/'references/pr597-selected-20261027-v1'
read=lambda p:json.loads(Path(p).read_bytes())
d=read(folder/'delta.json');a=read(ROOT/d['parent']);b=read(ROOT/'channels/server-pr597-selected-20261027-v1.json');q=read(folder/'qualified-validation.json')
assert q['ok']and q['client_changes']==q['new_hooks']==q['new_tables']==q['install_DDL']==q['new_runtime_modules']==0
assert not q['player_database_restore']and q['original_PR597_not_merged']
for mode in('online-friends','local-local','local-friends'):
    p=q['private'][mode];assert p['ok']and p['private_saves_removed']and len(p['checks'])==3
for ch in('online','local'):
    old={r['path']:r for r in a['channels'][ch]['files']};new={r['path']:r for r in b['channels'][ch]['files']}
    assert old.keys()==new.keys()and len(d['channels'][ch])==5
    assert {p for p in old if old[p]!=new[p]}==set(d['channels'][ch])
    for p,e in d['channels'][ch].items():
        assert e['before_sha256']==old[p]['sha256']
        assert all(new[p][k]==e[k]for k in('source','sha256','size'))
    plan(ROOT,b,ch)
    s=q['regressions'][ch];assert s['ok']and len(s['suites'])==32 and s['total']==226
assert len(q['native_replay']['cases'])==5 and len(q['native_replay']['codecs'])==2
accepted_path=ROOT/'channels/pr597-selected-accepted-20261027-v2.json'
if accepted_path.exists():
    accepted=read(accepted_path);receipt=read(folder/'accepted-delivery.json')
    assert receipt['ok']and receipt['installed']and receipt['client_changes']==receipt['new_hooks']==0
    assert not accepted['candidate']and accepted['actual_dual_delivery_verified']
    for ch in('online','local'):
        assert accepted['channels'][ch]['files']==b['channels'][ch]['files']
        assert accepted['channels'][ch]['formal_manifest_sha256']==receipt['channels'][ch]['manifest_sha256']
        assert receipt['channels'][ch]['delta_files']==5 and receipt['channels'][ch]['observation_seconds']>=120
        plan(ROOT,accepted,ch)
print(json.dumps(dict(ok=True,channels=2,existing_server_leaves=5,private_modes=3,accepted_delivery_recorded=accepted_path.exists(),client_changes=0,new_hooks=0)))
