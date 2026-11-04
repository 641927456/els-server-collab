"""Original ordinary-item bank guards and human-approved finite guild defaults."""
import struct
from els_server.game_data import client_data
from els_server.domain.inventory_items import validate_item
ALLOWED=frozenset(range(400156,400199))
PLAIN=frozenset(('uid','template','metadata','count','group','slot','expires_at','lock_until','sealed','seal_count','seal_used'))

def permissions():
 # DCE8A0: key byte,4 constructor booleans,constructor byte,name,2 signed ints.
 # Only the two actually produced member grades. No other permission granted.
 return ((1,5),(6,0))

def permissions_wire(value=None):
 value=permissions()if value is None else value
 if value!=permissions():raise ValueError('Unreviewed guild bank grade defaults')
 return struct.pack('>I',len(value))+b''.join(bytes((g,0,0,0,0,0))+struct.pack('>Iii',0,count,0)for g,count in value)

def period(now):
 if type(now)is not int or not 0<now<2**63:raise ValueError('Guild bank server clock')
 return (now+2*3600)//86400  # UTC+8 local06:00 boundary.

def require_plain(item,*,now):
 item=validate_item(item)
 if set(item)-PLAIN or item['metadata']not in(0,2)or item['group']not in(3,4,5,6):raise ValueError('Guild bank attachment-bearing consumer not qualified')
 if item['template']in(400152,400223):raise ValueError('Guild coins require original524 contribution consumer')
 definition=client_data().item(item['template']);flags=definition['flags4']
 # Actual guild chain2220F10 ->24198E0, not the unrelated2FF8310 trade UI.
 # Bit5 forbids banking; guild allowlist bypasses ordinary binding restriction.
 if flags&32 or flags&2 and not item.get('sealed',False)and item['template']not in ALLOWED:raise ValueError('Original guild bank item flags')
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 require_current(item,now=now);require_unlocked(item,now=now)
 if not 1<=item['count']<=20000:raise ValueError('Original guild bank finite single stack')
 return item
