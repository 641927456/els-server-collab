"""Verify the independent first-batch archive; never install or open player state."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'references/pr771-firstbatch-20261103-v1'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    manifest=json.loads((PACKAGE/'manifest.json').read_bytes())
    parent=json.loads((PACKAGE/'parent-manifest.json').read_bytes())
    assert digest(PACKAGE/'parent-manifest.json')==manifest['parent_manifest_sha256']
    assert parent['release']==manifest['parent']=='native-entry-boost-reward-sync-20261102-v1'
    assert len(manifest['files'])==7
    for row in manifest['files']:
        path=Path(row['path'])
        assert not path.is_absolute() and '..'not in path.parts and path.parts[0]=='els_server'
        source=PACKAGE/'online'/path
        assert source.stat().st_size==row['size'] and digest(source)==row['sha256']
        if row['parent_sha256'] is not None:assert digest(PACKAGE/'parent'/path)==row['parent_sha256']
        if source.suffix=='.py':ast.parse(source.read_text(encoding='utf8'))
    relative='els_server/data/consumable_extensions.json'
    old=json.loads((PACKAGE/'parent'/relative).read_bytes());new=json.loads((PACKAGE/'online'/relative).read_bytes())
    assert new['quick'][:len(old['quick'])]==old['quick']
    assert {r['template']for r in new['quick'][len(old['quick']):]}=={135402,78982,78360,78370,78380,78390,78400,78410,712040,712041}
    assert {k:v for k,v in old.items()if k!='quick'}=={k:v for k,v in new.items()if k!='quick'}
    assert new['new_acquisition_sources']is False and new['owned_use_only']is True
    scope=json.loads((PACKAGE/'scope.json').read_bytes())
    assert set(scope['permanent_pet_variants'])=={161117,301579,100000120,100003044,720856,720849}
    result=json.loads((PACKAGE/'validation.json').read_bytes())
    assert result['ok']and result['unique_tests']==15 and not result['skipped']
    assert not result['installed']and not result['public_QA']and not result['natural_GUI']
    ast.parse((PACKAGE/'test_firstbatch.py').read_text(encoding='utf8'))
    print(json.dumps(dict(ok=True,candidate_only=True,source_files=7,reported_business_cases=15,
        parent=manifest['parent'],runtime_or_player_write=False)))

if __name__=='__main__':main()
