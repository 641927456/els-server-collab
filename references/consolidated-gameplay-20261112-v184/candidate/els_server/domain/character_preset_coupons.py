"""Current preset expansion coupon family; owned use, no new sale/drop source."""
from functools import lru_cache
import hashlib,struct

SOURCES={
    313838:'813fc47496816086d7a93dcb58271355cced2d363bd2fa59f55b95992d39561d',
    711731:'941cb40311a112e9f188cc9c74818d7e5b75ad5ee683409b664ad990b6e1b2b4',
    711732:'e30cd55fe9fa851fc34323541b0d0e91df02fe50b6f3b7eac1c7b6917305c8ca',
    711733:'e596bfe64bc08702a21e33982ab66e7387539b2e4f5992da1acb4b4309d6c169',
}


@lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data
    rows=[]
    for template,digest in SOURCES.items():
        item=client_data().item(template);raw=item['record']
        if (hashlib.sha256(raw).hexdigest()!=digest or item['item_type']!=7
            or item['metadata']!=0 or (item['flags8']>>3)&31!=7 or item['flags4']&33):
            raise ValueError('Preset coupon native definition changed')
        stack=struct.unpack_from('<I',raw,0x10)[0]
        rows.append(dict(template=template,metadata=0,group=4,max_stack=max(1,stack)))
    return tuple(rows)
