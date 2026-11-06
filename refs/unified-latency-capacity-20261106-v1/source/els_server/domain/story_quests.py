"""Pinned main, normal and story tasks supported by authoritative events."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def story_catalog():
    path=PROJECT_ROOT/'els_server/data/story_quests.json'
    raw=path.read_bytes();manifest=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf8'))
    row=json.loads(raw);data=client_data()
    if (manifest['schema_version']!=1 or row['schema_version']!=1
        or manifest['client_sha256']!=CLIENT_SHA or row['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']
        or row['catalog_sha256']!=data.manifest['catalog_sha256']
        or len(row['quests'])!=manifest['quests'] or len(row['subquests'])!=manifest['subquests']):
        raise ValueError('Story task catalog identity')
    for item in row['reward_definitions']:
        if (hashlib.sha256(data.item(item['template'])['record']).hexdigest()!=item['record_sha256']
            or item['native']!=[dict(count=n,ok=1,consumed=304) for n in sorted({1,item['max_stack']})]):
            raise ValueError('Story task item evidence')
    return row
