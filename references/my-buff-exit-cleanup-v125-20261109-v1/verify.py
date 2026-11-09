"""Check the isolated support archive and run its portable synthetic regression."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def composer_only(parent, candidate):
    old = ast.parse(parent.read_text(encoding='utf8'))
    new = ast.parse(candidate.read_text(encoding='utf8'))
    fn = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == 'compose')
    imports = [n for n in fn.body if isinstance(n, ast.ImportFrom) and n.module == 'my_buff_cleanup']
    assert len(imports) == 1
    assert len(imports[0].names) == 1
    assert (imports[0].names[0].name, imports[0].names[0].asname) == ('compose', 'my_buff_source')
    fn.body.remove(imports[0])
    result = fn.body[-1]
    assert isinstance(result, ast.Return) and isinstance(result.value, ast.Call)
    call = result.value
    assert isinstance(call.func, ast.Name) and call.func.id == 'my_buff_source'
    assert not call.keywords and len(call.args) == 3
    assert [x.id for x in call.args[:2]] == ['snapshot', 'executable_sha256']
    result.value = call.args[2]
    assert ast.dump(new, include_attributes=False) == ast.dump(old, include_attributes=False)


def identities():
    contract = json.loads((ROOT / 'source-contract.json').read_bytes())
    rows = {r['path']: r for r in contract['files']}
    expected = {'tools/my_buff_cleanup.py', 'tools/my_buff_cleanup.js',
                'tools/native_cache_sync.py', 'tools/client_compatibility_profiles.json'}
    assert set(rows) == expected and len(contract['files']) == 4
    assert {p.relative_to(ROOT / 'source').as_posix() for p in (ROOT / 'source').rglob('*') if p.is_file()} == expected
    for rel, row in rows.items():
        path = ROOT / 'source' / rel
        assert path.stat().st_size == row['size'] and sha(path) == row['sha256'], rel
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf8'))
    for row in contract['parent_fixtures']:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
    if 'launcher_build_contract_sha256' in contract:
        assert sha(ROOT / 'launcher-build-contract.json') == contract['launcher_build_contract_sha256']
    parent = json.loads((ROOT / 'tests/fixtures/v124-client-compatibility-profiles.json').read_bytes())
    after = json.loads((ROOT / 'source/tools/client_compatibility_profiles.json').read_bytes())
    expected_profile = json.loads(json.dumps(parent))
    for before_profile, expected_row, actual in zip(parent['profiles'], expected_profile['profiles'], after['profiles'], strict=True):
        assert len(before_profile['artifacts']) == 60
        for rel in ('tools/my_buff_cleanup.py', 'tools/my_buff_cleanup.js'):
            assert rel not in before_profile['artifacts'] and rows[rel]['parent_sha256'] is None
        assert before_profile['artifacts']['tools/native_cache_sync.py'] == rows['tools/native_cache_sync.py']['parent_sha256']
        for rel in expected - {'tools/client_compatibility_profiles.json'}:
            expected_row['artifacts'][rel] = rows[rel]['sha256']
        assert len(actual['artifacts']) == 62
    assert after == expected_profile, 'Unrelated compatibility policy changed'
    composer_only(ROOT / 'tests/fixtures/v124-native-cache-sync.py', ROOT / 'source/tools/native_cache_sync.py')
    return contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity-only', action='store_true')
    args = parser.parse_args()
    contract = identities()
    if not args.identity_only:
        build = json.loads((ROOT / 'launcher-build-contract.json').read_bytes())
        assert build['status'] == 'bound_private_build', 'Actual private-build input contract is still pending'
        build_check = ROOT / 'tests/verify_launcher_inputs.py'
        assert build_check.is_file(), 'Launcher input verifier is missing'
        subprocess.run([sys.executable, '-B', str(build_check)], check=True)
        assert contract['portable_tests'], 'Portable tests are not yet archived'
        node = shutil.which('node')
        if node is None:
            raise RuntimeError('Node is required; synthetic behavior checks cannot be silently skipped')
        for row in contract['portable_tests']:
            path = ROOT / row['path']
            assert sha(path) == row['sha256'], row['path']
            if row['runtime'] == 'node':
                subprocess.run([node, str(path)], check=True)
            elif row['runtime'] == 'python':
                subprocess.run([sys.executable, '-B', str(path)], check=True)
            else:
                raise AssertionError('Unsupported portable test runtime')
    print(json.dumps({'ok': True, 'source_files': 4, 'profile_artifacts': 62,
                      'identity_only': args.identity_only,
                      'portable_behavior_executed': not args.identity_only,
                      'native_game_executed': False}))


if __name__ == '__main__':
    main()
