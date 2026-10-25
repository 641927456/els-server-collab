"""Native 2F6 feed result and 2F2/3/4 state notifications; 2FD entity refresh."""
import struct
from els_server.protocol.companion_messages import event,pet_record,inventory_delta

def feed(p=None,updates=(),removed=None,result=0):
    p=p or {};personality=p.get('personality',{})
    return event(0x2f6,struct.pack('>ihI',result,p.get('satiety',0),len(personality))+b''.join(struct.pack('>ih',int(k),v) for k,v in sorted(personality.items(),key=lambda x:int(x[0])))+struct.pack('>h',p.get('nutrition',0))+inventory_delta(updates,removed))

def progress(owner,p):return event(0x2f4,struct.pack('>QQhi',owner,p['uid'],p['satiety'],p['growth']))

def refresh(owner,p):return event(0x2fd,struct.pack('>Q',owner)+pet_record(p))
