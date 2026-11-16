"""The ten current GuildData seed material records, ordinary inventory shape."""
from functools import lru_cache
import struct

@lru_cache(maxsize=1)
def definitions():
    from els_server.domain.guild_rules import plants
    from els_server.game_data import client_data
    from els_server.domain.activity_2026_stack_policy import effective_stack
    result=[]
    for plant in plants().values():
        template=plant['SEED_ITEM_ID'];source=client_data().item(template)
        if(source['item_type'],source['metadata'],source['flags8'])!=(6,2,48):raise ValueError('Current guild seed material shape')
        cap=struct.unpack_from('<I',source['record'],16)[0]
        result.append(dict(template=template,metadata=2,group=3,max_stack=effective_stack(cap)))
    return tuple(result)
