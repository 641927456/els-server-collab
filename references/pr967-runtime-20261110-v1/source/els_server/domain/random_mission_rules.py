"""Finite current-native missions and explicitly approved local probability."""
import functools,hashlib,json
from pathlib import Path
DATA_SHA='396aeebcc7ec158c6c3af1acbbc085263ca1c58318a0f93ddf4fe528c1a74297'

@functools.lru_cache(maxsize=1)
def policy():
    from els_server.game_data import CLIENT_SHA
    p=Path(__file__).resolve().parents[1]/'data/random_missions.json';raw=p.read_bytes();d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA or d['client_sha256']!=CLIENT_SHA or d['schema']!=1 or d['mission_type']!=5 or d['mission_text_id']!=30681 or d['base_chance']!=20 or d['potion_chance']!=100 or d['new_potion_sources']:raise ValueError('Random mission finite policy')
    if d['experience_weights']!=[[110,50],[120,25],[150,15],[200,7],[300,2],[500,1]] or d['pools']!={'ordinary':[380,381,382,383],'maximum':[384,385,386,368,369,387]} or d['duration']!=1800 or d['maximum_stacks']!=3:raise ValueError('Random mission approved values')
    body={k:v for k,v in d.items()if k!='enabled'};d['identity']=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest();return d

def enabled():return policy()['enabled'] is True

def route(mid,run=None):
    r=policy()['routes'].get(str(mid))
    if r is None:return None
    from els_server.domain.dungeon_routes import route_catalog
    catalog=route_catalog();native=catalog._data['routes'].get(str(mid))
    if native is None:raise ValueError('Mission original normal route missing')
    graph=catalog._data['graphs'][native['source']]
    if graph['source_sha256']!=r['graph_sha256'] or graph['source']!=r['source'] or len(graph['stages'])<2 or run is not None and(run.identity!=mid or run.catalog is not catalog or run.graph!=graph):raise ValueError('Mission original graph identity')
    return r

def pool(level):
    if type(level)is not int or not 1<=level<=99:raise ValueError('Mission reward level')
    return tuple(policy()['pools']['maximum'if level==99 else'ordinary'])

def effect(buff):
    r=policy()['buffs'].get(str(buff))
    if r is None or r['period']!=1800 or r['maximum_stacks']!=3:raise ValueError('Mission native effect identity')
    return r
