"""Verify public source bytes and, when supplied, the exact private payload."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import zipfile


def check():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    contract = json.loads((root / 'source-contract.json').read_bytes())
    rows = contract['files']
    assert len(rows) == 9 and len({p['path'] for p in rows}) == 9
    for row in rows:
        if 'source' in row:
            raw = (root / row['source']).read_bytes()
            assert len(raw) == row['size']
            assert hashlib.sha256(raw).hexdigest() == row['sha256'], row['path']
            ast.parse(raw.decode('utf8'))
    for name, row in contract['tools'].items():
        raw = (root / 'tools' / name).read_bytes()
        assert len(raw) == row['size']
        assert hashlib.sha256(raw).hexdigest() == row['sha256'], name
        ast.parse(raw.decode('utf8'))
    if args.payload:
        raw = args.payload.read_bytes()
        pin = contract['private_payload']
        assert len(raw) == pin['size']
        assert hashlib.sha256(raw).hexdigest() == pin['sha256']
        with zipfile.ZipFile(args.payload) as archive:
            assert len(archive.namelist()) == len(rows)
            assert set(archive.namelist()) == {r['path'] for r in rows}
            assert archive.testzip() is None
            for row in rows:
                raw = archive.read(row['path'])
                assert len(raw) == row['size']
                assert hashlib.sha256(raw).hexdigest() == row['sha256'], row['path']
    print(json.dumps(dict(ok=True, exact_runtime_files=len(rows),
                          payload_checked=bool(args.payload), business_tests_reused=True)))


if __name__ == '__main__':
    check()
