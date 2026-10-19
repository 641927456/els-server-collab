"""Compare this checkout to a declared channel snapshot; never deploy or write state."""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--channel',choices=['local','online'],required=True);a=p.parse_args()
 doc=json.loads((ROOT/'channels'/(a.channel+'-20261019.json')).read_text('utf8'));different=[]
 for row in doc['source_files']:
  path=ROOT/row['path'];assert path.resolve().is_relative_to(ROOT)
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:different.append(row['path'])
 print(json.dumps(dict(ok=not different,channel=a.channel,formal_release=doc['formal_release'],checked=len(doc['source_files']),differences=different,server_deployed=False)))
 return bool(different)
if __name__=='__main__':raise SystemExit(main())
