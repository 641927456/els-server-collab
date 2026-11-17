"""Flag unlabelled direct-use probes for the pinned DX11 confirmation sender.

This checks evidence scope, not whether a gameplay feature works. Run in CI as
python -B tools/check_native_use_test_scope.py. It never executes game probes.
"""
from pathlib import Path
import argparse,hashlib,json,re

ROOT=Path(__file__).resolve().parents[1]
CALL=re.compile(r'(?:\bfn|\bNativeFunction)\s*\([^\r\n]*?0x(?:2260fd0|22611d0)\b',re.I)
MARKER='NATIVE_USE_TEST_SCOPE: confirmation_only'

def inspect(path):
    source=path.read_text('utf8')
    lines=[i for i,line in enumerate(source.splitlines(),1) if CALL.search(line)]
    if not lines:return None
    return dict(path=path.relative_to(ROOT).as_posix(),lines=lines,
                scope='confirmation_only' if MARKER in source else 'unlabelled',
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    # A reference to the address alone must not be counted as a direct call.
    assert CALL.search("fn(0x2260fd0,'void',args)(controller)")
    assert CALL.search("new NativeFunction(m.base.add(0x22611d0),'void',args)(controller)")
    assert not CALL.search("prefixes={0x2260fd0:expected}")
    rows=[row for path in sorted((ROOT/'tools').iterdir())
          if path.suffix in ('.py','.js') and path.name!=Path(__file__).name
          if (row:=inspect(path)) is not None]
    missing=[r['path'] for r in rows if r['scope']=='unlabelled']
    report=dict(passed=not missing,scope='tools/*.py and tools/*.js; pinned DX11 direct confirmation calls',
                direct_confirmation_probes=rows,missing_scope_labels=missing,
                proves_gameplay_functionality=False)
    if args.output:args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(dict(passed=report['passed'],probes=len(rows),missing_scope_labels=missing)))
    if missing:raise SystemExit(1)

if __name__=='__main__':main()
