"""Insert qualified sets without changing the relative order of old offers."""
import collections
import hashlib
import json
import re
from pathlib import Path

W = Path(__file__).resolve().parent
C = W / 'candidate'
P = Path(json.loads((W / 'update-binding.json').read_bytes())['parent_root'])
base = Path('analysis/shop-listing-20261015')
old = json.loads((P / base / 'bundle-order.json').read_bytes())
current = json.loads((C / base / 'fashion-bundles.json').read_bytes())
scope = json.loads((W / 'candidate-scope.json').read_bytes())
offers = {p['template']: p for p in current['offers']}
old_ids = old['templates']
old_set = set(old_ids)
role = re.compile(r'^(?:艾索德|爱莎|蕾娜|雷文|伊芙|澄|艾拉|艾丽希斯|艾迪|露／希尔|露/希尔|萝丝|艾因|娜薇|菈比|诺亚|莉缇娅|希尔|露)')


def family(p):
    name = role.sub('', p['name']).replace('稀有', '')
    name = re.split(r'[（(\-]|Ver\.?', name, maxsplit=1)[0]
    return p['kind'] + ':' + name.removesuffix('礼包')


sources = ['analysis/client-6c6b5180/20261014-062215/ice-resources/IceHeaterPreView.tables.json',
           'analysis/client-6c6b5180/20261014-173316/IceHeaterPreView_INT.tables.json']
registration = {}
for era, relative in enumerate(sources):
    calls = json.loads((C / relative).read_bytes())['__symbolic_calls__']
    for ordinal, call in enumerate(calls):
        if call['function'].endswith('.AddIceHeaterItemData') and call['arguments'][1] in offers:
            registration.setdefault(call['arguments'][1], (era, ordinal))
for era, relative in enumerate(['analysis/client-6c6b5180/20261014-212251/catalog-resources/PackageItemData.tables.json',
                                 'analysis/client-6c6b5180/20261014-210735/catalog-resources/PackageItemData_INT.tables.json']):
    for ordinal, call in enumerate(json.loads((C / relative).read_bytes())['__symbolic_calls__']):
        if call['function'].endswith('.AddPackageItemData') and call['arguments'][1] in offers:
            registration.setdefault(call['arguments'][1], (era, ordinal))

old_families = collections.defaultdict(list)
for index, t in enumerate(old_ids):
    old_families[family(offers[t])].append(index)
native_old = collections.defaultdict(dict)
for t in old_ids:
    if t in registration:
        era, ordinal = registration[t]
        f = family(offers[t])
        native_old[era][f] = min(native_old[era].get(f, ordinal), ordinal)

new_families = collections.defaultdict(list)
for p in scope['added_packages']:
    new_families[family(p)].append(p['template'])
insert = collections.defaultdict(list)
decisions = []
for f, ids in new_families.items():
    assert all(t in registration for t in ids), f
    position = min(registration[t] for t in ids)
    if f in old_families:
        index = max(old_families[f]) + 1
        basis = 'existing same-series block'
    else:
        era, ordinal = position
        neighbors = native_old[era]
        assert neighbors, f
        anchor = min(neighbors, key=lambda key: abs(neighbors[key] - ordinal))
        index = min(old_families[anchor]) if ordinal >= neighbors[anchor] else max(old_families[anchor]) + 1
        basis = 'nearest existing series in native registration order: ' + anchor
    insert[index].append((position, f, sorted(ids, key=lambda t: (registration[t], t))))
    decisions.append(dict(series=f, index=index, basis=basis, native_registration=position, templates=ids))

order = []
for index in range(len(old_ids) + 1):
    for _, _, ids in sorted(insert[index], reverse=True):
        order.extend(ids)
    if index < len(old_ids):
        order.append(old_ids[index])
assert [t for t in order if t in old_set] == old_ids
assert len(order) == len(set(order)) == len(offers) and set(order) == set(offers)
old['templates'] = order
old['catalog_sha256'] = hashlib.sha256((C / base / 'fashion-bundles.json').read_bytes()).hexdigest()
old['basis'] += '2026-11-04 additions follow their existing series or nearest native-preview registration neighbor; old offer order preserved. No official sale dates inferred.'
for p in scope['added_packages']:
    old.setdefault('series', {})[str(p['template'])] = dict(name=family(p), registration=registration[p['template']],
                                                        registration_scope='native preview/package source, not retail release date')
for relative in [*sources, 'analysis/shop-unlisted-listing-20261104-v1/bundle-membership.json']:
    if not any(row['path'] == relative for row in old['sources']):
        old['sources'].append(dict(path=relative, sha256=hashlib.sha256((C / relative).read_bytes()).hexdigest()))
(C / base / 'bundle-order.json').write_text(json.dumps(old, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
(W / 'order-result.json').write_text(json.dumps(dict(ok=True, old_order_preserved=True, count=len(order), added=len(scope['added_packages']),
                                                   decisions=decisions), ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print('Ordered', len(order), 'bundles; preserved every old offer in its original relative order.')
