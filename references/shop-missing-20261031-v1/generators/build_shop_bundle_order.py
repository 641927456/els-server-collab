"""Stable newest-series-first local order from native package registration.

Retail release timestamps are absent. Use the first registration of each series
in the historical base table followed by the international expansion table;
later character/colour backfills keep their existing series' age.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/shop-listing-20261015'
SOURCES=('analysis/client-6c6b5180/20261014-212251/catalog-resources/PackageItemData.tables.json',
         'analysis/client-6c6b5180/20261014-210735/catalog-resources/PackageItemData_INT.tables.json')
ROLE=re.compile(r'^(?:艾索德|爱莎|蕾娜|雷文|伊芙|澄|艾拉|艾丽希斯|艾迪|露／希尔|露/希尔|萝丝|艾因|娜薇|菈比|诺亚|莉缇娅|希尔|露)')


def series(p):
    name=ROLE.sub('',p['name']).replace('稀有','')
    name=re.split(r'[（(\-]|Ver\.?',name,maxsplit=1)[0]
    return p['kind']+':'+name.removesuffix('礼包')


def build():
    data=(BASE/'fashion-bundles.json').read_bytes();c=json.loads(data)
    offers={p['template']:p for p in c['offers']}
    registration={}
    for era,source in enumerate(SOURCES):
        for ordinal,call in enumerate(json.loads((ROOT/source).read_text(encoding='utf8'))['__symbolic_calls__']):
            if call['function'].endswith('.AddPackageItemData') and call['arguments'][1] in offers:
                registration.setdefault(call['arguments'][1],(era,ordinal))
    supplement=json.loads((ROOT/'analysis/shop-missing-20261031-v1/package-membership-supplement.json').read_bytes())
    for i,row in enumerate(supplement['packages']):
        if row['template'] in offers:registration[row['template']]=(1,1000000+i)
    assert set(registration)==set(offers)
    introduced={}
    for t,p in offers.items():
        key=series(p);introduced[key]=min(introduced.get(key,(99,0)),registration[t])
    ordered=sorted(offers,key=lambda t:(-introduced[series(offers[t])][0],-introduced[series(offers[t])][1],registration[t],t))
    result=dict(client_sha256=c['client_sha256'],catalog_sha256=hashlib.sha256(data).hexdigest(),
                basis='Local newest-series-first using first native package registration: historical base then INT expansion; no retail release dates inferred. Later character/colour backfills retain the age of their series.',
                sources=[dict(path=p,sha256=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()) for p in SOURCES],
                templates=ordered,series={str(t):dict(name=series(p),first_registration=introduced[series(p)],registration=registration[t]) for t,p in offers.items()})
    (BASE/'bundle-order.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Ordered',len(ordered),'bundles; first:',[(t,offers[t]['name']) for t in ordered[:5]])


if __name__=='__main__':build()
