"""Current common Force books, exclusion groups and original NPC sources."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA

SHA='6dab774cc2efcfaf94aa4aee12f308482d072268f709b0bf90f1e67a5e96adb6'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/native_force_catalog.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Native force catalog checksum')
    result=json.loads(raw);data=client_data()
    if result['schema_version']!=1 or result['client_sha256']!=CLIENT_SHA or result['catalog_sha256']!=data.manifest['catalog_sha256']:
        raise ValueError('Native force catalog build')
    for row in result['definitions']:
        item=data.item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or item['metadata']!=row['metadata']:
            raise ValueError('Native force inventory identity')
    for row in result['books']:
        item=data.item(row['item']);kind=data.skill(row['skill'])['m_eType']
        if (kind!=(20 if row['active']else 17) or row['required_stage']!=3
            or {3:3,2:4,1:5,6:6}[(item['flags4']>>20)&15]!=row['native_rank']
            or hashlib.sha256(item['record']).hexdigest()!=row['template_record_sha256']):
            raise ValueError('Native force book identity')
    return result

@functools.lru_cache(maxsize=1)
def by_skill():return {r['skill']:r for r in catalog()['books']}

def exclusion_group(skill):
    row=by_skill().get(skill)
    return row['exclusion_group'] if row else skill

def inventory_definitions():return catalog()['definitions']
