"""Finite current six-element result pool and original CN quantity price input."""
import functools,hashlib,struct
from els_server.game_data import client_data

# Current KR official probability248; exact current CN six item identities.
# Region difference is retained in the source contract, not a retail CN claim.
OUTCOMES=((130048,17),(130049,16),(130050,17),(130051,17),(130052,16),(130053,17))

@functools.lru_cache(maxsize=1)
def unit_fee():
    row=client_data().item(130054)
    if (hashlib.sha256(row['record']).hexdigest()!='cae171ef8a2bd7f6f1e33d808cebfd4cde3bfe114961b2a0cbac4bd26d50a627'
            or(row['item_type'],row['metadata'])!=(7,2)):
        raise ValueError('Current shard identification fee source')
    amount=struct.unpack_from('<I',row['record'],0x1c)[0]
    if amount!=2000:raise ValueError('Current shard quantity dialog unit price')
    return amount

def outcome(roll):
    if type(roll) is not int or not 0<=roll<100:raise ValueError('Shard identification roll')
    for template,weight in OUTCOMES:
        if roll<weight:return template
        roll-=weight
    raise ValueError('Shard result pool')
