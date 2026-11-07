"""Current-client stamina and riding skill metadata, with pinned provenance."""
import functools,hashlib,json,math,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA

@functools.lru_cache(maxsize=1)
def catalog():
 result=json.loads((PROJECT_ROOT/'analysis/mount-combat-20261015/rules.json').read_text(encoding='utf8'))
 if result['client_sha256']!=CLIENT_SHA:raise ValueError('Mount build mismatch')
 for row in result['sources']:
  if hashlib.sha256((PROJECT_ROOT/row['path']).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Mount rule evidence changed')
 return result

def template(unit):
 if type(unit) is not int:raise ValueError('Mount unit type')
 try:return catalog()['templates'][str(unit)]
 except KeyError:raise ValueError('Unsupported mount template') from None

def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]

def advance(unit,stamina,seconds,ridden):
 rule=template(unit)
 if type(ridden) is not bool or type(seconds) is not int or seconds<0 or type(stamina) not in (float,int) or not math.isfinite(stamina) or not 0<=stamina<=rule['max_stamina']:raise ValueError('Invalid mount clock/state')
 rules=catalog();value=f32(stamina)
 if ridden:value=f32(value-f32(f32(seconds)/rules['ridden_seconds_per_point']))
 else:value=f32(value+f32(f32(f32(seconds)/rules['recovery_seconds_per_point'])*rule['recovery_rate']))
 return max(0.,min(float(rule['max_stamina']),value))
