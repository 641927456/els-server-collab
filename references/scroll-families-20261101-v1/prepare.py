"""Build a reviewable delta against exact read-only runtime inputs; no install."""
import argparse,ast,hashlib,json,pathlib,zipfile
p=argparse.ArgumentParser();p.add_argument('--mode',choices=('online','local'),required=True);p.add_argument('--runtime',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);args=p.parse_args()
here=pathlib.Path(__file__).resolve().parent
contract_raw=(here/'source-contract.json').read_bytes();contract=json.loads(contract_raw);baseline=contract['baselines'][args.mode]
def sha(raw):return hashlib.sha256(raw).hexdigest()
assert sha((args.runtime/baseline['manifest']).read_bytes())==baseline['manifest_sha256'],'Different runtime manifest'
contents={}
for row in contract['files'][args.mode]:
    raw=(here/row['source']).read_bytes();assert sha(raw)==row['sha256'],row['source']
    target=args.runtime/row['target'];old=target.read_bytes()if target.exists()else None
    assert (sha(old)if old is not None else None)==row['baseline_sha256'],row['target']
    if row['target'].endswith('.py'):ast.parse(raw,filename=row['target'])
    if row['sha256']!=row['baseline_sha256']:contents[row['target']]=raw
receipt=dict(mode=args.mode,base_release=baseline['release'],base_manifest_sha256=baseline['manifest_sha256'],source_contract_sha256=sha(contract_raw),files={p:sha(raw)for p,raw in contents.items()},installation=False)
with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED)as archive:
    for name,raw in sorted(contents.items()):archive.writestr(name,raw)
    archive.writestr('scroll-candidate-manifest.json',json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(ok=True,mode=args.mode,changed_files=len(contents),sha256=sha(args.output.read_bytes()),installation=False)))
