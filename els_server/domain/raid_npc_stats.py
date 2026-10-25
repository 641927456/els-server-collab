"""Source-bound native base ATK/DEF inputs; original client calculates combat."""
from pathlib import Path
import functools,hashlib,json,math,struct

@functools.lru_cache(maxsize=1)
def policy():
 from els_server.game_data import CLIENT_SHA
 p=Path(__file__).resolve().parents[1]/'data/raid_npc_stats.json';raw=p.read_bytes();d=json.loads(raw);m=json.loads(p.with_suffix('.manifest.json').read_bytes())
 if (m['schema_version']!=1 or d['schema_version']!=1 or d['client_sha256']!=CLIENT_SHA or m['client_sha256']!=CLIENT_SHA
     or m['payload_sha256']!=hashlib.sha256(raw).hexdigest()or d['offsets']!=[8,12,16,20]
     or d['fields']!=['PHYSIC_ATT_VALUE','MAGIC_ATT_VALUE','PHYSIC_DEF_VALUE','MAGIC_DEF_VALUE']):raise ValueError('NPC native stat policy identity')
 return d

def apply(catalog,template,attrs,context):
 if context is None:return False
 if not isinstance(context,tuple)or len(context)!=7:raise ValueError('NPC stat original source context')
 mid,graph_sha,level,stage,part,group,index=context
 if any(type(x)is not int for x in(mid,level,stage,part,group,index,template)):raise ValueError('NPC stat context type')
 row=policy()['maps'].get(str(mid))
 if row is None:return False
 if row['graph_sha256']!=graph_sha or row['npc_level']!=level:raise ValueError('NPC stat graph or level changed')
 route=catalog._data['routes'].get(str(mid))
 if route is None or route['source']!=row['source']or catalog._data['graphs'][row['source']]['source_sha256']!=graph_sha:raise ValueError('NPC stat original route changed')
 entry=row['sources'].get(':'.join(map(str,(stage,part,group,index,template))))
 if entry is None:return False
 from els_server.game_data import client_data
 native=client_data().npc(template)
 if any(native[k]!=entry[k]for k in('enum','script','class_id','is_npc')):raise ValueError('NPC stat native identity changed')
 values=entry['values']
 if len(attrs)!=97 or len(values)!=4 or any(type(v)not in(int,float)or not math.isfinite(v)or not 0<=v<=2**31-1 for v in values):raise ValueError('NPC stat value bound')
 # Native DA4820 -> 1691DA0 -> v4F0/1C140D0 consumes these raw floats.
 # These are resolved for this NPC level; no growth or gauge multiplier.
 struct.pack_into('<4f',attrs,8,*values)
 return True
