"""Pinned supplementary definitions, each accepted by the native private reader."""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data
BASE=PROJECT_ROOT/'analysis/shop-standalone-20261015'

@functools.lru_cache(maxsize=2)
def catalog(name):
    if name not in ('standalone','ice-common'):raise ValueError('Unknown supplement')
    path=BASE/(name+'.json');content=path.read_bytes();c=json.loads(content)
    proof=json.loads((BASE/(name+'-body-proof.json')).read_text(encoding='utf8'))
    if c['client_sha256']!=CLIENT_SHA or proof['catalog_sha256']!=hashlib.sha256(content).hexdigest() or proof.get('all_passed') is not True:raise ValueError('Supplement native proof mismatch')
    for source in c.get('sources',[]):
        if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Supplement native source changed')
    evidence={p['template']:p for p in proof['rows']}
    if proof['count']!=len(evidence) or len(evidence)!=len(c['definitions']):raise ValueError('Supplement proof coverage')
    for row in c['definitions']:
        p=evidence[row['template']];raw=bytes.fromhex(row['record_hex'])
        if (len(raw)!=232 or struct.unpack_from('<I',raw)[0]!=row['template'] or raw!=client_data().item(row['template'])['record']
            or not (p['ok']==1 and p['consumed']==304 and p['fields_match'] and p['vectors_empty']
                    and p['native_template_id']==row['template'] and p['native_group']==row['group']
                    and p['private_data_item']['metadata']==row['metadata'] and p['native_name']==row['name'] and p['applied_to_game'] is False)):
            raise ValueError('Supplement item classification mismatch')
    return c

def offers(unit_type=None):
    from els_server.domain.shop_listing import ice_equipment,NPC_MEDICINES
    return tuple(dict(sku=1200000000+p['template'],**{k:p[k] for k in ('template','name','category','price','quantity')})
                 for p in catalog('standalone')['offers']
                 if (unit_type is None or p['role'] in (0,unit_type))
                 and p['template'] not in ice_equipment() and p['template'] not in NPC_MEDICINES)
