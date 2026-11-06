"""Verify the archived EXP delta without private runtime resources or saves."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'references/pve-experience-20261105-v1'
contract=json.loads((REF/'source-contract.json').read_bytes())
assert contract['issue']==858 and contract['candidate'] and not contract['activation']
assert not contract['online_installed'] and not contract['database_migration'] and not contract['client_changes']
files={}
for row in contract['files']:
    path=(ROOT/row['source']).resolve()
    assert path.is_relative_to(REF.resolve()) and row['path']not in files
    raw=path.read_bytes()
    assert len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
    if path.suffix=='.py':compile(raw,str(path),'exec')
    files[row['path']]=row
assert len(files)==9
def data(name):return json.loads((ROOT/files['els_server/data/'+name]['source']).read_bytes())
ordinary=data('pve_experience.json');raid=data('raid_phase_experience.json')
for name,payload in [('pve_experience',ordinary),('raid_phase_experience',raid)]:
    index=data(name+'.manifest.json')
    assert index['payload_sha256']==files['els_server/data/'+name+'.json']['sha256']
    assert payload['policy']==index['policy'] and payload['client_sha256']==contract['client_sha256']==index['client_sha256']
assert len(ordinary['maps'])==159 and len(raid['maps'])==15
assert sum(len(m['phases'])for m in raid['maps'].values())==45
assert ordinary['clear']['rate']==0.3
direct=sum(n['provenance']['kind']=='community_measurement'for m in ordinary['maps'].values()for n in m['monsters'].values())
assert direct==245
for row in ordinary['maps'].values():
    assert len(bytes.fromhex(row['graph_sha256']))==32
    for npc in row['monsters'].values():
        assert type(npc['experience'])is int and 0<=npc['experience']*10<=2**31-1
portrait=ordinary['maps']['34720']['monsters']
assert all(portrait[str(n)]['experience']==108878 for n in (8180,8181,8182))
assert portrait['8176']['experience']==4751040
assert sum(portrait[str(n)]['experience']*count for n,count in ((8180,14),(8181,34),(8182,22),(8176,1)))==12372500
for row in raid['maps'].values():
    assert row['family']in ('rosso','berthe') and row['mode']in ('normal','story','solo')
    for stage,phase in row['phases'].items():
        assert phase['phase']==int(stage)+1
        assert phase['experience']==(950208 if row['family']=='rosso'else 1900416)
for row in contract['evidence']:
    path=(ROOT/row['source']).resolve();assert path.is_relative_to(REF.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
ordinary_qa=json.loads((REF/'evidence/ordinary-validation.json').read_bytes())
raid_qa=json.loads((REF/'evidence/raid-sql-context-results.json').read_bytes())
assert ordinary_qa['sqlite']['passed']==11 and raid_qa['ok'] and raid_qa['tests_run']==9
for rel,digest in ordinary_qa['ordinary_candidate_source_sha256'].items():assert files[rel]['sha256']==digest
for rel,digest in raid_qa['overlay_sha256'].items():assert files[rel.replace('\\','/')]['sha256']==digest
assert all(r['ok'] and r['actual_Application'] and r['TLS_admission']for r in ordinary_qa['actual_application'])
print(json.dumps(dict(ok=True,source_leaves=9,ordinary_maps=159,community_records=245,raid_maps=15,raid_phases=45,
    source_and_evidence_hashes_verified=True,runtime_tests_repeated=False,private_runtime_required=False,activation=False)))
