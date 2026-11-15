"""Thirty native Hero scenes; one uniform draw per admitted run seed.

The entry/reward identity remains 120010. Scene IDs are private dependencies,
never additional selectable dungeons. Repeated selections are intentional.
"""
import copy
import functools
import hashlib
import json
import uuid
from pathlib import Path

DUNGEON = 120010
SCENES = tuple(range(110010, 110301, 10))


@functools.lru_cache(maxsize=1)
def policy():
    from els_server.game_data import CLIENT_SHA, client_data
    directory = Path(__file__).resolve().parents[1] / 'data'
    raw = (directory / 'hero_routes.json').read_bytes()
    manifest = json.loads((directory / 'hero_routes.manifest.json').read_bytes())
    data = json.loads(raw)
    if (manifest['payload_sha256'] != hashlib.sha256(raw).hexdigest()
            or data['client_sha256'] != CLIENT_SHA
            or data['policy'] != 'hero-30-equal-local-20261115-v1'
            or set(data['routes']) != set(map(str, SCENES))):
        raise ValueError('Hero scene policy identity')
    for identity in SCENES:
        native = client_data().dungeon(identity)
        source = data['routes'][str(identity)]['source']
        if native['dataFileName'].lower() != source or native['difficulty'] != 2:
            raise ValueError('Hero original scene identity')
    return data


def select(run_id):
    # Rejection sampling avoids modulo bias, and every peer with this run UUID
    # gets exactly the same result without sharing mutable random state.
    seed = uuid.UUID(run_id).bytes
    limit = (1 << 256) - (1 << 256) % len(SCENES)
    counter = 0
    while True:
        draw = int.from_bytes(hashlib.sha256(b'hero-scene-v1:' + seed
                              + counter.to_bytes(4, 'big')).digest(), 'big')
        if draw < limit:
            return SCENES[draw % len(SCENES)]
        counter += 1


def catalog(base, run_id):
    scene = select(run_id)
    data = policy()
    view = copy.copy(base)
    selected = data['routes'][str(scene)]
    # Retain already deployed graph/actor corrections when a source is shared.
    graphs = {**data['graphs'], **base._data['graphs']}
    npcs = {**data['npcs'], **base._data['npcs']}
    view._data = {**base._data, 'graphs': graphs, 'npcs': npcs,
                  'routes': {**base._data['routes'], str(DUNGEON): {
                      **base._data['routes'][str(DUNGEON)], 'source': selected['source']}}}
    view.manifest = {**base.manifest, 'source_sha256': {
        **data['sources'], **base.manifest['source_sha256']}}
    view.hero_scene = scene
    return view


def scene(identity, run_id):
    return select(run_id) if identity == DUNGEON else identity


def graph_profile(catalog, original):
    source = catalog._data['routes'][str(DUNGEON)]['source']
    graph = catalog._data['graphs'][source]
    if graph['source_sha256'] == original['graph_sha256']:
        return original
    # Original map-specific numerical exceptions cannot authorize another map.
    return {k: v for k, v in original.items() if k not in (
        'public_hp_templates', 'public_hp_sources', 'combat_hp_overrides')}


def hp_profile(catalog, original):
    row = graph_profile(catalog, original)
    source = catalog._data['routes'][str(DUNGEON)]['source']
    return {**row, 'source': source,
            'graph_sha256': catalog._data['graphs'][source]['source_sha256']}


def maximum(catalog, template):
    """Finite compiled, source-bound HP inputs; no generic 500/5000 fallback."""
    graph = catalog._data['graphs'][catalog._data['routes'][str(DUNGEON)]['source']]
    row = policy()['hp'][graph['source_sha256']][str(template)]
    native = catalog._data['npcs'][str(template)]
    if row['script_max_hp'] != native['script_max_hp']:
        raise ValueError('Hero HP original component changed')
    return row['hp']


def is_random_run(run):
    return run is not None and run.identity == DUNGEON and hasattr(run.catalog, 'hero_scene')


def final_boss(run, npc):
    if not is_random_run(run) or not npc['active'] or not npc['boss']:
        return False
    if not any(t['kind'] == 4 for c in run.current['conditions'] for t in c['next']):
        return False
    return all(n is npc or n['key'] in run.defeated for n in run.current['npcs']
               if n['active'] and n['boss'])


def loot_map(run, original):
    return {**original, 'graph_sha256': run.graph['source_sha256']}


def graph_by_sha(base, digest):
    data=policy()
    graphs={**data['graphs'],**base._data['graphs']}
    for route in data['routes'].values():
        graph=graphs[route['source']]
        if graph['source_sha256']==digest:
            return graph
    raise ValueError('Unknown Hero source graph')


def line_rules(run, original):
    rows=rules_for_graph(run,original.values(),'source_sha256')
    result={}
    for row in rows:
        key=(row['dungeon'],row['stage'],row['part'],row['trigger'])
        if key in result and result[key]!=row:
            raise ValueError('Conflicting native Hero trigger sources')
        result[key]=row
    return result


def rules_for_graph(run, rows, graph_key):
    """Reuse exact original source rules across entry identities."""
    if not is_random_run(run):
        return rows
    graph = run.graph['source_sha256']
    if graph_key=='graph_sha':
        rows=(*rows,*policy()['retirements'])
    by_source = {}
    for row in rows:
        if row[graph_key] != graph:
            continue
        value = {**row, 'dungeon': DUNGEON}
        by_source[json.dumps(value, sort_keys=True)] = value
    return tuple(by_source.values())
