"""Selected learned-force extraction, original6CE/6CF and finite extractor."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import empty_record,record

EXTRACTOR=135866
EXTRACTOR_SHA='e7602a3a4c6167a9c6be2f31fbf19df8042d658ab02dc0a482dee58c84a01346'

def register():
    import hashlib
    from els_server.game_data import client_data
    item=client_data().item(EXTRACTOR)
    if hashlib.sha256(item['record']).hexdigest()!=EXTRACTOR_SHA or (item['metadata'],item['item_type'])!=(2,7):raise ValueError('Original force extractor identity')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
    if EXTRACTOR in meta and (meta[EXTRACTOR],groups[EXTRACTOR],stacks[EXTRACTOR])!=(2,4,999):raise ValueError('Extractor registration conflict')
    # 999 is the existing explicit local stack policy. Registration does not
    # add an event reward or grant the extractor to any account.
    meta[EXTRACTOR]=2;groups[EXTRACTOR]=4;stacks[EXTRACTOR]=999

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=5:raise ValueError('Force extraction request size')
    skill,rank=struct.unpack('>iB',payload)
    from els_server.domain.boosting_2026_force_inventory import catalog
    if (skill,rank) not in {(r['skill'],r['native_rank']) for r in catalog().values()}:raise ValueError('Selected force extraction pair')
    return skill,rank

def acknowledgement(skill=0,rank=0,changes=(),result=0):
    # C55D70 writes i32 ID,u8 rank. 9CF750 reads result,ID,rank,
    # then DD46E0 absolute inventory records, before removing that owned pair.
    return Event(0x201,kind=0x6cf,payload=struct.pack('>iiBI',result,skill,rank,len(changes))+b''.join(empty_record(*p) if i is None else record(i) for p,i in changes))
