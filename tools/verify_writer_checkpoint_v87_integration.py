"""Verify approved writer methods integrated into the accepted V87 parent."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'refs/writer-checkpoints-v87-integration-20261107-v1'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def method(text,name):
    tree=ast.parse(text)
    owner=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Application')
    node=next(n for n in owner.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name==name)
    return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])

def main():
    binding=read(A/'source-bindings.json')
    assert binding['approved_writer_merge']=='c214cfda50acd1f196badda325d0ea61ec3f01fc'
    assert binding['runtime_parent_source_PR']==914 and binding['approved_writer_PR']==922
    assert len(binding['files'])==9 and not binding['production_installed']
    for row in binding['files'].values():
        p=ROOT/row['source'];assert p.resolve().is_relative_to(ROOT.resolve())and sha(p)==row['sha256']
        ast.parse(p.read_bytes())
    row=binding['runtime_parent_application'];parent=ROOT/row['source'];assert sha(parent)==row['sha256']
    approved=(ROOT/'refs/private-writer-checkpoints-20261107-v1/source/els_server/application.py').read_text('utf8')
    integrated=parent.read_text('utf8')
    for name in binding['changed_application_methods']:
        before=method(integrated,name);assert integrated.count(before)==1
        integrated=integrated.replace(before,method(approved,name))
    actual=(ROOT/binding['files']['els_server/application.py']['source']).read_text('utf8')
    assert actual==integrated,'Integration must preserve every other V87 application method'
    row=binding['runtime_parent_mail'];mail_parent=ROOT/row['source'];assert sha(mail_parent)==row['sha256']
    before=ast.parse(mail_parent.read_bytes());after=ast.parse((ROOT/binding['files']['els_server/storage/relationship_mail.py']['source']).read_bytes())
    old=next(n for n in before.body if isinstance(n,ast.FunctionDef)and n.name=='maintenance')
    new=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='maintenance')
    assert ast.dump(old.body[-1])==ast.dump(new.body[-1]),'Actual coupled writer branch must remain unchanged'
    before.body.remove(old);after.body.remove(new)
    assert ast.dump(before)==ast.dump(after),'All mail reward producers must remain unchanged'
    unit=read(A/'anniversary-read-first-tests.json');assert unit['passed']and unit['tests']==6 and not unit['GIL_enabled']
    assert sha(A/'tests/test_anniversary_read_first.py')==unit['test_script_sha256']and sha(A/'tests/bootstrap.py')==unit['bootstrap_sha256']
    baseline=read(A/'anniversary-baseline-tests.json');assert baseline['passed']and baseline['baseline_bug_reproduced']
    assert baseline['expected_loaded_mail_sha256_from_pinned_baseline']==row['sha256']
    proof=read(A/'local-native-read-first50-five.json')
    expected={'candidate/'+n:r['sha256']for n,r in binding['files'].items()}
    assert unit['source']==expected
    assert proof['source']==expected and proof['passed']and proof['seconds']==300
    assert proof['actors']==dict(town=20,dungeon=30,total=50,native_frontends=0)
    assert not proof['online_capacity_qualified']and proof['cold_currency_and_ACK_exact']and proof['final_town_SQL_coordinates_exact']
    assert proof['owned_runtime_removed']and proof['connections']==0 and not proof['errors']
    signed=read(A/'signed-preview-tests.json');endpoint=read(A/'compiled-endpoint-tests.json')
    assert signed['ok']and signed['components_verified']==2852 and signed['repeat_downloads']==0
    assert signed['source']=={n:r['sha256']for n,r in binding['files'].items()}
    assert signed['runtime_sha256']==binding['signed_candidate_payload_sha256']==endpoint['selected_payload_sha256']
    assert endpoint['passed']and endpoint['normal_stop']and endpoint['owned_workspace_removed']
    assert endpoint['actual_game_CPU_priority']==32 and endpoint['actual_game_IO_priority']==2
    print(json.dumps(dict(ok=True,preserved_V87_application=True,approved_writer_methods=2,local_native_actors=50,seconds=300,production_installed=False)))

if __name__=='__main__':main()
