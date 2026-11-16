"""Original C63340 / 30ACBF0 and 30ACFF0 layouts, big-endian integers."""
import struct
from els_server.protocol.companion_messages import event,pet_record,inventory_delta

def use_request(raw):
    if len(raw)!=29:raise ValueError('Pet support use length')
    item,pet,a,b,n,flag=struct.unpack('>QQiiIB',raw)
    if not 0<item<2**63 or not 0<=pet<2**63 or a or b or n or flag:raise ValueError('Unsupported pet support use parameters')
    return item,pet

def settings_request(raw):
    if len(raw)!=22:raise ValueError('Pet automatic settings length')
    pet,hp,mp,enabled,hp_seconds,mp_seconds,cheer,a,b=struct.unpack('>QBBbiiBBB',raw)
    if pet or enabled not in (0,1) or not 1<=hp<=100 or not 1<=mp<=100 or not 0<=cheer<=100 or a>3 or b>3 or not 0<=min(hp_seconds,mp_seconds)<=max(hp_seconds,mp_seconds)<=300:raise ValueError('Invalid pet automatic settings')
    return dict(hp=hp,mp=mp,enabled=enabled,hp_seconds=hp_seconds,mp_seconds=mp_seconds,cheer=cheer,cheer_a=a,cheer_b=b)

def settings(state,kind=0x662):
    # C63340: bool, expiry u64, HP/MP u8, upgraded bool, enabled bool,
    # two timer-seconds i32, cheer threshold and two cheer-mode u8.
    from els_server.domain.item_expiration import MAXIMUM
    expiry=state.get('automatic_expires_at',0)if state['automatic']else 0
    if state['automatic']and not expiry:expiry=MAXIMUM # Native FEC270 recognizes year>=2049 as permanent.
    if type(expiry)is not int or not 0<=expiry<2**40:raise ValueError('Pet automatic native deadline')
    return event(kind,struct.pack('>BQBBBBiiBBB',state['automatic'],expiry,state['hp'],state['mp'],state['upgrade'],state['enabled'],state['hp_seconds'],state['mp_seconds'],state['cheer'],state['cheer_a'],state['cheer_b']))

def pet_update(p=None,result=0):return event(0x2fc,struct.pack('>i',result)+pet_record(p))
def equipment_ack(p=None,updates=(),removed=None,result=0):
    return event(0x8c8,struct.pack('>i',result)+pet_record(p)+inventory_delta(updates,removed))
