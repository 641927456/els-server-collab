"""DE1310 mount DTO: real stamina, timestamps and native ridden flags."""
import math,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring

def record(mount=None):
 p=mount or {};stamina=p.get('stamina',0. if not mount else 120.)
 if type(stamina) not in (int,float) or not math.isfinite(stamina) or not 0<=stamina<=14400:raise ValueError('Invalid mount stamina')
 # 2E retains the legacy opaque time field; 36 is the stamina clock;
 # 3E is native mounted drain flag, 3F is the native no-stamina flag.
 return (struct.pack('>QHf',p.get('uid',0),p.get('unit',0),stamina)+wstring(p.get('name',''))
         +struct.pack('>QQBB',p.get('native_time1',0),p.get('accounted_at',0),bool(p.get('ridden')),bool(p.get('no_stamina')))
         +struct.pack('>QHBiI',0,0,0,0,0))

def summoned(result,mount=None):return Event(0x201,kind=0x42d,payload=struct.pack('>i',result)+record(mount))
def dismounted(result,uid,mount=None):return Event(0x201,kind=0x430,payload=struct.pack('>iQ',result,uid)+record(mount))
