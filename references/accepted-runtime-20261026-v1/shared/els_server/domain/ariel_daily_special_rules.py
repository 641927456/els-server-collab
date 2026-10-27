"""Exact ordinary daily-special rewards; ownership/reset are approved local policy."""
import functools,hashlib,json
from pathlib import Path

DATA_SHA='5ce1402b5d7109470e9f3a2d67bd05e95fbc5db3d3a1214556f877191c757fcb'

@functools.lru_cache(maxsize=1)
def data():
    raw=(Path(__file__).resolve().parents[1]/'data/ariel_daily_special.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Ariel daily finite source changed')
    value=json.loads(raw)
    if value['version']!=1 or len(value['maps'])!=20 or len(value['items'])!=70:raise ValueError('Ariel daily finite scope')
    return value

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data
    result={}
    for key,row in data()['items'].items():
        t=int(key)
        if t!=row['template'] or hashlib.sha256(client_data().item(t)['record']).hexdigest()!=row['record_sha256']:
            raise ValueError('Ariel daily native item record')
        result[t]={k:row[k]for k in('template','metadata','group','max_stack')}
    return result

def rule(dungeon):
    row=data()['maps'].get(str(dungeon))
    if row is None:return None
    from els_server.domain.dungeon_routes import route_catalog
    c=route_catalog();route=c._data['routes'].get(str(dungeon))
    if route is None or route['source']!=row['source'] or c._data['graphs'][route['source']]['source_sha256']!=row['graph_sha256']:
        raise ValueError('Ariel daily current normal graph changed')
    from els_server.game_data import client_data
    if client_data().dungeon(dungeon).get('m_eDungeonType',0)!=row['dungeon_type']:raise ValueError('Ariel daily mode changed')
    return row

def plans(dungeon,unit,multiplier):
    row=rule(dungeon)
    if row is None or type(unit)is not int or not 1<=unit<=15 or multiplier not in(1,2):raise ValueError('Ariel daily finite grant')
    pairs=row['rewards'] if row['rewards']is not None else row['unit_rewards'][str(unit)]
    defs=definitions()
    return [dict(template=t,metadata=defs[t]['metadata'],group=defs[t]['group'],quantity=q*multiplier)for t,q in pairs]
