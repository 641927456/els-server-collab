"""Source-qualified native player spawn keys; no position/effect simulation."""
from pathlib import Path
import functools,hashlib,json
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    root=Path(__file__).resolve().parents[1]/'data'
    raw=(root/'known_resurrection_maps.json').read_bytes()
    manifest=json.loads((root/'known_resurrection_maps.manifest.json').read_bytes())
    if (manifest['schema_version']!=1 or manifest['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']):raise ValueError('Resurrection map source mismatch')
    value=json.loads(raw)
    if value['schema_version']!=1 or value['client_sha256']!=CLIENT_SHA:raise ValueError('Resurrection map version')
    return value['maps']

def qualified(s):
    from els_server.domain.dungeon_routes import route_catalog
    if type(s.dungeon_id)is not int or type(s.gate_stage)is not int:raise ValueError('Resurrection map identity')
    row=catalog().get(str(s.dungeon_id))
    if row is None:raise ValueError('Resurrection scene source not qualified')
    source=client_data().dungeon(s.dungeon_id)
    digest=hashlib.sha256(json.dumps(source,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    routes=route_catalog();route=routes._data['routes'].get(str(s.dungeon_id))
    if (digest!=row['definition_sha256'] or route is None
        or routes._data['graphs'][route['source']]['source_sha256']!=row['graph_source_sha256']):raise ValueError('Resurrection scene changed')
    stage=row['stages'].get(str(s.gate_stage));part=s.dungeon_run.part if s.dungeon_run is not None else 0
    if stage is None or part not in stage['parts']:raise ValueError('Resurrection substage not qualified')
    keys=tuple(stage.get('keys',()))
    if not keys:
        if stage.get('native_solo_selector')is not True:raise ValueError('Resurrection native selector not qualified')
        return ()  # Shared admission rejects this; one native client selects its own loaded map key.
    if any(type(k)is not int or not 0<=k<2**31 for k in keys):raise ValueError('Resurrection spawn keys invalid')
    return keys

def shared_position(epoch,owner,life,keys):
    # One room-authoritative choice is broadcast unchanged; each client must
    # not independently execute the native random (-1) selector.
    raw=(epoch+':revive:'+str(owner)+':'+str(life)).encode()
    return keys[int.from_bytes(hashlib.sha256(raw).digest(),'big')%len(keys)]
