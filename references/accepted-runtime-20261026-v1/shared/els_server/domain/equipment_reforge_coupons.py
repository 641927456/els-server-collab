"""Current-client ED exemption coupons, owned selection and finite admission.

Family0 is universal; other values require the actual armor family. Only the
three current-channel-qualified templates are newly admitted. Choosing lowest
owned UID follows the existing local material allocator, not an official
priority claim. Native500 cap is retained; color999 is not generalized.
"""
from pathlib import Path
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='98e3e3b51796fa0aebe59849b27d0d6b82607d03ceef0909e4d49ed83fac8d03'
@functools.lru_cache(maxsize=1)
def policy():
    raw=(Path(__file__).resolve().parents[1]/'data/equipment_reforge_coupons.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Reforge coupon policy identity')
    c=json.loads(raw);data=client_data()
    if c['schema_version']!=1 or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=data.manifest['catalog_sha256'] or c['resource_sha256']!='cd622db6fe266e6a28323c1eb0e16a565def39f7008c1e21858684b7548f4738':raise ValueError('Reforge coupon source identity')
    if c['admitted']!=[714126,714127,720034] or c['quantity_per_attempt']!=1:raise ValueError('Reforge coupon finite admission')
    for t in c['admitted']:
        row=c['registered'][str(t)];d=data.item(t)
        if d['item_type']!=7 or d['metadata']!=2 or row['metadata']!=2 or row['group']!=4 or row['max_stack']!=500 or row['family'] not in (0,2) or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']:raise ValueError('Reforge coupon native record')
    return c
def definitions():return [policy()['registered'][str(t)] for t in policy()['admitted']]
def allocate(items,family,*,now):
    if type(family) is not int or family not in (1,2,3,4):raise ValueError('Reforge coupon armor family')
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    valid={x['template']:x for x in definitions()}
    for item in sorted(items,key=lambda x:x['uid']):
        row=valid.get(item['template'])
        if row is None or row['family'] not in (0,family):continue
        if (item['group'],item['metadata'])!=(row['group'],row['metadata']) or item['count']<1 or item.get('sealed'):continue
        try:require_current(item,now=now);require_unlocked(item,now=now)
        except ValueError:continue
        return {item['template']:1},[dict(uid=item['uid'],quantity=1)]
    raise ValueError('No current owned eligible reforge ED coupon')
