"""Check the two HP support identities; execute the portable Node regression."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--identity-only',action='store_true');args=p.parse_args()
 c=json.loads((ROOT/'source-contract.json').read_bytes());rows={r['path']:r for r in c['files']}
 assert set(rows)=={'tools/native_cache_sync.js','tools/client_compatibility_profiles.json'}
 for rel,r in rows.items():
  raw=(ROOT/'source'/rel).read_bytes();assert len(raw)==r['size'] and sha(raw)==r['sha256'],rel
 js=rows['tools/native_cache_sync.js'];raw=(ROOT/'source/tools/client_compatibility_profiles.json').read_bytes()
 assert raw.count(js['sha256'].encode())==1
 original=raw.replace(js['sha256'].encode(),js['parent_sha256'].encode())
 assert sha(original)==rows['tools/client_compatibility_profiles.json']['parent_sha256']
 before,after=json.loads(original),json.loads(raw)
 assert len(after['profiles'][0]['artifacts'])==60
 assert after['profiles'][0]['artifacts']['tools/native_cache_sync.js']==js['sha256']
 after['profiles'][0]['artifacts']['tools/native_cache_sync.js']=js['parent_sha256'];assert after==before
 assert sha((ROOT/'tests/fixtures/baseline-native-cache-sections.js').read_bytes())==c['baseline_scheduler_fragment_sha256']
 subprocess.run([sys.executable,'-B',str(ROOT/'tests/verify_launcher_inputs.py')],check=True)
 if not args.identity_only:
  node=shutil.which('node')
  if node is None:raise RuntimeError('Node required; the component regression must not be silently skipped')
  subprocess.run([node,str(ROOT/'tests/test_attribute_refresh.cjs')],check=True)
 print(json.dumps({'ok':True,'source_files':2,'identity_only':args.identity_only,'node_behavior_executed':not args.identity_only,'native_game_executed':False}))
if __name__=='__main__':main()
