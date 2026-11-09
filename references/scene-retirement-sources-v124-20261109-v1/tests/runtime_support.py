"""Explicit caller-supplied server/resource fixture; no private paths or downloads."""
from pathlib import Path
import argparse, ast, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[1]
def server_root():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--server-root',required=True,type=Path)
    args,remaining=parser.parse_known_args()
    sys.argv=[sys.argv[0],*remaining]
    root=args.server_root.resolve()
    bindings=json.loads((ROOT/'test-dependencies.json').read_bytes())
    for row in bindings['files']:
        actual=hashlib.sha256((root/row['path']).read_bytes()).hexdigest()
        assert actual in (row['tested_parent_sha256'],row['current_v123_sha256']),row['path']
    actual=hashlib.sha256((root/'els_server/domain/scene_retirement_sources.py').read_bytes()).hexdigest()
    assert actual==bindings['baseline_retirement_sha256'],'Use a parent fixture, not an installed candidate'
    return root
def added_rules():
    tree=ast.parse((ROOT/'source/els_server/domain/scene_retirement_sources.py').read_text())
    return ast.literal_eval(tree.body[-1].value)
