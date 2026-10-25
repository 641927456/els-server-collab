"""Finite disclosed primary pools for ten existing owned regional BOSS cubes.

The original JSON and86 primary outcomes remain byte-identical. Branch205 uses
ten independent native alternate groups with an explicitly approved finite
local supplement. Their file/authorization are pinned; there is no primary
fallback or new box producer.
"""
import functools
import hashlib
import json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

BUSINESS_ENABLED=True
LITHIA_ALTERNATE_ENABLED=True
DATA_PATH=Path(__file__).resolve().parents[1]/'data/regional_boss_cubes_legacy.json'
DATA_SHA='28100c20b5171d1d0720904579338a7ffaa36934fd861bafdeeaa95dc4d04947'
LITHIA_DATA_PATH=Path(__file__).resolve().parents[1]/'data/regional_boss_cubes_lithia.json'
LITHIA_DATA_SHA='ce077a2f3d104219ed2c7452cab11bf0ef2ce9cd4aeb092d49dbcbb95711f9af'
LITHIA_AUTHORIZATION_SHA='6dc2fdb497154e30e4c07a8beb5e689bfb086e2bb9b2e91db07059cba6c838f9'
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


def native_group(row,unit_type,unit_class):
    if not BUSINESS_ENABLED:raise ValueError('Regional cube producer disabled')
    from els_server.storage.characters import BASE_CLASSES
    if (type(unit_type)is not int or unit_type not in BASE_CLASSES
            or type(unit_class)is not int or client_data().unit(unit_class)['unitType']!=unit_type):
        raise ValueError('Legacy cube character identity')
    branches=[v for k,v in row['random_rule'].items()
              if k.isdigit() and v['m_cUnitClass']==BASE_CLASSES[unit_type]]
    if len(branches)!=1:
        raise ValueError('Legacy cube native class branch identity')
    group=branches[0]['m_iItemGroupID']
    if group not in(row['primary_group'],row['alternate_group']):
        raise ValueError('Legacy cube group outside finite source')
    return group


def pool_for(row,unit_type,unit_class):
    """Resolve the original class branch before selecting a qualified pool.

    An alternate group remains closed until its contents have an independent
    native/source contract or an explicitly approved finite local policy.
    Generic item descriptions and an unqualified primary list cannot fill it.
    """
    group=native_group(row,unit_type,unit_class)
    if group==row['primary_group']:return row
    if not LITHIA_ALTERNATE_ENABLED or unit_type!=15 or group!=row['alternate_group']:
        raise ValueError('Legacy cube native alternate pool remains unqualified')
    qualified=_lithia_data().get(group)
    if qualified is None or qualified['box']!=row['template']:
        raise ValueError('Legacy cube exact alternate group policy missing')
    return dict(row,entries=qualified['entries'],resolved_group=group,
                local_policy='user-approved-lithia-ten-owned-regional-cubes-20261026-v1',
                policy_sha256=LITHIA_DATA_SHA)



def require_primary(row,unit_type,unit_class):
    # Backward-compatible guard until the native preview hook uses pool_for.
    if native_group(row,unit_type,unit_class)!=row['primary_group']:
        raise ValueError('Legacy cube native branch has no witnessed reward pool')


@functools.lru_cache(maxsize=1)
def _lithia_data():
    try:raw=LITHIA_DATA_PATH.read_bytes()
    except OSError as error:raise ValueError('Lithia regional policy resource missing')from error
    if hashlib.sha256(raw).hexdigest()!=LITHIA_DATA_SHA:
        raise ValueError('Lithia regional policy data changed')
    c=json.loads(raw)
    if (c['schema_version']!=1 or c['approved']is not True
            or c['policy']!='user-approved-lithia-ten-owned-regional-cubes-20261026-v1'
            or c['authorization_sha256']!=LITHIA_AUTHORIZATION_SHA
            or c['proposal_sha256']!='9c7dffec3ec99aace90b4510bb8d9950c8222abbc68a5250ec93275b4fe4c13b'
            or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']
            or c['primary_data_sha256']!=DATA_SHA
            or c['scope']!=dict(unit_type=15,native_base_class=205,owned_boxes_only=True,
                                new_acquisition_sources=False,box_debit=1,ED_cost=0,reward_quantity=1)
            or tuple(r['box']for r in c['groups'])!=BOXES
            or tuple(r['native_group']for r in c['groups'])!=tuple(range(60353,60363))):
        raise ValueError('Lithia regional exact authorization/finite scope')
    originals={r['template']:r for r in data()['definitions']}
    for row in c['groups']:
        original=originals[row['box']]
        # Equality checks the frozen approved values; the independent payload
        # is mandatory, and never substituted from the primary list at runtime.
        if (row['native_base_class']!=205 or row['native_group']!=original['alternate_group']
                or row['entries']!=original['entries']
                or any(type(e['template'])is not int or type(e['weight'])is not int
                       or e['quantity']!=1 or not 0<e['weight']<=10000 for e in row['entries'])
                or sum(e['weight']for e in row['entries'])!=10000):
            raise ValueError('Lithia regional exact approved entries')
    return {r['native_group']:r for r in c['groups']}
