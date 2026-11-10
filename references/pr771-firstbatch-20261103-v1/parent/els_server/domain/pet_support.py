"""Pinned permanent pet-support items and native accessory registrations."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data
PRODUCTS={500720:'pickup',164566:'automatic',330562:'upgrade',300640:'automatic',300643:'pickup',300644:'pickup',500867:'pickup'}

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
    return tuple(dict(sku=1200000000+t,template=t,name=client_data().item(t)['name'],category=62,price=50,quantity=1) for t in (500720,164566,330562,500030))
