"""Verify the original bytes preserved while integrating six independent PRs."""
from pathlib import Path
import ast, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
contract = json.loads((ROOT / 'references/pending-source-integration-20261031-v1/source-contract.json').read_bytes())
assert [r['pr'] for r in contract['records']] == [654, 656, 660, 663, 667, 676]
assert not contract['runtime_changes'] and not contract['player_database_changes']
count = 0
for record in contract['records']:
    for row in record['files']:
        path = ROOT / row['path']
        assert path.resolve().is_relative_to(ROOT.resolve())
        raw = path.read_bytes()
        assert len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256'], row['path']
        if path.suffix == '.py':
            ast.parse(raw)
        elif path.suffix == '.json':
            json.loads(raw)
        count += 1
print(json.dumps(dict(ok=True, source_prs=6, exact_files=count, runtime_changed=False, draft669_excluded=True)))
