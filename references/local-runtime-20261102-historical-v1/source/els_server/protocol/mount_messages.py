"""DE1310 mount DTO: real stamina, timestamps and native ridden flags."""
import math,os,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring

# 尾部 19 字节语义未知，实验期由环境变量选择 level 落在 H(2B) 还是 Q(8B) 槽。
LEVEL_SLOT='q' if os.environ.get('ELS_MOUNT_LEVEL_SLOT','h')=='q' else 'h'

def tail_fields(mount):
 p=mount or {};level=p.get('level') or 0;exp=p.get('exp') or 0
 if type(level) is not int or type(exp) is not int or level<0 or exp<0:raise ValueError('Invalid mount level')
 if (p.get('slot') or LEVEL_SLOT)=='q':
  if level>0xffffffffffffffff:raise ValueError('Mount level exceeds Q slot')
  return struct.pack('>QHBiI',level,0,0,0,0)
 if level>0xffff:raise ValueError('Mount level exceeds H slot')
 return struct.pack('>QHBiI',exp,level,0,0,0)

def record(mount=None):
 p=mount or {};stamina=p.get('stamina',0. if not mount else 120.)
 if type(stamina) not in (int,float) or not math.isfinite(stamina) or not 0<=stamina<=14400:raise ValueError('Invalid mount stamina')
 # 2E retains the legacy opaque time field; 36 is the stamina clock;
 # 3E is native mounted drain flag, 3F is the native no-stamina flag.
 return (struct.pack('>QHf',p.get('uid',0),p.get('unit',0),stamina)+wstring(p.get('name',''))
         +struct.pack('>QQBB',p.get('native_time1',0),p.get('accounted_at',0),bool(p.get('ridden')),bool(p.get('no_stamina')))
         +tail_fields(p))

def summoned(result,mount=None):return Event(0x201,kind=0x42d,payload=struct.pack('>i',result)+record(mount))
def dismounted(result,uid,mount=None):return Event(0x201,kind=0x430,payload=struct.pack('>iQ',result,uid)+record(mount))
