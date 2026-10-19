"""Verified native costume package membership and explicit local set delivery."""
import functools
import hashlib
import json
import struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA

BASE = PROJECT_ROOT / 'analysis/shop-listing-20261015'


@functools.lru_cache(maxsize=1)
def catalog():
    path = BASE / 'fashion-bundles.json'
    data = path.read_bytes()
    c = json.loads(data)
    proof = json.loads((BASE / 'fashion-bundles-body-proof.json').read_text(encoding='utf8'))
    if c['client_sha256'] != CLIENT_SHA or proof['client_sha256'] != CLIENT_SHA:
        raise ValueError('Fashion bundle client identity')
    if proof['catalog_sha256'] != hashlib.sha256(data).hexdigest() or proof['all_passed'] is not True:
        raise ValueError('Fashion bundle catalog proof')
    for s in c['sources']:
        if hashlib.sha256((PROJECT_ROOT / s['path']).read_bytes()).hexdigest() != s['sha256']:
            raise ValueError('Fashion bundle source changed')
    evidence = {r['template']: r for r in proof['rows']}
    definitions = {r['template']: r for r in c['definitions']}
    if len(evidence) != len(proof['rows']) or set(evidence) != set(definitions) or proof['count'] != len(definitions):
        raise ValueError('Fashion bundle evidence coverage')
    for template, row in definitions.items():
        raw = bytes.fromhex(row['record_hex'])
        p = evidence[template]
        if len(raw) != 232 or struct.unpack_from('<I', raw)[0] != template or raw[7] & 15 != row['metadata']:
            raise ValueError('Fashion bundle native record')
        if not (p['ok'] == 1 and p['consumed'] == 304 and p['fields_match'] and p['vectors_empty']
                and p['native_template_id'] == template and p['native_group'] == row['group']
                and p['private_data_item']['metadata'] == row['metadata']
                and p['applied_to_game'] is False and p['no_reward_persistence'] is True):
            raise ValueError('Fashion bundle native body')
    if len({p['template'] for p in c['offers']}) != len(c['offers']):
        raise ValueError('Duplicate fashion bundle')
    for p in c['offers']:
        if not 0 <= p['unit_type'] <= 15 or p['category'] != (53 if p['kind'] == 'accessory' else 52) or p['price'] != 50 or p['quantity'] != 1:
            raise ValueError('Fashion bundle offer policy')
        children = [definitions[t] for t in p['contents']]
        if len(set(p['contents'])) != len(children) or not 2 <= len(children) <= 180:
            raise ValueError('Fashion bundle membership bound')
        if any(r['group'] not in (7, 27) for r in children):
            raise ValueError('Fashion bundle character membership')
        for role, ids in p['contents_by_role'].items():
            if int(role) not in range(1, 16) or p['unit_type'] not in (0, int(role)) or not 2 <= len(ids) <= 12:
                raise ValueError('Bundle role coverage')
            selected = [definitions[t] for t in ids]
            if not set(ids) <= set(p['contents']) or any(bytes.fromhex(r['record_hex'])[210] not in (0, int(role)) for r in selected):
                raise ValueError('Bundle role contents')
            if p['kind'] == 'costume' and not {6, 8, 9, 10, 11} <= {r['resource_position_byte'] for r in selected}:
                raise ValueError('Incomplete fashion bundle')
    return c


@functools.lru_cache(maxsize=1)
def by_template():
    return {p['template']: p for p in catalog()['offers']}


@functools.lru_cache(maxsize=1)
def replaced_templates():
    return frozenset(catalog()['costume_package_templates'])


@functools.lru_cache(maxsize=1)
def display_order():
    c=json.loads((BASE/'bundle-order.json').read_text(encoding='utf8'))
    if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=hashlib.sha256((BASE/'fashion-bundles.json').read_bytes()).hexdigest():
        raise ValueError('Bundle order catalog identity')
    ids=c['templates']
    if len(ids)!=len(set(ids)) or set(ids)!=set(by_template()):
        raise ValueError('Bundle order coverage')
    for s in c['sources']:
        if hashlib.sha256((PROJECT_ROOT/s['path']).read_bytes()).hexdigest()!=s['sha256']:
            raise ValueError('Bundle order source changed')
    return tuple(ids)


def offers(unit_type=None):
    from els_server.domain.acquisition_policy import can_acquire
    products=by_template()
    return tuple(dict(sku=1200000000 + p['template'], **{k: p[k] for k in ('template', 'name', 'category', 'price', 'quantity')})
                 for p in (products[t] for t in display_order()) if (unit_type is None or str(unit_type) in p['contents_by_role'])
                 and all(can_acquire(t) for t in p['contents']))


def delivery(template, quantity, unit_type):
    """Expand one locally sold set; grant_items owns allocation and rollback."""
    p = by_template().get(template)
    if p is None:
        return None
    ids = p['contents_by_role'].get(str(unit_type))
    if ids is None:
        raise ValueError('Bundle is not available for this character')
    return [(t, quantity) for t in ids]
