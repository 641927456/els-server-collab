"""Source-pinned current Raid policy; missing rates explicitly belong to this server."""
import functools,hashlib,json
from pathlib import Path

@functools.lru_cache(maxsize=1)
def policy():
 p=Path(__file__).resolve().parents[1]/'data/formal_raid_economy.json';raw=p.read_bytes();d=json.loads(raw);m=json.loads(p.with_suffix('.manifest.json').read_bytes())
 from els_server.game_data import client_data,CLIENT_SHA
 if (d['schema_version']!=1 or d['policy']!='formal-raid-economy-20261025-v1'
     or d['client_sha256']!=CLIENT_SHA or m['client_sha256']!=CLIENT_SHA
     or d['catalog_sha256']!=client_data().manifest['catalog_sha256'] or hashlib.sha256(raw).hexdigest()!=m['payload_sha256']):raise ValueError('Raid policy identity')
 if len(d['maps'])!=53 or set(d['maps'])&set(d['held_maps']):raise ValueError('Raid finite current modes')
 d['_sha256']=m['payload_sha256'];return d

def definition(identity):return policy()['maps'].get(str(identity))

def check_run(run):
 d=definition(run.identity)
 if d is None:return None
 if run.graph['source_sha256']!=d['graph_sha256'] or str(run.stage)not in d['phases']:raise ValueError('Raid original graph/stage changed')
 return d

def adjust(family):
 mid={'rosso':34150,'berthe':34560,'abyss':34840,'barkat':35560}[family]
 return policy()['native_adjust_drop_table'][str(mid)]

def level(family,points):
 rows=adjust(family)['DropLevel']
 if type(points)is not int or not 0<=points<=max(v['3']for v in rows.values()):raise ValueError('Raid adjust progress bound')
 return max(v['1']for v in rows.values()if points>=v['3'])

def maximum(family):return max(v['3']for v in adjust(family)['DropLevel'].values())

def plan(rows):
 from els_server.domain.reward_rules import item_plan
 merged={}
 for t,n in rows:
  if type(t)is not int or type(n)is not int or n<0:raise ValueError('Raid plan numeric type')
  if n:merged[t]=merged.get(t,0)+n
 return [item_plan(t,n)for t,n in sorted(merged.items())]

@functools.lru_cache(maxsize=2)
def circuits(only_t=False):
 from els_server.domain.equipment_circuit_rules import catalog as circuit_policy
 from els_server.game_data import client_data
 d=circuit_policy();c=client_data();out=tuple(sorted(int(t)for t in d['materials']if not only_t or c.item(int(t))['name'].startswith('T-')))
 if len(out)!=(48 if only_t else 120):raise ValueError('Raid original circuit shape pool')
 return out

def draw(run,owner,stage,label,denominator):
 import uuid
 if type(denominator)is not int or not 1<=denominator<=1000000:raise ValueError('Raid draw denominator')
 return int.from_bytes(hashlib.sha256(uuid.UUID(run).bytes+f':{owner}:{stage}:{label}:formal-raid-v1'.encode()).digest(),'big')%denominator

def pools(d,stage,first,run,owner,points):
 """Finite item candidates; no display-group ID is treated as an item ID."""
 p=policy();local=p['local'];f=d['family'];mode=d['mode'];ordinal=d['ordinal'];last=stage==max(map(int,d['phases']));rows=[]
 def add(t,n=1):rows.append((t,n))
 def choose(label,items):return items[draw(run,owner,stage,label,len(items))]
 def roll(label,bp):return draw(run,owner,stage,label,10000)<bp
 def accessory(t,allowed=True):
  if allowed and roll('accessory',local['weekly_accessory_bp']if first else local['repeat_accessory_bp']):add(t)
 if f in('rosso','berthe','abyss'):
  if first:
   if f=='abyss':
    add(local['abyss_purifier_template'],local['abyss_purifier_quantity'])
    add(choose('abyss-stone',local['abyss_stone_pool']),local['abyss_stone_quantity'])
   else:add(local['weekly_boxes'][f]['story'if mode=='story'else'normal'],local['weekly_box_quantity'])
   if last:
    boxes={'rosso':(30615,30616,30617),'berthe':(136052,136053),'abyss':(136107,136108,136108,None)}[f]
    if boxes[ordinal-1]is not None:accessory(boxes[ordinal-1])
   if f!='abyss'and last and d['final_map']:
    threshold=maximum(f);lv=level(f,points)
    chance=local['weapon_base_bp']+(lv-1)*local['weapon_level_increment_bp']
    if points>=threshold or (f!='abyss'and roll('weapon',chance)):
     add(adjust(f)['DropItem']);points=0
  if f=='abyss':
   if not first and roll('abyss-repeat-purifier',local['abyss_repeat_purifier_bp']):
    add(local['abyss_purifier_template'],local['abyss_purifier_quantity'])
    points=min(maximum(f),points+local['abyss_repeat_purifier_points'])
   if last and d['final_map']and points>=maximum(f):add(adjust(f)['DropItem']);points=0
  # Rosso/Berthe weapons keep weekly eligibility; Abyss uses its native full
  # purification condition, including a later repeat Origin clear.
 elif f=='conductor':
  if first:
   add(118638,local['weekly_chip_quantity'])
   if last:accessory((136172,136173)[ordinal-1])
  elif last:
   add(choose('circuit',circuits(mode=='hard'and ordinal==2)));add(choose('black-gem',local['black_gem_pool']));add(118638)
   if ordinal==2 or mode=='hard':
    if roll('chip-reset',1000):add(local['system_chip_reset_template'])
   if mode=='hard':accessory((136172,136173)[ordinal-1])
 elif f=='barkat':
  if first:
   add(choose('circuit',circuits(True)));add(118638,local['weekly_chip_quantity'])
   if last and ordinal<=3:accessory((136176,136177,136178)[ordinal-1])
   if last and ordinal==5:add(136201)
  elif last:
   add(choose('circuit',circuits(True)));add(118638)
   if mode=='normal':
    if roll('chip-reset',1000):add(local['system_chip_reset_template'])
    if ordinal<=3:accessory((136176,136177,136178)[ordinal-1])
    if ordinal==5:add(136201)
  if last and ordinal==5 and (points>=maximum(f)or roll('weapon',local['weapon_base_bp']+(level(f,points)-1)*local['weapon_level_increment_bp'])):
   add(136180);points=0
 elif f=='marcus'and mode=='normal'and first and last:
  # Canonical current native phase is used where the CN/NA textual phase units
  # conflict; this placement is explicitly a server rule, not an official quote.
  add(119216,p['official']['marcus_black_fragments_per_weekly_reward'])
  choices=list(range(119222,119241))
  add(choose('cartridge',choices))
  if last and ordinal==3:accessory(30875)
  if last and ordinal==5:accessory(30874);add(119215);add(119325)
 return rows,points
