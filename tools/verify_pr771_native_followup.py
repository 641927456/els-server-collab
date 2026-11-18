"""Check frozen follow-up evidence; do not rerun native/TLS business tests."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'references/pr771-native-followup-20261103-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    for name,digest in read(P/'manifest.json')['files'].items():assert sha(P/name)==digest
    scope=read(P/'scope.json');tls=read(P/'sentry-tls-result.json');native=read(P/'native-mount-exp-table.json')
    assert scope['production_source_changes']==0 and scope['combined_source_files']==35
    assert not scope['all_three_completed']and not scope['installed']and not scope['public_QA']and not scope['natural_GUI']
    rows=read(ROOT/scope['combined_source_reference'])['files']
    assert scope['current_candidate_hashes']=={r['path']:r['sha256']for r in rows}
    for r in rows:assert sha(ROOT/r['archive']/'online'/r['path'])==r['sha256']
    assert tls['ok']and tls['tests']==1 and tls['skipped']==0 and not tls['failures']
    assert tls['runtime_import_paths_verified']and not tls['mocked_gameplay_qualification']and not tls['installed']and not tls['natural_GUI']
    assert tls['test_sha256']==sha(P/'test_sentry_tls.py')and tls['helper_sha256']==sha(ROOT/'tests/test_friends_server.py')
    for path,digest in scope['current_candidate_hashes'].items():
        if path in tls['source_hashes']:assert tls['source_hashes'][path]==digest
    assert native['image_sha256']=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
    assert native['registered_rows']==20 and native['native_tree_payload_matches']and len(native['cases'])==7
    assert native['native_table_not_rewritten']and native['original_image_unchanged']and not native['live_process']
    assert not native['rank_award_verified']and not native['upgrade_weights_verified']and not native['server_experience_awarded']
    for name in ('test_sentry_tls.py','prove_mount_exp_table.py'):ast.parse((P/name).read_text('utf8'))
    print(json.dumps(dict(ok=True,production_source_changes=0,combined_sources=35,evidence_only=True,installed=False)))
if __name__=='__main__':main()
