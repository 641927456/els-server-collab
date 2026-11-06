"""Rebuild the source-qualified resurrection registry from pinned client data.

Reads the immutable client catalog and the pinned solo route graphs, then writes
`known_resurrection_maps.json`/`.manifest.json`. Explicit shared-room spawn keys
that were already reviewed are carried over unchanged; every other stage uses
the native solo -1 selector.
"""
import hashlib
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from els_server.game_data import CLIENT_SHA, DATA_DIR  # noqa: E402

DATA = ROOT / 'els_server/data'


def canon(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def raw_sha(data):
    return hashlib.sha256(data).hexdigest()


def client_definitions():
    with sqlite3.connect((DATA_DIR / 'catalog.sqlite3').as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        return {row[0]: json.loads(row[1]) for row in db.execute('SELECT id,definition FROM dungeons')}


def build():
    routes_raw = (DATA_DIR / 'dungeon_routes.json').read_bytes()
    routes = json.loads(routes_raw)
    routes_manifest = json.loads((DATA_DIR / 'dungeon_routes.manifest.json').read_text(encoding='utf8'))
    if routes_manifest['client_sha256'] != CLIENT_SHA:
        raise ValueError('Dungeon route client identity')
    if raw_sha(routes_raw) != routes_manifest['payload_sha256']:
        raise ValueError('Dungeon route payload changed')
    definitions = client_definitions()
    graphs = routes['graphs']
    previous = json.loads((DATA / 'known_resurrection_maps.json').read_text(encoding='utf8'))
    manifest = json.loads((DATA / 'known_resurrection_maps.manifest.json').read_text(encoding='utf8'))
    if previous['client_sha256'] != CLIENT_SHA or manifest['client_sha256'] != CLIENT_SHA:
        raise ValueError('Resurrection registry client identity')

    maps = {}
    rule_sources = []
    solo_scope = {}
    shared_scope = {}
    for identity_text, route in sorted(routes['routes'].items(), key=lambda pair: int(pair[0])):
        identity = int(identity_text)
        if identity not in definitions:
            raise ValueError('Missing client dungeon definition: %d' % identity)
        source = definitions[identity]
        graph = graphs[route['source']]
        stages = {}
        carried = previous['maps'].get(identity_text, {}).get('stages', {})
        for stage_text, stage in sorted(graph['stages'].items(), key=lambda pair: int(pair[0])):
            parts = sorted({int(part) for part in stage['parts']})
            old = carried.get(stage_text)
            if old is not None and old.get('keys'):
                entry = dict(old)
                if sorted(int(part) for part in entry['parts']) != parts:
                    raise ValueError('Carried spawn keys changed stage parts: %d/%s' % (identity, stage_text))
                shared_scope.setdefault(identity_text, []).append(int(stage_text))
            else:
                entry = dict(parts=parts, keys=[], native_solo_selector=True)
            stages[stage_text] = entry
        solo_scope[identity_text] = sorted(int(stage) for stage in stages)
        maps[identity_text] = dict(
            graph_source_sha256=graph['source_sha256'],
            definition_sha256=canon(source),
            stages=stages,
        )
        condition = source.get('DUNGEON_CHECK_CONDITION', {})
        rule_sources.append(dict(
            dungeon=identity,
            definition_sha256=canon(source),
            graph_source_sha256=graph['source_sha256'],
            DUNGEON_CHECK_CONDITION=sorted({int(v) for v in condition.values()}),
            LimitedMaxResurrectionUseCount_present='LimitedMaxResurrectionUseCount' in source,
            stages=sorted({int(stage) for stage in stages}),
            parts=sorted({part for stage in stages.values() for part in stage['parts']}),
            encounter=graph.get('encounter'),
        ))

    payload = dict(
        schema_version=1,
        client_sha256=CLIENT_SHA,
        maps=maps,
        scope=('Every pinned solo route stage uses the native -1 selector. General maps keep no per-run '
               'revival cap; only client-declared LimitedMaxResurrectionUseCount caps the remaining maps. '
               'Reviewed shared-room spawn keys are carried unchanged.'),
    )
    body = (json.dumps(payload, indent=2, ensure_ascii=False) + '\n').encode('utf8')
    manifest['solo_native_selector_scope'] = solo_scope
    manifest['shared_explicit_key_scope'] = shared_scope
    manifest['map_rule_sources'] = rule_sources
    manifest['payload_sha256'] = raw_sha(body)
    return body, manifest


def main():
    body, manifest = build()
    (DATA / 'known_resurrection_maps.json').write_bytes(body)
    (DATA / 'known_resurrection_maps.manifest.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    print('maps=%d payload=%s' % (len(json.loads(body)['maps']), manifest['payload_sha256']))


if __name__ == '__main__':
    main()
