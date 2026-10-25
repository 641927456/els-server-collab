"""Versioned native quick-item group identities, distinct from template IDs."""
import functools,hashlib,json
from els_server.game_data import DATA_DIR,CLIENT_SHA


@functools.lru_cache(maxsize=1)
def mappings():
    raw=(DATA_DIR/'quick_bindings.json').read_bytes()
    manifest=json.loads((DATA_DIR/'quick_bindings.manifest.json').read_text(encoding='utf8'))
    if manifest['schema_version']!=1 or manifest['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=manifest['sha256']:
        raise ValueError('Quick binding catalog identity')
    rows=json.loads(raw)
    if len(rows)!=manifest['count'] or any(len(r)!=2 or any(type(n) is not int or n<=0 for n in r) for r in rows):
        raise ValueError('Quick binding catalog rows')
    values=dict(rows)
    if len(values)!=len(rows) or len(set(values.values()))!=manifest['groups']:
        raise ValueError('Quick binding catalog cardinality')
    return values


def item_binding(template):return mappings().get(template,0)


@functools.lru_cache(maxsize=1)
def binding_ids():return frozenset(mappings().values())
