"""One original armor retention alias; no source admission from registration."""
import functools,hashlib,struct
from els_server.game_data import client_data
@functools.lru_cache(maxsize=1)
def definition():
 d=client_data().item(119328);raw=d['record']
 if(d['metadata']!=2 or d['item_type']!=7 or hashlib.sha256(raw).hexdigest()!='74cfdbcc24e20132eea7e1e7fb9bb52ca4ddbfd92dcda8758e6eb762672a22a4'
    or struct.unpack_from('<I',raw,0x10)[0]!=500):raise ValueError('Native armor retention alias definition')
 return dict(template=119328,metadata=2,group=4,max_stack=500)
