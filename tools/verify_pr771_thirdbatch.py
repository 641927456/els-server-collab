"""Check frozen selected sources; business/native execution is reported separately."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'references/pr771-thirdbatch-20261103-v1'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    mf=read(PACKAGE/'manifest.json');previous={}
    parent_path=ROOT/'references/pr771-firstbatch-20261103-v1/parent-manifest.json'
    assert digest(parent_path)==mf['parent_manifest_sha256']
    online={r['path']:r for r in read(parent_path)['files']}
    for batch in('firstbatch','secondbatch'):
        prefix=f'references/pr771-{batch}-20261103-v1'
        for row in read(ROOT/prefix/'manifest.json')['files']:previous[row['path']]=dict(row,archive=prefix)
    assert mf['parent']=='native-entry-boost-reward-sync-20261102-v1'and len(mf['files'])==22
    assert mf['new_lazy_tables']==['pet_consumable_cooldowns']and not mf['installation_DDL']and mf['client_changes']==0
    result=read(PACKAGE/'validation.json')
    assert result['ok']and result['tests']==20 and len(set(result['case_ids']))==20 and result['skipped']==0
    assert not any(result[k]for k in('installed','public_QA','natural_GUI','natural_battle'))
    assert digest(PACKAGE/'test_gaps.py')==result['test_sha256']
    ast.parse((PACKAGE/'test_gaps.py').read_text(encoding='utf8'))
    for row in mf['files']:
        rel=Path(row['path']);assert not rel.is_absolute()and'..'not in rel.parts and rel.parts[0]=='els_server'
        source=PACKAGE/'online'/rel
        assert source.stat().st_size==row['size']and digest(source)==row['sha256']==result['source_hashes'][row['path']]
        expected=previous.get(row['path'],online.get(row['path'],{})).get('sha256')
        assert row['prior_candidate_sha256']==expected
        assert row['online_parent_sha256']==online.get(row['path'],{}).get('sha256')
        if expected is not None:assert digest(PACKAGE/'parent'/rel)==expected
        if source.suffix=='.py':ast.parse(source.read_text(encoding='utf8'))
        previous[row['path']]=dict(row,archive='references/pr771-thirdbatch-20261103-v1')
    combined=read(PACKAGE/'combined-files.json')
    assert len(combined['files'])==30 and {r['path']:r for r in combined['files']}==previous
    for row in combined['files']:
        assert digest(ROOT/row['archive']/'online'/row['path'])==result['source_hashes'][row['path']]
    q=read(PACKAGE/'online/els_server/data/reselection_quest.json')['quests']['39480']
    assert(q['m_bRepeat'],q['m_eRepeatType'],q['m_eQuestType'])==(0,0,2)
    assert sorted((v['m_iItemID'],v['m_iQuantity'],v['m_iPeriod'])for v in q['Reward']['m_vecItem'].values())==[(135871,1,1),(135872,1,1)]
    print(json.dumps(dict(ok=True,candidate_only=True,selected_sources=30,third_batch_sources=22,reported_business_cases=20,business_tests_executed_by_this_check=False,runtime_or_player_write=False)))
if __name__=='__main__':main()
