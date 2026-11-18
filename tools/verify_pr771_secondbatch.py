"""Verify the selective second-batch archive; never start or install a server."""
import ast,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'references/pr771-secondbatch-20261103-v1'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    m=json.loads((PACKAGE/'manifest.json').read_bytes())
    assert digest(PACKAGE/m['parent_manifest'])==m['parent_manifest_sha256']
    assert len(m['files'])==5 and not m['source_schema_changes']and m['client_changes']==0
    for row in m['files']:
        p=Path(row['path']);assert not p.is_absolute()and '..'not in p.parts and p.parts[0]=='els_server'
        candidate=PACKAGE/'online'/p
        assert candidate.stat().st_size==row['size']and digest(candidate)==row['sha256']
        ast.parse(candidate.read_text(encoding='utf8'))
        if row['parent_sha256']is not None:assert digest(PACKAGE/'parent'/p)==row['parent_sha256']
    for name in('boosting_2026_region_entries.py','boosting_2026_quests.py'):
        source=(PACKAGE/'online/els_server/domain'/name).read_text(encoding='utf8')
        assert 'ACTIVE_QUEST_LIMIT'in source and '>=30'not in source
    validation=json.loads((PACKAGE/'validation.json').read_bytes())
    assert validation['ok']and validation['unique_tests']==15 and not validation['skipped']and not validation['installed']
    tree=ast.parse((PACKAGE/'test_secondbatch.py').read_text(encoding='utf8'))
    assert sum(isinstance(n,ast.FunctionDef)and n.name.startswith('test_')for n in ast.walk(tree))==15
    print(json.dumps(dict(ok=True,candidate_only=True,source_files=5,reported_business_cases=15,runtime_or_player_write=False)))

if __name__=='__main__':main()
