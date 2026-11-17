"""Current guild bank item flags and approved warehouse limits."""
import struct
from els_server.game_data import client_data
from els_server.domain.inventory_items import validate_item
ALLOWED=frozenset(range(400156,400199))
PLAIN=frozenset(('uid','template','metadata','count','group','slot','expires_at','lock_until','sealed','seal_count','seal_used'))

def permissions():
 from els_server.domain.guild_rules import authorities
 return tuple((grade,row[4])for grade,row in sorted(authorities().items()))

def permission_rows(state=None):
 from els_server.domain.guild_rules import initial
 state=initial()if state is None else state
 return tuple((grade,*state['authorities'][str(grade)][:5],state['grade_names'].get(str(grade),''),
     *state['authorities'][str(grade)][5:])for grade in range(1,7))

def permissions_wire(value=None):
 # DCE8A0: grade, invite/manage/skills/funds, withdrawal count, rank name,
 # minimum lifetime honor and maximum item count per withdrawal.
 # Defaults come from GuildData; the latter was added by the2023 bank update.
 value=permission_rows()if value is None else value
 if len(value)!=6 or tuple(r[0]for r in value)!=tuple(range(1,7)):
  raise ValueError('Guild six-rank authority map')
 from els_server.protocol.guild_membership_profile import _string
 return struct.pack('>I',len(value))+b''.join(bytes(row[:6])+_string(row[6])+struct.pack('>ii',*row[7:])for row in value)

def period(now):
 if type(now)is not int or not 0<now<2**63:raise ValueError('Guild bank server clock')
 return (now+2*3600)//86400  # UTC+8 local06:00 boundary.

def require_item(item,*,now,container='inventory'):
 item=validate_item(item,container=container)
 from els_server.domain.bag_capacity import BAG_GROUPS
 if item['group']not in BAG_GROUPS:raise ValueError('Guild bank requires unequipped inventory source')
 if item.get('sealed',False)and(set(item)-PLAIN or item['metadata']not in(0,2)):raise ValueError('Guild bank sealed equipment transition is not qualified')
 if item['template']in(400152,400223):raise ValueError('Guild coins require original524 contribution consumer')
 definition=client_data().item(item['template']);flags=definition['flags4']
 # Actual guild chain2220F10 ->24198E0, not the unrelated2FF8310 trade UI.
 # Bit5 forbids banking; guild allowlist bypasses ordinary binding restriction.
 if flags&32 or flags&2 and not item.get('sealed',False)and item['template']not in ALLOWED:raise ValueError('Original guild bank item flags')
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 require_current(item,now=now);require_unlocked(item,now=now)
 return item
