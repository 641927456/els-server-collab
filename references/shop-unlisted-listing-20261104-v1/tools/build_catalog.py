"""Qualify the audited omissions against existing native membership sources."""
import ast
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

W = Path(__file__).resolve().parent
R = W.parents[1]
C = W / 'candidate'
sys.dont_write_bytecode = True
sys.path.insert(0, str(C))
from els_server.game_data import client_data
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS
from els_server.domain.acquisition_policy import has_legacy_marker
from els_server.domain.ordinary_accessories import definitions as ordinary_accessories
from els_server.domain.character_rules import CLASSES
from els_server.domain.equipment_requirements import class_matches
from els_server.storage.characters import BASE_CLASSES


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk(value):
    if isinstance(value, dict):
        if 'CUSTOM_ID' in value:
            yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def numbers(value):
    if type(value) is int:
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from numbers(child)
    elif isinstance(value, list):
        for child in value:
            yield from numbers(child)


def excluded_name(name):
    return has_legacy_marker(name) or any(s in name for s in ('[科宝]', '[路莉尔]', '[阿莉尔]', '[GM]', '测试', '体验'))


class Unqualified(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Unqualified(reason)


D = client_data()
with D.connect() as db:
    items = {r[0]: dict(zip(('template', 'name', 'flags4', 'flags8', 'type', 'metadata', 'position', 'raw'), r))
             for r in db.execute('SELECT id,name,flags4,flags8,item_type,metadata,equip_position,record FROM items')}

audit = read(R / 'analysis/shop-unlisted-check-20261104-v1/remaining-online.json')
bundle_path = C / 'analysis/shop-listing-20261015/fashion-bundles.json'
old = read(bundle_path)
existing = {p['template']: p for p in old['offers']}
definitions = {p['template']: p for p in old['definitions']}
ice = set(read(C / 'analysis/shop-standalone-20261015/ice-shop-exclusions.json')['templates'])
source = 'analysis/shop-missing-20261031-v1/CharCustomData.tables.json'
calls = read(C / source)['__symbolic_calls__']
families = {'MOTION': (1, 1), 'SIT_MOTION': (7, 7), 'SKILL_CUT': (3, 3), 'FACE': (2, 2), 'HYPER_EFFECT': (15, 15)}
by_book = collections.defaultdict(list)
by_custom = {}
gifts = collections.defaultdict(set)
for call in calls:
    kind = next((k for k in families if call['function'].endswith('.CHAR_CUSTOM_' + k + '_DATA')), None)
    for row in walk(call['arguments']):
        if type(row.get('ITEM_ID')) is not int or row['ITEM_ID'] <= 0:
            continue
        for parent in numbers(row.get('PACKAGE_ITEM_ID', {})):
            gifts[parent].add(row['ITEM_ID'])
        if kind is None:
            continue
        row = dict(row, family=families[kind][0], slot=families[kind][1])
        by_book[row['ITEM_ID']].append(row)
        by_custom[row['CUSTOM_ID']] = row
replacements = {c['arguments'][1]: c['arguments'][2:] for c in calls if c['function'].endswith('AddReplaceCustomID')}
preview_groups = collections.defaultdict(list)
for relative in ('20261014-173316/IceHeaterPreView_INT.tables.json',
                 '20261014-062215/ice-resources/IceHeaterPreView.tables.json'):
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for call in read(C / 'analysis/client-6c6b5180' / relative)['__symbolic_calls__']:
        if call['function'].endswith('.AddIceHeaterItemData'):
            _, parent, child, role, appearance = call['arguments']
            grouped[parent][(json.dumps(role, sort_keys=True), appearance)].append(child)
    for parent, groups in grouped.items():
        preview_groups[parent].append(dict(source=relative, groups=[dict(role=json.loads(role), appearance=appearance, children=ids)
                                                                  for (role, appearance), ids in groups.items()]))
permanent_path = C / 'els_server/data/character_custom_permanent.json'
custom = read(permanent_path)
books = {r['book']: r for r in custom['books']}
customs = {r['custom_id']: r for r in custom['customs']}
added_books = []


def variant(row):
    return (2 if row.get('IS_MAJOR', 0) else 3) if row['UNIT_TYPE'] == 10 else 1


def book_rule(t):
    if t in books:
        return books[t], []
    candidates = by_book[t]
    signatures = {(r['CUSTOM_ID'], r['UNIT_TYPE'], variant(r), r['family'], r['slot'],
                   r.get('ALLOW_SOCKET_OPTION_GROUP'), bool(r.get('ACCOUNT_CUSTOM', False))) for r in candidates}
    require(len(signatures) == 1, 'missing or conflicting native custom book link')
    row = candidates[0]
    item = items[t]
    require(item['type'] == 14 and row['UNIT_TYPE'] == item['raw'][210]
            and not row.get('ACCOUNT_CUSTOM', False), 'unsupported custom book ownership/type')
    class_valid = any(D.unit(k)['unitType'] == item['raw'][210] and class_matches(k, item['raw'][211]) for k in CLASSES)
    if not class_valid:
        # The current permanent-book catalog already binds four old type14
        # class bytes through required_class. Keep the two agreeing native
        # unit identities and normalize only a conflicting base-class byte.
        require(item['raw'][211] in BASE_CLASSES.values()
                and D.unit(item['raw'][211])['unitType'] != item['raw'][210],
                'native custom book has impossible role/class restriction')
    cid = row['CUSTOM_ID']
    ids = replacements.get(cid, [cid])
    require(all(i in by_custom for i in ids), 'missing custom replacement source')
    rule = dict(book=t, custom_id=cid, type=row['family'], slot=row['slot'], unit_type=item['raw'][210],
                units=[item['raw'][210]], native_item_sha256=hashlib.sha256(item['raw']).hexdigest(),
                variant=variant(row), ability_group=row.get('ALLOW_SOCKET_OPTION_GROUP'), custom_ids=ids)
    if not class_valid:
        rule['required_class'] = BASE_CLASSES[item['raw'][210]]
    values = []
    for i in ids:
        other = by_custom[i]
        value = dict(custom_id=i, type=other['family'], variant=variant(other), ability_group=other.get('ALLOW_SOCKET_OPTION_GROUP'))
        require(i not in customs or customs[i] == value, 'custom identity conflicts with current catalog')
        values.append(value)
    return rule, values


def native_members(row):
    versions = row['package_sources']
    if versions:
        require(all(all(period == 0 and visible for _, period, visible in v['entries']) for v in versions),
                'nonpermanent or hidden package member')
        distinct = {tuple(dict.fromkeys(child for child, _, _ in v['entries'])) for v in versions}
        require(len(distinct) == 1, 'conflicting regional package membership')
        selected = list(next(iter(distinct)))
        return selected, dict(kind='native permanent package, one of each distinct member under existing local policy',
                              sources=[v['source'] for v in versions],
                              raw_counts=[len(v['entries']) for v in versions])
    versions = preview_groups[row['template']]
    require(bool(versions), 'no deterministic native package/preview membership')
    distinct = {tuple(dict.fromkeys(i for g in v['groups'] for i in g['children'])) for v in versions}
    require(len(distinct) == 1, 'conflicting regional preview membership')
    selected = list(next(iter(distinct)))
    return selected, dict(kind='native preview appearances, one of each distinct member under local complete-set policy',
                          sources=[v['source'] for v in versions], preview_groups=versions)


def definition(t):
    item = items[t]
    group = (27 if item['flags8'] & 256 else 7) if item['flags4'] & 1 else TEMPLATE_BAG_GROUPS.get(t, 4)
    return dict(template=t, name=item['name'], metadata=item['metadata'], group=group,
                max_stack=TEMPLATE_MAX_STACKS.get(t, 1 if item['flags4'] & 1 or item['type'] == 14 else 99),
                resource_position_byte=item['position'], record_hex=item['raw'].hex())


rows = {p['template']: p for p in audit['full_costume_source_candidates']}
rows.update({p['template']: p for p in audit['elstar2_all_unlisted_packages'] if '粉丝' in p['name']})
added = []
held = []
decisions = []
ordinary = ordinary_accessories()
for t, row in sorted(rows.items()):
    try:
        require(t not in existing, 'already listed')
        p = items[t]
        require(p['type'] == 7 and not p['flags4'] & 33 and not excluded_name(p['name']), 'unqualified parent template')
        require(not re.search(r'宝箱|钥匙|隨機|随机|抽奖|挫冰|挫宝|[0-9]+\s*\+\s*[0-9]+', p['name']),
                'box or lottery promotion; fixed costume delivery not qualified')
        selected, basis = native_members(row)
        linked = sorted(gifts[t])
        selected = list(dict.fromkeys([*selected, *linked]))
        require(2 <= len(selected) <= 36 and not set(selected) & ice, 'member bound or true ice reward')
        require(all(i in items for i in selected), 'missing member template')
        children = [items[i] for i in selected]
        require(not any(excluded_name(i['name']) for i in children), 'legacy event or test member')
        require(p['raw'][210] in range(16), 'unknown parent character')
        pending = {}
        for item in children:
            i = item['template']
            require(not item['flags4'] & 32 and item['raw'][210] in range(16), 'PC-bang or unknown member character')
            if item['type'] == 14:
                pending[i] = book_rule(i)
            elif item['type'] in (1, 2, 3) and item['flags4'] & 1:
                require(item['flags4'] & 0xffff0000 == 0x00400000
                        and item['position'] in {2, 6, 8, 9, 10, 11, *range(48, 60)}, 'unsupported cash equipment profile/position')
            else:
                require(item['type'] == 3 and i in ordinary and not ordinary[i]['restricted']
                        and i in VERIFIED_TEMPLATES and TEMPLATE_BAG_GROUPS[i] == 2, 'unsupported nonfashion member')
        costume = any(i['type'] in (1, 2) for i in children)
        by_role = {}
        for role in range(1, 16):
            if p['raw'][210] not in (0, role):
                continue
            ids = [i for i in selected if items[i]['raw'][210] in (0, role)]
            if len(ids) != len(selected):
                continue
            if costume and not {6, 8, 9, 10, 11} <= {items[i]['position'] for i in ids if items[i]['type'] in (1, 2)}:
                continue
            by_role[str(role)] = ids
        require(bool(by_role), 'no complete role-compatible delivery')
        product = dict(template=t, name=p['name'], unit_type=p['raw'][210], kind='costume' if costume else 'accessory',
                       category=52 if costume else 53, price=50, quantity=1, contents=selected, contents_by_role=by_role)
        for i, (rule, values) in pending.items():
            if i not in books:
                custom['books'].append(rule)
                books[i] = rule
                added_books.append(i)
                for value in values:
                    if value['custom_id'] not in customs:
                        custom['customs'].append(value)
                        customs[value['custom_id']] = value
        added.append(product)
        decisions.append(dict(template=t, name=p['name'], basis=basis, contents=selected,
                              explicit_custom_gifts=linked, ordinary_templates=row['ordinary_listed_matches']))
        for i in [t, *selected]:
            if i not in definitions:
                definitions[i] = definition(i)
    except Unqualified as error:
        held.append(dict(template=t, name=row['name'], reason=str(error)))

extended_path = C / 'analysis/client-6c6b5180/extended-shop-catalog.json'
extended = read(extended_path)
extended_ids = {p['template'] for p in extended['offers']}
accessory_positions = {48:22,49:22,50:22,51:23,52:24,53:25,54:26,55:27,56:21,57:23,58:22,59:26}
npc = set(read(C / 'analysis/shop-standalone-20261015/standalone.json')['npc_templates'])
accessories = []
for row in audit['unrepresented_accessories']:
    t = row['template']
    item = items[t]
    require(t not in extended_ids and t not in ice and t not in npc, 'accessory identity/source collision')
    require(item['type'] == 3 and item['flags4'] & 1 and not item['flags4'] & 32
            and item['flags4'] & 0xffff0000 == 0x00400000 and not excluded_name(item['name'])
            and item['position'] in accessory_positions and row['positive_native_price'] > 0, 'accessory source changed')
    product = dict(**definition(t), category=accessory_positions[item['position']], price=50, quantity=1,
                   item_type=3, classification='Human-approved historical positive-price ordinary cash accessory; source not an ice/NPC reward')
    extended['offers'].append(product)
    accessories.append(dict(template=t, name=item['name'], native_price=row['positive_native_price'],
                            category=product['category'], role=item['raw'][210]))

supplement_rel = 'analysis/shop-unlisted-listing-20261104-v1/bundle-membership.json'
supplement = dict(client_sha256=old['client_sha256'], date='2026-11-04',
                  human_instruction='除开普通时装散件，然后把其他的可以上架的进行上架',
                  policy='Existing local permanent complete-set direct delivery and50ED. Native unambiguous package/preview membership plus explicit PACKAGE_ITEM_ID-linked custom gifts. Human separately approved all3-5Track2fan banners, one light and one linked dance per50EDpackage. No random rewards or inferred probabilities; no ordinary fashion single expansion.',
                  custom_source=source, custom_source_sha256=digest(C / source), decisions=decisions)
supplement['custom_class_corrections'] = [dict(book=t, unit_type=books[t]['unit_type'],
                                              native_class_byte=items[t]['raw'][211], required_class=books[t]['required_class'],
                                              basis='Native item UNIT_TYPE and CharCustomData UNIT_TYPE agree; reuse existing per-book old base-class normalization.')
                                        for t in added_books if 'required_class' in books[t]]
save(C / supplement_rel, supplement)
old['offers'].extend(added)
old['definitions'] = [definitions[t] for t in sorted(definitions)]
old['costume_package_templates'] = sorted(set(old['costume_package_templates']) | {p['template'] for p in added if p['kind'] == 'costume'})
old['sources'].append(dict(path=supplement_rel, sha256=digest(C / supplement_rel)))
old['policy'] += '2026-11-04 authorized audited missing complete/fan sets; existing standalone fashion selection unchanged.'
save(bundle_path.with_name('fashion-bundles.candidate.json'), old)
accessory_source = 'analysis/client-6c6b5180/approved-missing-accessories-20261104.json'
save(C / accessory_source, dict(client_sha256=old['client_sha256'], date='2026-11-04',
                               human_instruction=supplement['human_instruction'], offers=accessories,
                               sources=read(C / 'analysis/shop-standalone-20261015/standalone.json')['sources'][:2],
                               policy='Ordinary cash accessories only; retain current50ED pricing and role/equipment restrictions.'))
extended['sources'].append(dict(path=Path(accessory_source).relative_to('analysis/client-6c6b5180').as_posix(), sha256=digest(C / accessory_source)))
save(extended_path, extended)
custom['scope'] += ';2026-11-04 native PACKAGE_ITEM_ID-linked custom gifts for audited missing complete/fan sets.'
save(permanent_path, custom)
domain = C / 'els_server/domain/character_custom.py'
text = domain.read_text(encoding='utf8')
old_hash = re.search(r"hexdigest\(\)!='([a-f0-9]{64})'", text).group(1)
text = text.replace(old_hash, digest(permanent_path))
for name, data in [('COUNTS', custom['customs']), ('SOURCE_COUNTS', custom['books'])]:
    line = next(line for line in text.splitlines() if line.startswith(name + '='))
    keys = ast.literal_eval(line.split('=', 1)[1])
    text = text.replace(line, name + '=' + repr({k:sum(p['type'] == k for p in data) for k in keys}))
domain.write_text(text, encoding='utf8')
scope = dict(added_packages=added, added_accessories=accessories, added_books=added_books,
             custom_class_corrections=supplement['custom_class_corrections'],
             held=held, input_packages=len(rows), new_definition_count=len(definitions) - len(read(bundle_path)['definitions']),
             all_packages=len(old['offers']), price_ED=50, ordinary_fashion_single_expansion=False,
             original_client_delta=0, new_schema=False)
save(W / 'candidate-scope.json', scope)
print(json.dumps(dict(added_packages=len(added), costumes=sum(p['kind']=='costume' for p in added),
                      fan_packages=sum('粉丝' in p['name'] for p in added), accessories=len(accessories),
                      added_books=len(added_books), held=len(held), held_reasons=dict(collections.Counter(p['reason'] for p in held)),
                      new_definitions=scope['new_definition_count']), ensure_ascii=False))
