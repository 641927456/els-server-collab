"""DE1310 mount DTO: destruction date, stamina clocks and ridden flags."""
import math,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring

def growth_record(mount=None):
 p=mount or {}
 from els_server.domain.mount_racing_rules import profile
 growth=p.get('racing')
 growth=profile() if growth is None else profile(growth['experience'],growth['stats'])
 stats=sorted(growth['stats'].items())
 return (struct.pack('>QHBiI',p.get('uid',0),p.get('unit',0),growth['level'],growth['experience'],len(stats))
         +b''.join(struct.pack('>ii',key,value)for key,value in stats))

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
         # Nested DB2B20: original7E1DE0 initializes its level byte to1.
         # H is the racing mount type (1822BC0/3497AD0 via UserInfo+2970).
         # It is independent of the level byte and cumulative experience.
         # D81DD0 locates the owned outer record by this nested UID.
         +growth_record(p))

def summoned(result,mount=None):return Event(0x201,kind=0x42d,payload=struct.pack('>i',(2856) if result == -1 else result)+record(mount))
def dismounted(result,uid,mount=None):return Event(0x201,kind=0x430,payload=struct.pack('>iQ',(2856) if result == -1 else result,uid)+record(mount))

def reset_ack(result=0,mount=None,*,updates=(),removed=None):
 from els_server.protocol.companion_messages import inventory_delta
 return Event(0x201,kind=0xa8f,payload=struct.pack('>i',(21) if result == -1 else result)+growth_record(mount)+inventory_delta(updates,removed))
