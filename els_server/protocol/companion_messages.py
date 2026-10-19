"""Wire layouts recovered from D9C550, DE1310 and original RPC producers."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.domain.inventory_items import inventory_payload

def event(kind,payload):return Event(0x201,kind=kind,payload=payload)

def uid_request(payload,*,zero=False):
    if len(payload)!=8:raise ValueError('Invalid companion UID request')
    uid,=struct.unpack('>Q',payload)
    if not (0 if zero else 1)<=uid<2**63:raise ValueError('Invalid companion UID')
    return uid

def create_pet_request(payload):
    if len(payload)<12:raise ValueError('Truncated pet creation')
    uid=uid_request(payload[:8]);n,=struct.unpack_from('>I',payload,8)
    if n>48 or n%2 or len(payload)!=12+n:raise ValueError('Invalid pet name length')
    from els_server.domain.companions import valid_name
    return uid,valid_name(payload[12:].decode('utf-16le'))

def pet_record(p=None):
    p=p or {};uid=p.get('uid',0);unit=p.get('unit',0)
    # D9C550 packed DTO offsets are documented in docs/pet-mounts.md.
    data=struct.pack('>Qi',uid,unit)+wstring(p.get('name',''))
    # D9C550 -> DTO +2C step, +57 satiety, +59 growth, +2D personality
    # allocation map. The map is not a learned-skill list (35E6B40/3018190).
    personality=p.get('personality',{})
    data+=struct.pack('>bhiI',p.get('step',0),p.get('satiety',3840 if uid else 0),p.get('growth',0),len(personality))
    data+=b''.join(struct.pack('>ih',int(k),v) for k,v in sorted(personality.items(),key=lambda x:int(x[0])))
    gear=p.get('equipment',{})
    data+=struct.pack('>QhI',0,p.get('nutrition',0),len(gear))+b''.join(struct.pack('>iii',int(slot),e['template'],e['socket']) for slot,e in sorted(gear.items(),key=lambda v:int(v[0])))
    data+=struct.pack('>hhB',0,0,0)
    data+=wstring('')*3+struct.pack('>BQB',bool(p.get('pickup')),0,0)+wstring('')+b'\0'
    data+=struct.pack('>iBQb',0,0,0,0)
    return data

def mount_record(p=None):
    from els_server.protocol.mount_messages import record
    return record(p)

def initialization(saved):
    # 13E09E0 -> 1387A20, original 2D restore: active pet, its records,
    # two UID vectors, auxiliary map, and the complete riding-pet vector.
    pets=[p for p in saved['companions'] if p['kind']=='pet']
    active=[p for p in pets if p['uid']==saved['pet']]
    mounts=[p for p in saved['companions'] if p['kind']=='mount']
    data=struct.pack('>iQI',0,saved['pet'],len(active))+b''.join(pet_record(p) for p in active)
    data+=struct.pack('>I',len(pets))+b''.join(struct.pack('>Q',p['uid']) for p in pets)
    data+=struct.pack('>III',0,0,len(mounts))+b''.join(mount_record(p) for p in mounts)
    return event(0x2d,data)

def inventory_delta(updates=(),removed=None):
    data=inventory_payload(list(updates))
    if removed is None:return data
    from els_server.domain.inventory_items import item_body,fixture
    body=bytearray(item_body(removed))
    for f in fixture()['fields']:
        if int(f['offset'],0) in (0,5):struct.pack_into('>i',body,f['wire_offset'],0)
    return struct.pack('>I',len(updates)+1)+data[4:]+struct.pack('>QBh',0,removed['group'],removed['slot'])+body+bytes(9)

def activation_ack(kind,result,p=None,delta=None):
    record=pet_record(p) if kind=='pet' else mount_record(p)
    return event(0x2e9 if kind=='pet' else 0x433,struct.pack('>i',result)+record+(delta if delta is not None else struct.pack('>I',0)))

def pet_list(result,pets=(),*,pages=1,page=1):
    return event(0x2eb,struct.pack('>iIII',result,pages,page,len(pets))+b''.join(pet_record(p) for p in pets)+b'\0')

def pet_summon(result,p=None):return event(0x2ed,struct.pack('>i',result)+pet_record(p))
def mount_list(result,mounts=()):return event(0x42b,struct.pack('>iI',result,len(mounts))+b''.join(mount_record(p) for p in mounts))
def mount_summon(result,owner,p=None):return event(0x42d,struct.pack('>i',result)+mount_record(p))
def mount_ride(result,owner,p=None):return event(0x430,struct.pack('>iQ',result,owner)+mount_record(p))
