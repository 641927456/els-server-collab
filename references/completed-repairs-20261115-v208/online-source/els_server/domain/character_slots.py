"""Account slot entitlement and native one/two-space coupon definitions."""
import functools,struct
from els_server.game_data import client_data

BASE_CAPACITY=16  # Preserve this server's existing allowance.
MAX_CAPACITY=72   # CN implemented Lithia fourth-path update; native item text.
PRODUCT=206820
SKU=1200000000+PRODUCT
# Existing variants remain usable, without reopening historical producers.
TICKETS={154093:2,165729:2,190050:1,206820:1,206830:2,
         263120:2,297078:1,304894:1,713766:1,60000825:1}

# Cash-shop variants have no original right-click use flag. Keep their stored
# identity, but send the native usable variant with the same slot entitlement.
# The original 219 request identifies the inventory instance by UID only.
_USABLE_VARIANTS={1:190050,2:154093}

@functools.lru_cache(maxsize=256)
def client_identity(template):
    gain=TICKETS.get(template)
    if gain is None:return None
    data=client_data();item=data.item(template)
    if not struct.unpack_from('<I',item['record'],4)[0]&8:
        item=data.item(_USABLE_VARIANTS[gain])
    if (item['item_type']!=7 or not struct.unpack_from('<I',item['record'],4)[0]&8
        or f'角色栏扩张券（{gain}格）' not in item['name']):
        raise ValueError('Character slot native usable variant')
    return item['id'],item['metadata']

class SlotsFull(ValueError):
    result=442  # Native generic expansion failure; do not display old 55-slot text.

def validate_capacity(value):
    if type(value)is not int or not BASE_CAPACITY<=value<=MAX_CAPACITY:
        raise ValueError('Character slot capacity')
    return value

@functools.lru_cache(maxsize=1)
def definitions():
    rows=[]
    for template,gain in TICKETS.items():
        item=client_data().item(template);raw=item['record']
        if item['item_type']!=7 or f'角色栏扩张券（{gain}格）' not in item['name']:
            raise ValueError('Character slot coupon resource mismatch')
        maximum=struct.unpack_from('<I',raw,0x10)[0] or 1
        rows.append(dict(template=template,metadata=item['metadata'],group=4,max_stack=maximum))
    return tuple(rows)

def offers():
    # Owner approved 2026-11-14: 50 ED for one one-space coupon.
    return (dict(sku=SKU,template=PRODUCT,name=client_data().item(PRODUCT)['name'],
                 category=41,price=50,quantity=1),)
