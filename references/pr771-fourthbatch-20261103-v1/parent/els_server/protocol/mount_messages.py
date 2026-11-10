"""DE1310 mount DTO: destruction date, stamina clocks and ridden flags."""
import math,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring

def record(mount=None):
 p=mount or {};stamina=p.get('stamina',0. if not mount else 120.)
 if type(stamina) not in (int,float) or not math.isfinite(stamina) or not 0<=stamina<=14400:raise ValueError('Invalid mount stamina')
 from els_server.domain.item_expiration import date_string
 # DE1310+0E is m_wstrDestroyDate, not a player-chosen mount name.
 # Current35F3030+50C passes this string to374470 and subtracts server time
 # before formatting the native remaining-day/hour/minute label.
 deadline=date_string(p['expires_at'])if 'expires_at'in p else ''
 # 2E is last-unsummon/list ordering;36 is the stamina clock.
 return (struct.pack('>QHf',p.get('uid',0),p.get('unit',0),stamina)+wstring(deadline)
         +struct.pack('>QQBB',p.get('native_time1',0),p.get('accounted_at',0),bool(p.get('ridden')),bool(p.get('no_stamina')))
         +struct.pack('>QHBiI',0,0,0,0,0))

def summoned(result,mount=None):return Event(0x201,kind=0x42d,payload=struct.pack('>i',result)+record(mount))
def dismounted(result,uid,mount=None):return Event(0x201,kind=0x430,payload=struct.pack('>iQ',result,uid)+record(mount))
