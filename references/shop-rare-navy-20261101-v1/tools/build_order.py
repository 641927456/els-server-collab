"""Keep existing series order and place additions next to their normal sets."""
import hashlib
import json
from pathlib import Path

W=Path(__file__).resolve().parent
C=W/'candidate'
P=Path(json.loads((W/'update-binding.json').read_bytes())['parent_root'])
read=lambda p:json.loads(p.read_bytes())
base='analysis/shop-listing-20261015/'
old=read(P/base/'bundle-order.json')
current=read(C/base/'fashion-bundles.json')
scope=read(W/'candidate-scope.json')
decisions=read(C/'analysis/shop-rare-navy-20261101-v1/bundle-membership.json')['decisions']
old_offers={r['template']:r for r in read(P/base/'fashion-bundles.json')['offers']}
rank={t:i for i,t in enumerate(old['templates'])}
inserts={}
for d in decisions:
    anchors=[t for t in d['ordinary_templates']if t in rank]
    if not anchors:
        assert '水手泳装'in d['name']
        anchors=[t for t,r in old_offers.items()if '水手泳装'in r['name']]
    anchor=min(anchors,key=rank.__getitem__)
    inserts.setdefault(anchor,[]).append(d['template'])
order=[]
for t in old['templates']:
    order.append(t)
    order.extend(sorted(inserts.get(t,[])))
assert len(order)==len(set(order))==len(current['offers'])
assert set(order)=={r['template']for r in current['offers']}
old.update(catalog_sha256=hashlib.sha256((C/base/'fashion-bundles.json').read_bytes()).hexdigest(),templates=order,
    basis=old['basis']+'2026-11-01 rare/navy additions follow their existing normal set series; new Noah/Lithia sailor variants retain the same series age.')
f='analysis/shop-rare-navy-20261101-v1/bundle-membership.json'
old['sources'].append(dict(path=f,sha256=hashlib.sha256((C/f).read_bytes()).hexdigest()))
(C/base/'bundle-order.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,bundles=len(order),added=len(decisions),old_order_preserved=True)))
