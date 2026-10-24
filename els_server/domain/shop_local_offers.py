"""Owner-requested local ED packs and GM shop additions.

Only price, pack size and exposure are local policy. Every item record still has
to be a verified inventory template of the pinned client build; the built-in
resonance pack additionally has to match the reviewed 2026 catalogue.
"""
import functools
import hashlib
import json
import os
import threading
from pathlib import Path

from els_server.game_data import client_data
from els_server.paths import PROJECT_ROOT

CATALOG_SHA256 = '6160498a1c277d9b3d0819edbbce816991f4a7268acd7fc5069f1772060279a9'
TEMPLATE = 135948
NAME = '艾尔共鸣药水（100倍浓缩）'
CATEGORY = 41
PRICE = 1
QUANTITY = 1000
SKU = 1600135948
MAX_PRICE = 1_000_000_000
MAX_QUANTITY = 1000
DEFAULT_CATEGORY = 41

_state = dict(path=None, stamp=None, offers=())
_lock = threading.RLock()


def configure(path):
    path = Path(path) if path is not None else None
    with _lock:
        if _state['path'] == path:
            return
        _state.update(path=path, stamp=None, offers=())


def path():
    return _state['path'] or (PROJECT_ROOT/'state/local-shop-offers.json')


@functools.lru_cache(maxsize=1)
def definition():
    path = PROJECT_ROOT/'els_server/data/selected2026/rewards.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError('Reviewed local reward catalogue changed')
    data = json.loads(raw)
    row = next((t for t in data['templates'] if t['template'] == TEMPLATE), None)
    if row is None or row['name'] != NAME:
        raise ValueError('Local shop pack item definition missing')
    item = client_data().item(TEMPLATE)
    if (item['name'] != NAME or item['item_type'] != 7
            or hashlib.sha256(item['record']).hexdigest() != row['record_sha256']):
        raise ValueError('Local shop pack item definition changed')
    return row


def register_inventory():
    from els_server.domain.activity_2026_stack_policy import effective_stack
    from els_server.domain.inventory_items import (TEMPLATE_BAG_GROUPS,
                                                   TEMPLATE_MAX_STACKS,
                                                   VERIFIED_TEMPLATES)
    row = definition()
    expected = (row['metadata'], row['group'])
    if TEMPLATE in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[TEMPLATE],
                                           TEMPLATE_BAG_GROUPS[TEMPLATE]) != expected:
        raise ValueError('Conflicting local shop pack classification')
    VERIFIED_TEMPLATES[TEMPLATE] = row['metadata']
    TEMPLATE_BAG_GROUPS[TEMPLATE] = row['group']
    TEMPLATE_MAX_STACKS[TEMPLATE] = effective_stack(row['max_stack'])


def _static_offer():
    register_inventory()
    return dict(sku=SKU, template=TEMPLATE, name=NAME, category=CATEGORY,
                price=PRICE, quantity=QUANTITY)


def _validate_rows(rows):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES
    result = []
    templates, skus = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('商城附加条目格式无效')
        template = row.get('template')
        price = row.get('price')
        quantity = row.get('quantity')
        category = row.get('category', DEFAULT_CATEGORY)
        sku = row.get('sku')
        if any(type(v) is not int for v in (template, price, quantity, category, sku)):
            raise ValueError('商城附加条目字段无效')
        if not 0 <= price <= MAX_PRICE or not 1 <= quantity <= MAX_QUANTITY:
            raise ValueError('商城附加价格或数量超出范围')
        if not 1 <= category <= 255 or not 0 < sku < 2**31:
            raise ValueError('商城附加分类或编号超出范围')
        if template not in VERIFIED_TEMPLATES:
            raise ValueError('该道具尚未在当前服务端验证，不能上架')
        if template in templates or sku in skus:
            raise ValueError('商城附加道具重复')
        templates.add(template)
        skus.add(sku)
        result.append(dict(sku=sku, template=template, name=client_data().item(template)['name'],
                           category=category, price=price, quantity=quantity))
    return tuple(result)


def custom_offers():
    target = path()
    try:
        stamp = (target.stat().st_mtime_ns, target.stat().st_size)
    except FileNotFoundError:
        with _lock:
            _state.update(stamp=None, offers=())
        return ()
    with _lock:
        if _state['stamp'] == stamp:
            return _state['offers']
    document = _read_document()
    offers = _validate_rows(document['offers'])
    with _lock:
        _state.update(stamp=stamp, offers=offers)
    return offers


def offers():
    return (_static_offer(),)+custom_offers()


def bulk_packs():
    return {o['template']: o['quantity'] for o in offers() if o['quantity'] > 1}


def _read_document():
    target = path()
    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        return dict(schema_version=1, offers=[])
    document = json.loads(raw.decode('utf8'))
    if (not isinstance(document, dict) or document.get('schema_version') != 1
            or not isinstance(document.get('offers'), list)):
        raise ValueError('商城附加目录格式无效')
    return document


def _write_document(document):
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)+'\n'
    temporary = target.with_name(target.name+'.tmp')
    with temporary.open('w', encoding='utf8') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if target.exists():
        target.with_name(target.name+'.bak').write_bytes(target.read_bytes())
    os.replace(temporary, target)
    with _lock:
        _state.update(stamp=None, offers=())


def add(state_file, template, price, quantity, category, reason, operation_id):
    configure(Path(state_file).parent/'local-shop-offers.json')
    with _lock:
        document = _read_document()
        rows = list(document['offers'])
        existing = next((r for r in rows if r.get('template') == template), None)
        if existing is not None:
            if existing.get('operation_id') == operation_id:
                return dict(_validate_rows([existing])[0], reason=existing.get('reason'),
                            operation_id=operation_id)
            raise ValueError('该道具已在商城附加目录中')
        row = dict(template=template, price=price, quantity=quantity,
                   category=category, sku=_next_sku(rows), reason=reason,
                   operation_id=operation_id)
        entry = _validate_rows(rows+[row])[-1]
        stored = dict(row, name=entry['name'])
        document['offers'] = rows+[stored]
        _write_document(document)
        return dict(entry, reason=reason, operation_id=operation_id)


def remove(state_file, template, reason, operation_id):
    configure(Path(state_file).parent/'local-shop-offers.json')
    with _lock:
        document = _read_document()
        rows = list(document['offers'])
        kept = [r for r in rows if r.get('template') != template]
        if len(kept) == len(rows):
            raise ValueError('该道具不在商城附加目录中')
        document['offers'] = kept
        _write_document(document)
        return dict(template=template, reason=reason, operation_id=operation_id)


def _next_sku(rows):
    used = {r.get('sku') for r in rows if type(r.get('sku')) is int}
    candidate = 1700000001
    while candidate in used:
        candidate += 1
    if candidate >= 2**31:
        raise ValueError('商城附加编号已用尽')
    return candidate
