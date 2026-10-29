"""Pinned permanent pet-support items and native accessory registrations."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data
SHOP_PRODUCTS={500720:'pickup',164566:'automatic',330562:'upgrade'}

def _blocks(offsets):
    out,start,prev=[],None,None
    for o in sorted(offsets):
        if start is None:start=prev=o
        elif o==prev+1:prev=o
        else:out.append([start,prev]);start=prev=o
    if start is not None:out.append([start,prev])
    return out

@functools.lru_cache(maxsize=1)
def variant_definitions():
    evidence=json.loads((PROJECT_ROOT/'els_server/data/pet_ticket_variants.json').read_text(encoding='utf8'))
    if evidence['client_sha256']!=CLIENT_SHA:raise ValueError('Pet ticket variant build identity')
    if sorted(evidence['entitled_templates'])!=sorted(r['template'] for r in evidence['rows']):raise ValueError('Pet ticket variant scope')
    for r in evidence['rows']:
        if SHOP_PRODUCTS.get(r['base'])!=r['product']:raise ValueError('Pet ticket variant product')
        variant=client_data().item(r['template']);raw=bytes(variant['record'])
        base=bytes(client_data().item(r['base'])['record'])
        if (variant['item_type']!=r['item_type'] or variant['item_type']!=7 or raw[7]&15!=r['metadata']
            or (variant['flags8']>>3)&31!=7 or variant['flags4']!=r['flags4'] or variant['flags8']!=r['flags8']
            or hashlib.sha256(raw).hexdigest()!=r['record_sha256']
            or _blocks({o for o,b in enumerate(raw)if b!=base[o]})!=r['identifier_and_text_blocks']):
            raise ValueError('Pet ticket variant native identity')
    return tuple(evidence['rows'])

PRODUCTS=dict((*SHOP_PRODUCTS.items(),*((r['template'],r['product']) for r in variant_definitions())))

@functools.lru_cache(maxsize=1)
def catalog():
    c=json.loads((PROJECT_ROOT/'analysis/pet-support-20261015/catalog.json').read_text(encoding='utf8'))
    if c['client_sha256']!=CLIENT_SHA:raise ValueError('Pet support build identity')
    for s in c['sources']:
        if hashlib.sha256((PROJECT_ROOT/s['path']).read_bytes()).hexdigest()!=s['sha256']:raise ValueError('Pet support source identity')
    for r in c['definitions']:
        if r['native_reader_ok']!=1 or r['consumed']!=304 or hashlib.sha256(client_data().item(r['template'])['record']).hexdigest()!=r['record_sha256']:raise ValueError('Pet item native identity')
    if len(c['equipment'])!=18 or 135972 in c['equipment']:raise ValueError('Pet accessory scope')
    return c

def offers():
    # The ordinary El Tree seed is a native cash feed. The ordinary fruit is
    # already in the main shop catalog; event/bound food variants are not sold.
    # Rebranded tickets use the same entitlement but are not sold separately.
    return tuple(dict(sku=1200000000+t,template=t,name=client_data().item(t)['name'],category=62,price=50,quantity=1) for t in (*SHOP_PRODUCTS,500030))
