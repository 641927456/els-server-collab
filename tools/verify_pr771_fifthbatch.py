"""Verify the frozen fifth batch; native/runtime execution is separate evidence."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-fifthbatch-20261103-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    manifest=read(P/'manifest.json');result=read(P/'validation.json')
    assert manifest['prior_candidate_git_head']=='8833b25067a42a40631946d6361f05906fd615b6'
    assert manifest['parent']=='native-entry-boost-reward-sync-20261102-v1'
    assert manifest['new_lazy_tables']==[]and not manifest['installation_DDL']and manifest['client_changes']==0
    assert result['ok']and result['tests']==3 and result['skipped']==0 and result['native_before_after']
    assert not any(result[k]for k in('installed','public_QA','natural_GUI','natural_battle','server_experience_awarded','all_remaining_completed'))
    for name,digest in result['evidence_hashes'].items():assert sha(P/name)==digest
    prior={r['path']:r for r in read(ROOT/'references/pr771-fourthbatch-20261103-v1/combined-files.json')['files']}
    assert len(manifest['files'])==1
    row=manifest['files'][0];rel=row['path'];assert rel=='els_server/protocol/mount_messages.py'
    source=P/'online'/rel;parent=P/'parent'/rel
    assert sha(source)==row['sha256']==result['source_hashes'][rel]and source.stat().st_size==row['size']
    assert sha(parent)==row['prior_candidate_sha256']==prior[rel]['sha256']
    expected=parent.read_text(encoding='utf8').replace("         +struct.pack('>QHBiI',0,0,1,0,0))", "         # D81DD0 locates the owned outer record by this nested UID.\n         +struct.pack('>QHBiI',p.get('uid',0),0,1,0,0))")
    assert source.read_text(encoding='utf8')==expected
    ast.parse(expected)
    for name in ('prove_mount_identity.py','run_mount_affected.py'):ast.parse((P/name).read_text(encoding='utf8'))
    before=read(P/'native-mount-identity-before.json');after=read(P/'native-mount-identity-fixed.json')
    assert before['source_sha256']==sha(parent)and after['source_sha256']==sha(source)
    assert before['image_sha256']==after['image_sha256']=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    assert before['nested_uid']==0 and not before['update_applied']and before['observed']==[[1,0],[1,0]]
    assert after['nested_uid']==after['outer_uid']!=0 and after['update_applied']and after['observed']==[[2,200],[1,0]]
    assert all(r['foreign_mount_unchanged']and r['private_Unicorn']and r['synthetic_growth_fixture']and not r['server_experience_awarded']and not r['live_process']for r in(before,after))
    tests=read(P/'mount-regressions.json')
    assert tests['ok']and tests['tests']==3 and not tests['skipped']and tests['import_paths_verified']and not tests['errors']
    assert tests['source_sha256']==sha(source)
    for name,digest in tests['test_hashes'].items():assert sha(ROOT/'tests'/(name+'.py'))==digest
    prior[rel]=dict(row,archive=str(P.relative_to(ROOT)).replace('\\','/'))
    combined=read(P/'combined-files.json');assert len(combined['files'])==32
    assert {r['path']:r for r in combined['files']}==prior
    for r in combined['files']:assert sha(ROOT/r['archive']/'online'/r['path'])==r['sha256']
    print(json.dumps(dict(ok=True,combined_sources=32,fifth_batch_sources=1,business_tests_executed_by_this_check=False,installed=False)))
if __name__=='__main__':main()
