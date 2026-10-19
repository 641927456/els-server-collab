"""Compare this checkout to a declared channel snapshot; never deploy or write state."""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--channel',choices=['local','online'],required=True);p.add_argument('--snapshot',help='Explicit repository-relative historical snapshot');a=p.parse_args()
 active=json.loads((ROOT/'channels/active.json').read_text('utf8'))
 selected=a.snapshot or active.get(a.channel+'_snapshot') or (active.get('snapshot') if active.get('channel')==a.channel else None) or ('channels/'+a.channel+'-20261019.json')
 snapshot=(ROOT/selected).resolve();assert snapshot.is_relative_to(ROOT)
 doc=json.loads(snapshot.read_text('utf8'));assert doc['channel']==a.channel;different=[]
 for row in doc['source_files']:
  path=ROOT/row['path'];assert path.resolve().is_relative_to(ROOT)
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:different.append(row['path'])
 print(json.dumps(dict(ok=not different,channel=a.channel,formal_release=doc['formal_release'],checked=len(doc['source_files']),differences=different,server_deployed=False)))
 return bool(different)
if __name__=='__main__':raise SystemExit(main())
