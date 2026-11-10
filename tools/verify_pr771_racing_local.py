"""Verify qualified local-policy/source archives, without claiming a race rerun."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-racing-local-20261103-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())

def main():
    m=read(P/'manifest.json');v=read(P/'validation.json');t=read(P/'targeted-results.json')
    assert m['prior_candidate_git_head']=='2625f95678d1e98f1ddbaf11fb94aedeb3db0da3'
    assert m['new_lazy_tables']==['mount_growth']and not m['installation_DDL']and not m['client_changes']and not m['original_EXE_KOM_changes']
    assert v['ok']and v['local_policy_authorized']and v['targeted_passed_cases']==28 and v['skipped']==0
    assert not any(v[k]for k in ('official_probabilities_verified','full_racing_ready','race_reward_writer','reset_inventory_transaction','installed','natural_GUI','public_QA'))
    prior={r['path']:r for r in read(ROOT/'references/pr771-sixthbatch-20261103-v1/combined-files.json')['files']}
    online={r['path']:r for r in read(ROOT/'references/pr771-firstbatch-20261103-v1/parent-manifest.json')['files']}
    assert len(m['files'])==5
    for r in m['files']:
        rel=r['path'];p=P/'online'/rel;assert sha(p)==r['sha256']==v['source_hashes'][rel]and p.stat().st_size==r['size']
        old=prior.get(rel)or online.get(rel)
        assert (old['sha256']if old else None)==r['prior_candidate_sha256']
        if old:assert sha(P/'parent'/rel)==old['sha256']
        if p.suffix=='.py':ast.parse(p.read_text('utf8'))
        prior[rel]=dict(r,archive=str(P.relative_to(ROOT)).replace('\\','/'))
    assert len(prior)==39 and v['combined_sources']==39
    combined=read(P/'combined-files.json')['files'];assert {r['path']:r for r in combined}==prior
    for r in combined:assert sha(ROOT/r['archive']/'online'/r['path'])==r['sha256']
    for name,digest in v['evidence_hashes'].items():assert sha(P/name)==digest
    assert t['ok']and t['distinct_passed_cases']==28 and t['existing_mount_cases']==17 and t['new_rule_and_persistence_cases']==11
    assert t['source_hashes']==v['source_hashes']and t['test_sha256']==sha(P/'test_racing.py')
    new=read(P/'tests-final.json');last=read(P/'affected-tests-final-two.json');native=read(P/'native-growth-profile.json')
    assert new['ok']and new['tests']==11 and last['ok']and last['tests']==2 and not new['failures']and not last['failures']
    assert new['source_hashes']==last['source_hashes']==v['source_hashes']
    assert new['properties']==2 and new['generated_examples_per_property']==200
    for name,digest in t['test_hashes'].items():assert sha(ROOT/'tests'/(name+'.py'))==digest
    assert native['ok']and native['decoded']==native['applied']
    assert native['applied']['level']==20 and native['applied']['experience']==11300 and sum(native['applied']['stats'].values())==30
    assert native['foreign_mount']==dict(uid=1001012,unknown=0,level=1,experience=0,stats={})
    assert native['image_sha256']=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    assert native['private_Unicorn']and not native['live_process']and not native['real_race_settlement']and not native['original_EXE_KOM_modified']
    for path,digest in native['sources'].items():assert v['source_hashes'][path]==digest
    policy=read(P/'online/els_server/data/mount_racing_local.json')
    assert policy['provenance']=='local_policy'and policy['rank_experience']==[120,100,80,60,40,20]
    assert sum(policy['points_on_level'])==30 and all(sum(w)==100 for w in policy['bonus_weights_by_rank'].values())
    for name in ('test_racing.py','run_tests.py','run_affected.py','prove_native_growth.py'):ast.parse((P/name).read_text('utf8'))
    print(json.dumps(dict(ok=True,changed_sources=5,combined_sources=39,local_policy=True,business_tests_executed_by_this_check=False,full_racing_ready=False,installed=False)))
if __name__=='__main__':main()
