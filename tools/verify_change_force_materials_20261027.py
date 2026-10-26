"""Validate exact archived source bytes and an optional independently accepted parent."""
import argparse,ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];ART=ROOT/'references/native-change-force-materials-20261027-v1'
MANIFEST_SHA='1abd059944a74bb96e926090e72a08b0d90e4e5d31a77b6e7bc3755378577766'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--channel',choices=('online','local'),default='online');p.add_argument('--parent',type=Path);p.add_argument('--full-parent',action='store_true');a=p.parse_args()
 assert sha(ART/'manifest.json')==MANIFEST_SHA;m=json.loads((ART/'manifest.json').read_bytes());c=m['channels'][a.channel];rows=c['runtime_leaves']
 assert len(rows)==16 and len({r['path']for r in rows})==16 and sum(r['new_file']for r in rows)==3
 assert m['new_tables']==0 and m['install_DDL']==0
 for row in rows:
  path=ART/row['archive_path'];assert sha(path)==row['sha256']and path.stat().st_size==row['size'];assert row['new_file']==(row['parent_sha256']is None)
  if path.suffix=='.py':ast.parse(path.read_text('utf-8-sig'))
  elif path.suffix=='.json':json.loads(path.read_bytes())
 if a.parent:
  mf=a.parent/c['parent_manifest_name'];assert sha(mf)==c['parent_manifest_sha256'];d=json.loads(mf.read_bytes());assert d['release']==c['parent_release'];parent={r['path']:r for r in d['files']}
  for row in rows:assert row['parent_sha256']==parent.get(row['path'],{}).get('sha256')
  if a.full_parent:
   for row in parent.values():assert sha(a.parent/row['path'])==row['sha256']
 print(json.dumps(dict(ok=True,channel=a.channel,delta16=True,new_files3=True,new_schema0=True,installDDL0=True,full_parent=a.full_parent)))
if __name__=='__main__':main()
