"""Native 2F6 feed result and 2F2/3/4 state notifications; 2FD entity refresh."""
import struct
from els_server.protocol.companion_messages import event,pet_record,inventory_delta

def feed(p=None,updates=(),removed=None,result=0):
    p=p or {};personality=p.get('personality',{})
    return event(0x2f6,struct.pack('>ihI',result,p.get('satiety',0),len(personality))+b''.join(struct.pack('>ih',int(k),v) for k,v in sorted(personality.items(),key=lambda x:int(x[0])))+struct.pack('>h',p.get('nutrition',0))+inventory_delta(updates,removed))

def progress(owner,p):return event(0x2f4,struct.pack('>QQhi',owner,p['uid'],p['satiety'],p['growth']))

def refresh(owner,p):return event(0x2fd,struct.pack('>Q',owner)+pet_record(p))

def nutrient(p=None,updates=(),removed=None,result=0):
    # 2DCD260: result, available growth points, digestion deadline, inventory
    # records, and the pet UID, in this exact order. The deadline is a signed
    # 64-bit epoch: reading the native reader at 2DCD260 stores it with an
    # eight-byte load at frame -0x2A, so a 32-bit slot shifts the inventory
    # block by four bytes and the client drops the whole reply.
    p=p or {}
    return event(0x8ae,struct.pack('>ihQ',result,p.get('nutrition',0),p.get('digest_until',0))+inventory_delta(updates,removed)+struct.pack('>Q',p.get('uid',0)))

def digestion(p=None,result=0):
    # 2DCD700 uses the ordinary complete D9C550 pet reader.
    return event(0x8ba,struct.pack('>i',result)+pet_record(p))

def investment(p=None,result=0):
    # 30200C0 reads result, an unused u64, then the complete D9C550 record.
    return event(0x8b0,struct.pack('>iQ',result,0)+pet_record(p))
