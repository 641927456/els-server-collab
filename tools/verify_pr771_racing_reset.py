"""Source/evidence integrity for the native crystal reset candidate."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-racing-reset-20261103-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())

def main():
    m=read(P/'manifest.json');v=read(P/'validation.json');t=read(P/'targeted-results.json')
    assert m['prior_candidate_git_head']=='5b8bc83a29fd76e8f05300c3604a2e5c1a287461'
    assert m['new_lazy_tables']==['mount_reset_receipts']and not m['installation_DDL']and not m['client_changes']and not m['original_EXE_KOM_changes']
    assert v['ok']and v['reset_inventory_transaction']and v['combined_sources']==44 and v['targeted_passed_cases']==28
    assert not any(v[k]for k in ('installed','natural_GUI','public_QA','full_racing_ready','race_reward_writer'))
    prior={r['path']:r for r in read(ROOT/'references/pr771-racing-local-20261103-v1/combined-files.json')['files']}
    online={r['path']:r for r in read(ROOT/'references/pr771-firstbatch-20261103-v1/parent-manifest.json')['files']}
    assert len(m['files'])==7
    for r in m['files']:
        rel=r['path'];p=P/'online'/rel;assert sha(p)==r['sha256']==v['source_hashes'][rel]and p.stat().st_size==r['size']
        old=prior.get(rel)or online.get(rel)
        assert (old['sha256']if old else None)==r['prior_candidate_sha256']
        if old:assert sha(P/'parent'/rel)==old['sha256']
        if p.suffix=='.py':ast.parse(p.read_text('utf8'))
        prior[rel]=dict(r,archive=str(P.relative_to(ROOT)).replace('\\','/'))
    combined=read(P/'combined-files.json')['files'];assert {r['path']:r for r in combined}==prior and len(combined)==44
    for r in combined:assert sha(ROOT/r['archive']/'online'/r['path'])==r['sha256']
    for name,digest in v['evidence_hashes'].items():assert sha(P/name)==digest
    first=read(P/'tests-first.json');last=read(P/'tests-selected.json');reg=read(P/'regressions.json')
    assert first['ok']and first['tests']==8 and last['ok']and last['tests']==1 and reg['ok']and reg['tests']==20
    assert not first['errors']and not last['errors']and not reg['errors']and not first['skipped']and not last['skipped']and not reg['skipped']
    assert first['source_hashes']==last['source_hashes']==reg['source_hashes']==t['source_hashes']==v['source_hashes']
    assert t['distinct_passed_cases']==28 and t['unchanged_reset_cases_reused']==7 and t['extended_reset_case_rerun']==1
    assert t['test_sha256']==last['test_sha256']==sha(P/'test_reset.py')and t['reused_property_cases']==400
    for name,digest in reg['test_hashes'].items():assert sha(ROOT/'tests'/(name+'.py'))==digest
    assert reg['old_growth_test_sha256']==sha(ROOT/'references/pr771-racing-local-20261103-v1/test_racing.py')
    previous=read(ROOT/'references/pr771-racing-local-20261103-v1/validation.json')
    for rel,digest in t['unchanged_rule_sources'].items():assert previous['source_hashes'][rel]==digest
    items=read(P/'native-items.json');assert sha(P/'native-items.json')==sha(P/'online/els_server/data/mount_racing_items.json')
    assert [r['template']for r in items['items']]==[714108,714109,714118]
    assert [r['group']for r in items['items']]==[4,3,4]and [r['max_stack']for r in items['items']]==[300,500,300]
    assert all(len(r['cases'])==2 and all(c['ok']and c['consumed']==304 for c in r['cases'])for r in items['items'])
    native=read(P/'native-reset-consumer.json');contract=read(P/'native-contract.json')
    assert native['ok']and native['full_receiver_returned']and native['consumed']==375 and native['failure_reply_consumed']==27 and native['failure_unchanged']
    assert native['source_sha256']==v['source_hashes']['els_server/protocol/mount_messages.py']
    assert native['target']['stats']!={str(k):val for k,val in native['foreign']['stats'].items()}
    assert native['target']['experience']==native['foreign']['experience']==11300
    assert native['inventory_application_observed']==[dict(uid=0,group=4,slot=3,template=0,count=0)]
    assert not native['inventory_apply_function_executed']and native['UI_closed']and native['acknowledgement_service_stubbed']
    assert native['image_sha256']==items['image_sha256']==contract['image_sha256']=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    assert native['private_Unicorn']and not native['live_process']and not native['original_EXE_KOM_modified']
    assert contract['request']['kind']==0xa8e and contract['response']['kind']==0xa8f and contract['producer_static_proof']and not contract['original_request_captured']
    assert contract['helper_sha256']==sha(ROOT/'references/pr771-racing-local-20261103-v1/prove_native_growth.py')
    for name in ('build_items.py','test_reset.py','run_tests.py','run_regressions.py','prove_reset_consumer.py'):ast.parse((P/name).read_text('utf8'))
    print(json.dumps(dict(ok=True,combined_sources=44,changed_sources=7,reset_transaction=True,business_tests_executed_by_this_check=False,full_racing_ready=False,installed=False)))
if __name__=='__main__':main()
