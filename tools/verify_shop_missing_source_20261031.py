"""Verify exact shop source archive; runtime installation is a separate result."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'references/shop-missing-20261031-v1'
contract=json.loads((BASE/'source-contract.json').read_bytes())
assert contract['issue']==692 and contract['root_runtime_changed']is False
assert contract['status']=='qualified candidate; not installed'
source_count=0
for channel in contract['channels'].values():
    for relative,row in channel['files'].items():
        if 'source'not in row:continue
        path=ROOT/row['source']
        assert path.resolve().is_relative_to((BASE/'source').resolve())
        raw=path.read_bytes()
        assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256'],relative
        compile(raw,str(path),'exec');source_count+=1

# Exercise the archived shared classifier with independently known profiles:
# ordinary paid costume versus both current ice reward classes.
path=BASE/'source/common/els_server/domain/shop_listing.py'
tree=ast.parse(path.read_bytes());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='ordinary_cash_equipment')
space={};exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(path),'exec'),space)
classifier=space['ordinary_cash_equipment']
assert classifier(0x00402103)and classifier(0x00402203)
assert not classifier(0x00302103)and not classifier(0x20202103)
supplement=json.loads((BASE/'package-membership-supplement.json').read_bytes())
assert {r['template']for r in supplement['packages']}=={320434,320435,388023,388024}
assert all(len(set(r['contents']))==6 for r in supplement['packages'])
v=contract['validation']
assert all(row['ok']for row in v.values())
assert v['packages']['cases']==1971 and v['eyes']['cases']==17 and v['extras']['cases']==5
assert v['original_native_bodies']['new_cases']==13160
assert contract['scope']['price_ED']==50 and contract['scope']['original_EXE_KOM_changed']is False
assert contract['private_payload']['shared_in_git']is False
print(f'Shop692: {source_count} exact channel source bindings, classifier counterexamples and frozen validation verified; installation not claimed')
