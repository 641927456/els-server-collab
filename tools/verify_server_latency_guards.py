"""Verify exact channel deltas and exercise guards against each rebuilt engine."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.materialize_formal_runtime import materialize, plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--with-runtime', action='store_true')
    args = parser.parse_args()
    baseline = json.loads((ROOT / 'channels/formal-clock-20261027-v1.json').read_bytes())
    candidate = json.loads((ROOT / 'channels/server-latency-guards-20261027-v1.json').read_bytes())
    delta = json.loads((ROOT / 'references/server-latency-guards-20261027-v1/delta.json').read_bytes())
    parent = ROOT / '.runtime-cache'
    parent.mkdir(exist_ok=True)
    for channel in ('online', 'local'):
        old = {r['path']: r for r in baseline['channels'][channel]['files']}
        new = {r['path']: r for r in candidate['channels'][channel]['files']}
        changes = delta['channels'][channel]
        actual = {p for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
        assert actual == set(changes), (channel, actual)
        assert len(changes) == (7 if channel == 'local' else 6)
        for path, entry in changes.items():
            assert entry['before_sha256'] == (old[path]['sha256'] if path in old else None)
            assert all(new[path][k] == entry[k] for k in ('source', 'sha256', 'size'))
        plan(ROOT, candidate, channel)
        if not args.with_runtime:
            print(json.dumps({'ok': True, 'channel': channel, 'delta_files': len(changes), 'runtime_tests': False}))
            continue
        with tempfile.TemporaryDirectory(prefix='latency-guards-', dir=parent) as name:
            view = Path(name) / 'engine'
            materialize(ROOT, candidate, channel, view, assets_root=ROOT, link_assets=True)
            (view / 'tests').mkdir()
            for test in ('test_server_latency_guards.py', 'test_native_auxiliary_latency.py'):
                shutil.copyfile(ROOT / 'tests' / test, view / 'tests' / test)
            result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                                     '-p', 'test_*latency*.py'], cwd=view, capture_output=True)
            if result.returncode:
                sys.stderr.write(result.stderr.decode('utf8', errors='replace')[-12000:])
                raise SystemExit(result.returncode)
        print(json.dumps({'ok': True, 'channel': channel, 'delta_files': len(changes),
                          'test_summary': result.stderr.decode('utf8', errors='replace').splitlines()[-1]}))


if __name__ == '__main__':
    main()
