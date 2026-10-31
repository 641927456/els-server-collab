"""Build local complete costume bundles from pinned native package previews.

The preview specifies membership, not retail fulfilment. This profile explicitly
sells the complete, permanent set directly to the bag at a local 50 ED price.
"""
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from els_server.game_data import CLIENT_SHA, client_data
from els_server.domain.acquisition_policy import has_legacy_marker
from els_server.domain.shop_listing import ordinary_cash_equipment

BASE = ROOT / 'analysis/client-6c6b5180'
OUT = ROOT / 'analysis/shop-listing-20261015'
PACKAGES = ('20261014-210735/catalog-resources/PackageItemData_INT.tables.json',
            '20261014-212251/catalog-resources/PackageItemData.tables.json')
ICE = ('20261014-173316/IceHeaterPreView_INT.tables.json',
       '20261014-062215/ice-resources/IceHeaterPreView.tables.json')
POSITIONS = {2, 6, 8, 9, 10, 11, *range(48, 60)}


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def build():
    data = client_data()
    with data.connect() as db:
        items = {r[0]: dict(zip(('template', 'name', 'flags4', 'flags8', 'item_type',
                                 'resource_position_byte', 'metadata', 'record'), r))
                 for r in db.execute('SELECT id,name,flags4,flags8,item_type,equip_position,metadata,record FROM items')}
    ice = {r['arguments'][2] for name in ICE
           for r in read(BASE / name)['__symbolic_calls__']
           if r['function'].endswith('.AddIceHeaterItemData') and not ordinary_cash_equipment(items.get(r['arguments'][2], {}).get('flags4', 0))}
    variants = collections.defaultdict(list)
    for name in PACKAGES:
        entries = collections.defaultdict(list)
        for call in read(BASE / name)['__symbolic_calls__']:
            if not call['function'].endswith('.AddPackageItemData'):
                continue
            _, parent, child, period, visible = call['arguments']
            entries[parent].append((child, period, visible in (True, {'global': 'True'})))
        for parent, children in entries.items():
            variants[parent].append(tuple(children))
    supplement_path = ROOT / 'analysis/shop-missing-20261031-v1/package-membership-supplement.json'
    supplement = read(supplement_path)
    native_previews = read(ROOT / supplement['source'])['__symbolic_calls__']
    for row in supplement['packages']:
        assert row['template'] not in variants
        available = {c['arguments'][2] for c in native_previews if c['function'].endswith('.AddIceHeaterItemData') and c['arguments'][1] == row['preview']}
        assert set(row['contents']) <= available
        assert len(row['contents']) == 6 and {items[t]['resource_position_byte'] for t in row['contents']} == {2, 6, 8, 9, 10, 11}
        variants[row['template']].append(tuple((t, 0, True) for t in row['contents']))
    costume_packages = sorted(t for t, versions in variants.items()
                              if any(items.get(child, {}).get('flags4', 0) & 1
                                     for v in versions for child, _, _ in v))
    rejected = collections.Counter()
    offers, needed = [], set()
    for template, versions in sorted(variants.items()):
        p = items.get(template)
        if not p or p['item_type'] != 7 or p['flags4'] & 33:
            rejected['package template unavailable'] += 1
            continue
        if any(v != versions[0] for v in versions[1:]):
            rejected['conflicting native membership'] += 1
            continue
        entries = versions[0]
        ids = [r[0] for r in entries]
        if len(set(ids)) != len(ids) or not 2 <= len(ids) <= 180 or any(period != 0 or not show for _, period, show in entries):
            rejected['ambiguous or nonpermanent membership'] += 1
            continue
        children = [items.get(t) for t in ids]
        if any(r is None for r in children):
            rejected['missing child template'] += 1
            continue
        if any(t in ice for t in ids):
            rejected['ice reward membership'] += 1
            continue
        if any(not r['flags4'] & 1 or r['flags4'] & 32 or r['item_type'] not in (1, 2, 3)
               or r['resource_position_byte'] not in POSITIONS for r in children):
            rejected['not a pure supported costume set'] += 1
            continue
        roles = {r['record'][210] for r in children}
        accessory = all(r['item_type'] == 3 for r in children)
        if accessory:
            role = p['record'][210]
            if role not in range(16) or not roles <= set(range(16)):
                rejected['unknown accessory character'] += 1
                continue
            by_role = {str(n): [r['template'] for r in children if r['record'][210] in (0, n)]
                       for n in range(1, 16) if role in (0, n)}
            by_role = {n: ts for n, ts in by_role.items() if 2 <= len(ts) <= 12}
            if not by_role:
                rejected['incomplete accessory set'] += 1
                continue
        else:
            if len(roles) != 1 or not roles <= set(range(1, 16)):
                rejected['mixed or generic character membership'] += 1
                continue
            role = next(iter(roles))
            if p['record'][210] != role:
                rejected['package and contents character mismatch'] += 1
                continue
            if not 5 <= len(ids) <= 12 or not {6, 8, 9, 10, 11} <= {r['resource_position_byte'] for r in children}:
                rejected['incomplete costume set'] += 1
                continue
            by_role = {str(role): ids}
        names = [p['name']] + [r['name'] for r in children]
        if any(has_legacy_marker(n) or any(s in n for s in ('[科宝]', '[路莉尔]', '[阿莉尔]', '[GM]', '测试', '体验')) for n in names):
            rejected['legacy free event or test item'] += 1
            continue
        offers.append(dict(template=template, name=p['name'], unit_type=role,
                           kind='accessory' if accessory else 'costume', contents_by_role=by_role,
                           category=53 if accessory else 52, price=50, quantity=1, contents=ids))
        needed.update([template, *ids])
    definitions = []
    for template in sorted(needed):
        r = items[template]
        definitions.append(dict(template=template, name=r['name'], metadata=r['metadata'],
                                group=(27 if r['flags8'] & 256 else 7) if r['flags4'] & 1 else 4,
                                max_stack=1 if r['flags4'] & 1 else 99,
                                resource_position_byte=r['resource_position_byte'], record_hex=r['record'].hex()))
    sources = [dict(path=str((BASE / name).relative_to(ROOT)), sha256=hashlib.sha256((BASE / name).read_bytes()).hexdigest())
               for name in (*PACKAGES, *ICE)]
    sources.append(dict(path=str(supplement_path.relative_to(ROOT)), sha256=hashlib.sha256(supplement_path.read_bytes()).hexdigest()))
    sources.append(dict(path='els_server/data/client/catalog.sqlite3', sha256=data.manifest['catalog_sha256']))
    result = dict(client_sha256=CLIENT_SHA, sources=sources, offers=offers, definitions=definitions,
                  costume_package_templates=costume_packages,
                  policy='Local permanent complete-set direct delivery, one of each native preview member, 50 ED per bundle. Not recovered retail fulfilment, availability or prices.',
                  rejected=dict(rejected))
    OUT.mkdir(exist_ok=True)
    (OUT / 'fashion-bundles.candidate.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(bundles=len(offers), definitions=len(definitions), roles=dict(collections.Counter(r['unit_type'] for r in offers)), rejected=dict(rejected)), ensure_ascii=False))


if __name__ == '__main__':
    build()
