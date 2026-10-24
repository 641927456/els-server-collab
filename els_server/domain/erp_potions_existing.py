"""Current modern and retained single-use ERP potions; owned SQL instances only."""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType

LEGACY_TEMPLATES=tuple(range(135938,135949))
MODERN_TEMPLATES=tuple(range(136161,136172))
TEMPLATES=LEGACY_TEMPLATES+MODERN_TEMPLATES
# Owner-requested local shop pack: this retained potion is sold and stacked
# locally. The use transaction already decrements partial counts.
LOCAL_STACKABLE=frozenset((135948,))
PAYLOAD_SHA='968b5d177163acf36f064348d345f9bbb5d4cc87b9a9c5de461f9b2d22e8ac5b'

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import CLIENT_SHA,client_data
    raw=(Path(__file__).resolve().parents[1]/'data/erp_potions_existing.json').read_bytes()
    data=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA or data['client_sha256']!=CLIENT_SHA
        or data['schema_version']!=1 or not data['existing_owned_only'] or data['new_acquisition_providers']
        or tuple(r['template']for r in data['rows'])!=TEMPLATES):
        raise ValueError('ERP potion current source binding')
    result={}
    for row in data['rows']:
        item=client_data().item(row['template']);record=item['record']
        if (hashlib.sha256(record).hexdigest()!=row['record_sha256'] or record.hex()!=row['record_hex']
            or (item['metadata'],item['item_type'],row['metadata'],row['group'])!=((0,7,0,4)if row['template']in LEGACY_TEMPLATES else(2,7,2,4))
            or struct.unpack_from('<II',record,4)[1]!=56
            or (row['min_level'],row['max_level'])!=(1,0)
            or type(row['experience'])is not int or row['experience']<=0):
            raise ValueError('ERP potion current tuple/record')
        result[row['template']]=MappingProxyType(row)
    return MappingProxyType(result)

def request(payload):
    # Original219: modern quantity callback flag1; retained nonstack item uses flag0 and secondary0.
    if type(payload)is not bytes or len(payload)!=29:raise ValueError('ERP potion use length')
    uid,quantity,a,b,n,flag=struct.unpack('>QQiiIB',payload)
    if not 0<uid<2**63 or a or b or n or flag not in(0,1):
        raise ValueError('ERP potion native use parameters')
    if flag==0:
        if quantity:raise ValueError('ERP single use has no secondary UID')
        return uid,1
    if not 1<=quantity<2**31:raise ValueError('ERP potion native quantity parameters')
    return uid,quantity

class _ExistingPotion(dict):
    __slots__=('_original',)

def read_existing(item):
    keys={'uid','template','metadata','count','group','slot'}
    if (type(item)is not dict or set(item)-{'expires_at','lock_until','sealed','seal_used'}!=keys
        or any(type(item[k])is not int for k in keys)
        or not 0<item['uid']<2**63 or item['template']not in TEMPLATES
        or (item['metadata'],item['group'])!=((0,4)if item['template']in LEGACY_TEMPLATES else(2,4))
        or not 1<=item['count']<2**31
        or (item['template']in LEGACY_TEMPLATES and item['template']not in LOCAL_STACKABLE
            and item['count']!=1)):
        raise ValueError('Existing ERP potion instance shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0<=item['slot']<wire_limit(4):raise ValueError('Existing ERP potion slot')
    definitions()
    value=dict(item)
    if 'expires_at'in value:
        from els_server.domain.item_expiration import validate
        value['expires_at']=validate(value['expires_at'])
    if 'lock_until'in value:
        from els_server.domain.item_locks import validate
        value['lock_until']=validate(value['lock_until'])
    if 'sealed'in value or 'seal_used'in value:
        from els_server.storage.item_seals import validate
        validate(value.get('sealed',False),value.get('seal_used',0))
    result=_ExistingPotion(value);result._original=dict(result)
    return result

def validate_existing(item):
    if type(item)is not _ExistingPotion or dict(item)!=item._original:
        raise ValueError('ERP potion requires unchanged owned SQL reader')
    read_existing(dict(item))
    return item
