"""Frozen source/evidence integrity; no claim of a business or native rerun."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-sixthbatch-20261103-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    m=read(P/'manifest.json');v=read(P/'validation.json')
    assert m['prior_candidate_git_head']=='e7011286bcf735c710a5c0252323284a4300096e'
    assert m['parent']=='native-entry-boost-reward-sync-20261102-v1'
    assert m['new_lazy_tables']==[]and not m['installation_DDL']and not m['client_changes']and not m['original_EXE_KOM_changes']
    assert v['ok']and v['targeted_passed_cases']==7 and v['skipped']==0
    assert not any(v[k]for k in ('installed','public_QA','natural_GUI','natural_battle','all_three_completed','new_mount_growth_writer'))
    expected={'els_server/domain/'+n+'.py'for n in ('dungeon_routes','dungeon_flow','local_session','dungeon_settlement_commands','friends_spawns')}
    assert {r['path']for r in m['files']}==expected
    prior={r['path']:r for r in read(ROOT/'references/pr771-fifthbatch-20261103-v1/combined-files.json')['files']}
    online={r['path']:r for r in read(ROOT/'references/pr771-firstbatch-20261103-v1/parent-manifest.json')['files']}
    for r in m['files']:
        rel=r['path'];source=P/'online'/rel;parent=P/'parent'/rel
        assert sha(source)==r['sha256']==v['source_hashes'][rel]and source.stat().st_size==r['size']
        assert sha(parent)==r['prior_candidate_sha256']==(prior[rel]if rel in prior else online[rel])['sha256']
        assert r['online_parent_sha256']==online[rel]['sha256']
        ast.parse(source.read_text('utf8'));ast.parse(parent.read_text('utf8'))
        prior[rel]=dict(r,archive=str(P.relative_to(ROOT)).replace('\\','/'))
    for name,digest in v['evidence_hashes'].items():assert sha(P/name)==digest
    combined=read(P/'combined-files.json');assert len(combined['files'])==35
    assert {r['path']:r for r in combined['files']}==prior
    for r in combined['files']:assert sha(ROOT/r['archive']/'online'/r['path'])==r['sha256']
    t=read(P/'targeted-results.json');last=read(P/'tests-scripted-final.json')
    assert t['ok']and t['distinct_passed_cases']==7 and t['skipped']==0
    assert last['ok']and last['tests']==2 and last['skipped']==0 and not last['errors']and last['import_paths_verified']
    assert t['source_hashes']==last['source_hashes']==v['source_hashes']
    assert last['test_sentry_carry_sha256']==sha(P/'test_sentry_carry.py')
    for name,digest in last['test_hashes'].items():assert sha(ROOT/'tests'/(name+'.py'))==digest
    for name in ('test_sentry_carry.py','run_affected.py','prove_stage_retention.py','prove_sentry_relocation.py'):ast.parse((P/name).read_text('utf8'))
    retention=read(P/'native-stage-retention.json');move=read(P/'native-sentry-relocation.json')
    assert retention['image_sha256']==move['image_sha256']=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    assert len(retention['cases'])==5 and sum(c['full_function_returned']for c in retention['cases'])==2
    assert move['full_selector_returned']and len(move['cases'])==2
    assert all(c['owner_and_actor_storage_unchanged']for c in move['cases'])
    assert retention['original_image_unchanged']and move['original_image_unchanged']and not retention['live_process']and not move['live_process']
    print(json.dumps(dict(ok=True,combined_sources=35,changed_sources=5,business_tests_executed_by_this_check=False,installed=False)))
if __name__=='__main__':main()
