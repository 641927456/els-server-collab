"""Finite disclosed primary pools for ten existing owned regional BOSS cubes.

The JSON carries extracted facts and source archive hashes. Those archives are
build evidence, not runtime dependencies. Branch205 selects a different,
unwitnessed pool and must never fall back to the primary pool.
"""
import functools
import hashlib
import json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

BUSINESS_ENABLED=True
DATA_PATH=Path(__file__).resolve().parents[1]/'data/regional_boss_cubes_legacy.json'
DATA_SHA='28100c20b5171d1d0720904579338a7ffaa36934fd861bafdeeaa95dc4d04947'
BOXES=(130159,130160,130161,130162,130645,131262,133471,160662,160774,162020)
SOURCE_HASHES=('9e9bcbfad45c2043cdd660f26eb3f10042f21db4ef6ab8632deae841bc1b927c',
               '618bacd86fa68ab92d40e8d98ce51da4d536e0f57c45801e3375704616e8699c')


@functools.lru_cache(maxsize=1)
def data():
    raw=DATA_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:
        raise ValueError('Legacy regional cube data changed')
    c=json.loads(raw)
    if (c['client_sha256']!=CLIENT_SHA
            or c['source_catalog_sha256']!=client_data().manifest['catalog_sha256']
            or tuple(s['sha256'] for s in c['sources'])!=SOURCE_HASHES):
        raise ValueError('Legacy regional cube evidence identity')
    if tuple(r['template'] for r in c['definitions'])!=BOXES or len(c['items'])!=86:
        raise ValueError('Legacy regional cube finite shape')
    for row in c['definitions']:
        if (row['selection_count']!=0 or row['random'] is not True
                or row['grant_source']!='regional_boss_cube'
                or row['alternate_group']-row['primary_group']!=10
                or sum(e['weight'] for e in row['entries'])!=10000):
            raise ValueError('Legacy regional cube mode/probability')
        for entry in row['entries']:
            if (entry['quantity']!=1 or not 0<entry['weight']<=10000
                    or hashlib.sha256(client_data().item(entry['template'])['record']).hexdigest()
                    !=c['items'][str(entry['template'])]['record_sha256']):
                raise ValueError('Legacy regional reward identity')
    return c


def catalog():
    if not BUSINESS_ENABLED:return {}
    # An uninstalled optional candidate must not disable every existing cube.
    if not DATA_PATH.is_file():return {}
    return {r['template']:r for r in data()['definitions']}


def require_primary(row,unit_type,unit_class):
    if not BUSINESS_ENABLED:raise ValueError('Regional cube producer disabled')
    from els_server.storage.characters import BASE_CLASSES
    if (type(unit_type)is not int or unit_type not in BASE_CLASSES
            or type(unit_class)is not int or client_data().unit(unit_class)['unitType']!=unit_type):
        raise ValueError('Legacy cube character identity')
    branches=[v for k,v in row['random_rule'].items()
              if k.isdigit() and v['m_cUnitClass']==BASE_CLASSES[unit_type]]
    if len(branches)!=1 or branches[0]['m_iItemGroupID']!=row['primary_group']:
        raise ValueError('Legacy cube native branch has no witnessed reward pool')
