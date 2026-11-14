"""Frozen candidate integrity only; business/native runs are separate evidence."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-fourthbatch-20261103-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    mf=read(P/'manifest.json');result=read(P/'validation.json')
    assert mf['prior_candidate_git_head']=='9639367a0e1aaa0b82c66db39b0cf872f9b319ce'
    prior={r['path']:r for r in read(ROOT/'references/pr771-thirdbatch-20261103-v1/combined-files.json')['files']}
    online={r['path']:r for r in read(ROOT/'references/pr771-firstbatch-20261103-v1/parent-manifest.json')['files']}
    assert mf['parent']=='native-entry-boost-reward-sync-20261102-v1'and len(mf['files'])==2
    assert mf['new_lazy_tables']==[]and not mf['installation_DDL']and mf['client_changes']==0
    assert result['ok']and result['tests']==4 and len(set(result['case_ids']))==4 and result['skipped']==0
    assert not any(result[k]for k in('installed','public_QA','natural_GUI','natural_battle'))
    assert sha(P/'test_remaining.py')==result['test_sha256']
    ast.parse((P/'test_remaining.py').read_text(encoding='utf8'))
    for name,digest in result['evidence_hashes'].items():assert sha(P/name)==digest
    for row in mf['files']:
        rel=Path(row['path']);assert not rel.is_absolute()and'..'not in rel.parts
        assert row['path']in('els_server/domain/dungeon_flow.py','els_server/protocol/mount_messages.py')
        source=P/'online'/rel;expected=prior.get(row['path'],online[row['path']])['sha256']
        assert source.stat().st_size==row['size']and sha(source)==row['sha256']==result['source_hashes'][row['path']]
        assert row['prior_candidate_sha256']==expected==sha(P/'parent'/rel)
        assert row['online_parent_sha256']==online[row['path']]['sha256']
        ast.parse(source.read_text(encoding='utf8'));prior[row['path']]=dict(row,archive=str(P.relative_to(ROOT)).replace('\\','/'))
    combined=read(P/'combined-files.json');assert len(combined['files'])==32
    assert {r['path']:r for r in combined['files']}==prior
    for row in combined['files']:assert sha(ROOT/row['archive']/'online'/row['path'])==row['sha256']
    assert result['native_initialization']['ok']and result['native_initialization']['native_level']==1
    mount=read(P/'mount-regressions.json')
    assert mount['ok']and mount['tests']==2 and not mount['skipped']and mount['import_paths_verified']
    assert mount['source_sha256']==result['source_hashes']['els_server/protocol/mount_messages.py']
    for name,digest in mount['test_hashes'].items():assert sha(ROOT/'tests'/(name+'.py'))==digest
    print(json.dumps(dict(ok=True,combined_sources=32,fourth_batch_sources=2,reported_business_cases=4,business_tests_executed_by_this_check=False,installed=False)))
if __name__=='__main__':main()
