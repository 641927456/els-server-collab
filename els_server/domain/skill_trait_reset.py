"""Native scroll payment extension; historical trait definitions stay byte-pinned."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.protocol.protocol_codec import Event

@functools.lru_cache(maxsize=1)
def reset_items():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/skill_trait_reset_items.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='05ada82ee94a901062d7173b28cf06f79ea8dd623eb44ddceacd65e95accab38':raise ValueError('Trait reset item definitions changed')
    data=json.loads(raw)
    if data['schema_version']!=1 or data['client_sha256']!=CLIENT_SHA:raise ValueError('Trait reset item build')
    for row in data['items'].values():
        item=client_data().item(row['template']);record=item['record']
        if (hashlib.sha256(record).hexdigest()!=row['record_sha256']
            or item['metadata']!=row['metadata'] or (item['flags8']>>3)&31!=7
            or row['group']!=4 or row['max_stack']!=(int.from_bytes(record[16:20],'little') or 1)):
            raise ValueError('Trait reset original item identity')
    return {r['template']:r for r in data['items'].values()}


def reset_request(payload):
    # C53BE0: original skill, note, optional scroll UID, use-ED boolean.
    if len(payload)!=17:raise ValueError('Skill trait reset size')
    skill,note,item_uid,use_ed=struct.unpack('>iiQB',payload)
    if (skill<=0 or not 1<=note<=22 or use_ed not in (0,1)
        or (item_uid!=0 if use_ed else not 0<item_uid<2**63)):raise ValueError('Unsupported trait reset payment')
    return skill,note,item_uid,bool(use_ed)


def reset_acknowledgement(skill=0,note=0,ed=0,result=0,*,changes=(),use_ed=True):
    # BC32D0: four ints, byte, DD46E0 inventory vector, DAF1D0 UID/bool
    # vector, boolean, ED, then DB3D10's fixed optional record.
    tail=struct.pack('>IBiQQB',0,2,0,0,0,0)
    from els_server.domain.fashion_state import record,empty_record
    delta=struct.pack('>I',len(changes))+b''.join(empty_record(*p) if item is None else record(item) for p,item in changes)
    body=struct.pack('>iiiiB',result,0,skill,note,0)+delta+struct.pack('>IBQ',0,int(result==0 and use_ed),ed)+tail
    return Event(0x201,kind=0x560,payload=body)

