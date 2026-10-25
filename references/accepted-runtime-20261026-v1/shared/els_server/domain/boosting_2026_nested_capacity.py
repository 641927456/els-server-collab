"""One explicit nested box and its six original eight-slot voucher effects."""
import hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA
BOX=721788
POLICY='user-approved-cn20260729-nested-capacity-v1'
DEFINITION_SHA256='b64a78d935826ceea8898d29c2dc417520e8a0f46781a89880160fe91e515c30'
_items=None

def register():
    global _items
    raw=(Path(__file__).resolve().parents[1]/'data/boosting2026-nested-capacity.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:raise ValueError('Nested capacity definition identity')
    data=json.loads(raw);client=client_data()
    if data['policy']!=POLICY or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']:
        raise ValueError('Nested capacity fixed client')
    box=client.item(BOX)
    if hashlib.sha256(box['record']).hexdigest()!=data['box']['record_sha256']:raise ValueError('Nested capacity source box')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
    from els_server.domain.activity_2026_stack_policy import effective_stack
    from els_server.domain.bag_capacity import PRODUCT_GROUPS
    rows=data['items']
    if [r['template'] for r in rows]!=list(range(190589,190595)):raise ValueError('Nested capacity exact six templates')
    for i,row in enumerate(rows):
        t=row['template'];item=client.item(t)
        if (item['name']!=row['name'] or item['metadata']!=2 or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or (row['metadata'],row['group'],row['quantity'],row['slots'])!=(2,4,1,8)
            or row['capacity_group']!=(1,2,6,3,5,4)[i] or row['canonical_product']!=200751+i
            or PRODUCT_GROUPS[row['canonical_product']]!=row['capacity_group']):raise ValueError('Nested capacity original item/effect')
        if t in meta and (meta[t],groups[t],stacks[t])!=(2,4,effective_stack(row['max_stack'])):raise ValueError('Nested capacity registration conflict')
    result={r['template']:MappingProxyType(dict(r)) for r in rows}
    if _items is not None and _items!=result:raise ValueError('Cannot replace nested capacity policy')
    for t,row in result.items():meta[t]=2;groups[t]=4;stacks[t]=effective_stack(row['max_stack'])
    _items=MappingProxyType(result)
    from els_server.domain.cubes import catalog
    catalog.cache_clear()

def items():return _items or MappingProxyType({})

def entry():
    return MappingProxyType(dict(template=BOX,selection_count=0,entries=tuple(dict(template=t,quantity=1) for t in items()))) if _items is not None else None
