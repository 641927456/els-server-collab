"""Finite original Hero inputs. Base wire and resulting actor maximum differ."""
import functools,hashlib,json,math,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def policy():
 directory=Path(__file__).resolve().parents[1]/'data'
 raw=(directory/'native_hero_inputs.json').read_bytes();manifest=json.loads((directory/'native_hero_inputs.manifest.json').read_bytes());p=json.loads(raw)
 if (manifest['client_sha256']!=CLIENT_SHA or manifest['payload_sha256']!=hashlib.sha256(raw).hexdigest()
     or p['client_sha256']!=CLIENT_SHA or p['schema_version']!=1 or p['policy']!='finite-native-Hero-120000-source-inputs-20261026-v1'):
  raise ValueError('Native Hero input policy identity')
 return p

def difficulty(identity):
 if identity!=120000:return 0
 p=policy();native=client_data().dungeon(identity)
 if native['difficulty']!=p['difficulty']or native['m_NPCLevel']!=p['npc_level']:
  raise ValueError('Native Hero original difficulty and level')
 return p['difficulty']

def factor_vector(identity):
 if identity!=120000:return bytes(4)
 difficulty(identity);values=policy()['ten_floats']
 if len(values)!=10 or any(type(v)not in(int,float)or not math.isfinite(v)or v<=0 for v in values):
  raise ValueError('Native Hero finite factor vector')
 return struct.pack('>I10f',1,*values)

def source_maximum(catalog,template,base,context):
 if not isinstance(context,tuple)or len(context)!=7:raise ValueError('Native Hero static context')
 mid,graph,level,stage,part,group,index=context
 if mid!=120000:return base,False
 p=policy();difficulty(mid)
 if any(type(v)is not int for v in(mid,template,level,stage,part,group,index)):
  raise ValueError('Native Hero source types')
 route=catalog._data['routes'].get(str(mid))
 if route is None or route['source']!=p['source']or catalog._data['graphs'][p['source']]['source_sha256']!=p['graph_sha256']:
  raise ValueError('Native Hero original route')
 if graph!=p['graph_sha256']or level!=p['npc_level']:raise ValueError('Native Hero original graph and level')
 row=p.get('mode_sources',p['sources']).get(':'.join(map(str,(stage,part,group,index,template))))
 if row is None:return base,False
 native=client_data().npc(template)
 if any(native[k]!=row[k]for k in('enum','script','class_id','is_npc')):
  raise ValueError('Native Hero exact monster identity')
 if type(base)not in(int,float)or not math.isfinite(base)or base<=0:raise ValueError('Native Hero base HP')
 f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
 result=f32(f32(base)*f32(p['ten_floats'][6]))
 if not math.isfinite(result)or result<=0:raise ValueError('Native Hero resulting HP')
 # Only the server authority uses this result. The 97-byte native record
 # still contains base HP; 1041040 -> 15706F0 applies the factor once.
 return result,True

def ability_metadata(keys):
 if len(keys)>16384 or len(set(keys))!=len(keys)or any(type(k)is not int or not 0<=k<16384 for k in keys):
  raise ValueError('Native Hero instance keys')
 return struct.pack('>I',len(keys))+b''.join(struct.pack('>i4b',k,0,0,0,0)for k in keys)+bytes(25)
