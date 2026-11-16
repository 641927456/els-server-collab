"""Exact frozen source/evidence integrity; does not execute private QA."""
from pathlib import Path
import ast,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-racing-full-20261103-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    m=read(P/'manifest.json');v=read(P/'validation.json');t=read(P/'targeted-results.json')
    assert m['prior_candidate_git_head']=='ae5f37e7daab8b9c607c035f0d15e496e8098d6b'
    assert m['new_lazy_tables']==['mount_races','mount_race_results','mount_race_busy']
    assert not m['installation_DDL']and not m['client_changes']and not m['original_EXE_KOM_changes']
    assert v['ok']and v['code_closed']and v['race_controller_implemented']and v['race_reward_writer']and v['master_road_HP_unchanged']
    assert not any(v[k]for k in('installed','natural_GUI','public_QA','production_release_ready','full_scene_physics_validated'))
    assert v['changed_sources']==len(m['files'])==23 and v['combined_sources']==m['combined_sources']==59
    assert v['targeted_passed_cases']==t['distinct_passed_cases']==len(t['cases'])==61 and t['skipped']==0
    assert t['source_hashes']==v['source_hashes']and t['actual_server_race_growth']and t['property_examples']==400
    previous={r['path']:r for r in read(ROOT/'references/pr771-racing-reset-20261103-v1/combined-files.json')['files']}
    online={r['path']:r for r in read(ROOT/'references/pr771-firstbatch-20261103-v1/parent-manifest.json')['files']}
    for row in m['files']:
        rel=row['path'];p=P/'online'/rel;assert p.suffix in('.py','.json')
        assert sha(p)==row['sha256']==v['source_hashes'][rel]and p.stat().st_size==row['size']
        old=previous.get(rel)or online.get(rel)
        assert row['prior_candidate_sha256']==(old['sha256']if old else None)
        if old:assert sha(P/'parent'/rel)==old['sha256']
        if p.suffix=='.py':ast.parse(p.read_text('utf8'))
        previous[rel]=dict(row,archive=P.relative_to(ROOT).as_posix())
    assert {r['path']:r for r in read(P/'combined-files.json')['files']}==previous
    for row in previous.values():assert sha(ROOT/row['archive']/'online'/row['path'])==row['sha256']
    for name,digest in v['evidence_hashes'].items():assert sha(P/name)==digest
    reports=['tests-targeted.json','tests-selected.json','tests-exchange.json','tests-flow.json','tests-shared.json','tests-shared-selected.json','tests-shared-wire.json']
    passed={}
    for name in reports:
        report=read(P/name);assert report['import_paths_verified']and report['skipped']==0
        assert set(report['source_hashes'])==set(v['source_hashes'])
        assert {p for p,h in report['source_hashes'].items()if h!=v['source_hashes'][p]}<= {'els_server/domain/friends_racing.py'}
        for entry in report['passed']:
            identity=re.fullmatch(r'(\w+) \(([^)]+)\)',entry)[2]
            identity=identity.replace('existing_world_faults.WorldCleanup.','test_shared.CurrentWorld.').replace('test_qualification_busy_reset_and_crash_login_release','test_qualification_duplicate_start_and_crash_login_release')
            passed[identity]=name
    assert passed==t['cases']
    for name in('tests-selected.json','tests-exchange.json','tests-flow.json','tests-shared-wire.json'):assert read(P/name)['ok']
    assert read(P/'tests-flow.json')['source_hashes']==v['source_hashes']and read(P/'tests-flow.json')['tests']==8
    for name,digest in t['external_test_hashes'].items():assert sha(ROOT/'tests'/name)==digest
    for name,digest in t['test_hashes'].items():assert sha(P/name)==digest
    assert sha(P/'run_tests.py')==t['runner_sha256']
    native=read(P/'native-racing-decoders.json');curves=read(P/'native-racing-curves.json');reset=read(P/'native-reset-consumer.json');contract=read(P/'native-contract.json')
    image='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    assert native['ok']and curves['ok']and reset['ok']
    assert native['image_sha256']==curves['image_sha256']==reset['image_sha256']==contract['image_sha256']==image
    assert native['full_A85_receiver_returned']and len(native['native_runtime'])==len(native['native_members'])==len(native['result_roster'])==6
    assert native['admission_wire_bytes']==27126 and native['slot_vector_bytes']==372
    assert all(r['normal']==22 and r['obstacles']==4 for r in native['boosters'])
    assert all(r['unit']==105 and r['mount']>0 for r in native['native_members']+native['result_roster'])
    assert native['test_sha256']==sha(P/'prove_native_race.py')and curves['test_sha256']==sha(P/'prove_native_curves.py')
    for report in(native,curves):
        for rel,digest in report['sources'].items():assert digest==v['source_hashes'][rel]
    assert len(curves['cases'])==5 and sum(len(c['checked'])for c in curves['cases'])==35
    assert all(x['actual']==x['expected']for c in curves['cases']for x in c['checked'])
    assert curves['scene_actor_vector_empty']and not curves['rendering_executed']and not curves['natural_GUI']
    assert reset['full_receiver_returned']and reset['target']['unknown']==reset['foreign']['unknown']==105
    assert reset['source_sha256']==v['source_hashes']['els_server/protocol/mount_messages.py']and reset['failure_unchanged']
    assert native['private_fixture_sha256']==contract['private_fixture_sha256']and not contract['raw_fixture_in_Git']and not contract['full_scene_physics_validated']
    assert not(P/'native-inputs.json').exists()
    policy=read(P/'online/els_server/data/mount_racing_local.json')
    assert policy['provenance']=='local_policy'and policy['rank_experience']==[120,100,80,60,40,20]
    assert policy['race_adjudication_hz']==60 and sum(policy['points_on_level'])==30
    exchange=read(P/'online/els_server/data/mount_racing_exchange.json')
    assert(exchange['house'],exchange['source'],exchange['source_quantity'],exchange['destination'],exchange['quantity'])==(40016,714109,20,714108,1)
    assert exchange['towns']==list(range(20001,20014))
    for p in P.glob('*.py'):ast.parse(p.read_text('utf8'))
    print(json.dumps(dict(ok=True,changed_sources=23,combined_sources=59,recorded_business_cases=61,business_tests_executed_by_this_check=False,installed=False,production_release_ready=False)))
if __name__=='__main__':main()
