"""Original account/30-day assist, composed with the separately approved 10x."""
from functools import lru_cache
import hashlib

TEMPLATE=720773
SKU=1200000000+TEMPLATE
PRICE=50  # Existing local ED shop unit-price policy; not a retail cash price.
DURATION=30*86400

@lru_cache(maxsize=1)
def offer():
    from els_server.game_data import client_data
    item=client_data().item(TEMPLATE)
    if hashlib.sha256(item['record']).hexdigest()!=ITEM_SHA:raise ValueError('Resonance assist template changed')
    return dict(sku=SKU,template=TEMPLATE,name=item['name'],category=41,price=PRICE,quantity=1)

def level_multiplier(level):
    # Explicit CN product terms: below350=300%, below500=200%.
    if type(level)is not int or not 0<=level<=999:raise ValueError('Assist resonance level')
    return 3 if level<350 else 2 if level<500 else 1

ITEM_SHA='8122ed3a45600ad2ac46499606ed829d135abd194b4971265875b10030a82d15'
