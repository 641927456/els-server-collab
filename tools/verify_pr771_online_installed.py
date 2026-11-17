"""Verify the exact installed source archive and sanitized result binding."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-online-installed-20261103-v2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    m=read(P/'manifest.json');v=read(P/'validation.json');receipt=read(P/'installation-receipt.json')
    assert m['source_candidate_git_head']=='9bb522e7ae96b99e9c3b40611ff39a768ba5aba7'
    assert m['installed_release']==receipt['release']=='native-pr771-gameplay-racing-20261103-v2'
    assert m['installed_manifest_sha256']==receipt['manifest_sha256']==sha(P/'runtime-manifest.json')
    assert m['installed_parent_manifest_sha256']==sha(P/'parent-runtime-manifest.json')
    assert m['installed_parent_release']=='native-attendance-projection-reuse-20261103-v4'
    assert v['ok']and m['combined_sources']==v['combined_sources']==59 and v['changed_sources']==4
    assert m['installed_runtime_files']==v['installed_runtime_files']==receipt['runtime_files_verified']==1474
    assert m['installed_delta']==receipt['source_delta']==59 and m['installed_new_files']==23
    assert not any(m[k]for k in('installation_DDL','client_changes','original_EXE_KOM_changes','Git_merge','local_installed','launcher_changed'))
    assert m['master_road_HP_unchanged']and m['local_pointer_unchanged']and m['launcher_pointer_unchanged']
    prior={r['path']:r for r in read(ROOT/'references/pr771-racing-full-20261103-v1/combined-files.json')['files']}
    parent={r['path']:r for r in read(P/'parent-runtime-manifest.json')['files']}
    installed={r['path']:r for r in read(P/'runtime-manifest.json')['files']}
    assert len(prior)==59 and len(parent)==1451 and len(installed)==1474
    assert len(m['files'])==4
    for r in m['files']:
        rel=r['path'];assert prior[rel]['sha256']==r['prior_candidate_sha256']==sha(P/'candidate-before'/rel)
        assert parent[rel]['sha256']==r['installed_parent_sha256']==sha(P/'parent'/rel)
        assert installed[rel]['sha256']==v['source_hashes'][rel]==r['sha256']==sha(P/'online'/rel)
        assert(P/'online'/rel).stat().st_size==r['size']
        ast.parse((P/'online'/rel).read_bytes())
        prior[rel]=dict(r,archive=P.relative_to(ROOT).as_posix())
    combined=read(P/'combined-files.json');assert {r['path']:r for r in combined['files']}==prior
    assert combined['online_manifest_sha256']==m['installed_manifest_sha256']
    expected=dict(parent)
    for rel,r in prior.items():
        assert sha(ROOT/r['archive']/'online'/rel)==r['sha256']==installed[rel]['sha256']
        expected[rel]=dict(path=rel,size=r['size'],sha256=r['sha256'])
    assert expected==installed
    for name,digest in v['evidence_hashes'].items():assert sha(P/name)==digest
    tests=read(P/'rebase-tests.json');assert tests['ok']and tests['tests']==22 and not tests['skipped']and not tests['errors']
    assert tests['import_paths_verified']and not tests['production_database_used']
    assert tests['test_sha256']==sha(P/'evidence/rebase-test-source.py')
    assert tests['source_hashes']=={rel:r['sha256']for rel,r in prior.items()}
    runtime=read(P/'runtime-manifest.json');binding=runtime['source_binding']
    assert binding['rebase_test_sha256']==sha(P/'rebase-tests.json')and binding['head']==m['source_candidate_git_head']
    assert runtime['new_tables']==m['new_lazy_table_definitions']==receipt['new_lazy_table_definitions']
    assert len(runtime['new_tables'])==6 and runtime['master_road_HP_unchanged']
    public=read(P/'public-acceptance.json');assert public['ok']and public['public_TLS']and public['controlled_QA']and public['own_accounts']==6
    assert len(public['checks'])==8 and public['all_six_receipts_settled']and public['server_plan_bound']
    assert public['initial_growth_fixture']==[200,0,0,0,0,0]
    assert not public['natural_GUI']and not public['natural_battle']and receipt['observation_seconds']>=120
    assert all(receipt[k]for k in('ok','online_installed','own_QA_cleaned','publication_closed','progress_public_readback'))
    assert not any(receipt[k]for k in('player_database_restore','Git_merge','local_installed','launcher_changed','natural_GUI','natural_battle'))
    clean=read(P/'cleanup-summary.json');assert clean['ok']and clean['writer_barrier_passed']and clean['capacity_delta_verified']and clean['protected_authentication_rows_preserved']
    assert clean['slots_freed']==6 and clean['own_tasks_removed']==3 and clean['own_stage_count_removed']==2
    assert clean['own_publication_locks_released']and clean['invalid_credential_removed']and not clean['game_database_modified']
    progress=read(P/'progress-readback.json');assert progress['ok']and progress['scores_unchanged']and progress['record']['online_installed']
    backup=read(P/'backup-policy.json');assert backup['first_attempt']['failed_before_stop']and backup['first_attempt']['service_untouched']
    controller=P/'evidence/publication-control.py';assert backup['successful_attempt']['control_sha256']==sha(controller)
    assert 'EXPECTED_REQ_SHA='+repr(backup['successful_attempt']['requirements_sha256'])in controller.read_text('utf8')
    ast.parse(controller.read_bytes());ast.parse((P/'evidence/rebase-test-source.py').read_bytes())
    print(json.dumps(dict(ok=True,installed_sources=59,rebased_sources=4,installed_runtime_files=1474,recorded_rebase_cases=22,recorded_public_accounts=6,business_tests_executed_by_this_check=False,server_actions=False)))
if __name__=='__main__':main()
