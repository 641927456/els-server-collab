"""Portable source identity and narrow production-predicate checks."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import sys

sys.dont_write_bytecode = True
AREA = Path(__file__).resolve().parent
contract = json.loads((AREA / 'source-contract.json').read_bytes())
assert contract['schema_version'] == 1
assert contract['delivery_delta']['server_files'] == 2
assert contract['delivery_delta']['support_behavior_changes'] == 0
assert len(contract['files']) == 14
roles = {}
for item in contract['files']:
    path = AREA / item['path']
    assert path.resolve().is_relative_to(AREA.resolve())
    data = path.read_bytes()
    assert len(data) == item['size'], item['path']
    assert hashlib.sha256(data).hexdigest() == item['sha256'], item['path']
    roles[item['role']] = roles.get(item['role'], 0) + 1
    if path.suffix == '.py':
        ast.parse(data.decode('utf-8-sig'), filename=item['path'])
assert roles == {'server_candidate': 2, 'negative_regression_baseline': 2,
                 'unchanged_installed_support_archive': 10}
subprocess.run([sys.executable, '-B', str(AREA / 'tests/verify_launcher_inputs.py')], check=True)
subprocess.run([sys.executable, '-B', str(AREA / 'tests/test_server_predicates.py')], check=True)
print(json.dumps({'ok': True, 'source_identities': 14, 'predicate_tests': 8,
                  'game_started': False, 'server_started': False, 'network_used': False,
                  'private_validation_reused': True, 'natural_gameplay_verified': False}))
