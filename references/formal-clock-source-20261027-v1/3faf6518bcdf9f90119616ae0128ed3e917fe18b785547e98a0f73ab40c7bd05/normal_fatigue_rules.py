"""Finite original routes and retained ordinary-fatigue potion definitions."""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType
DATA_SHA='21d8e89d6155b36bf88580cad5ab0d9c414d4d8532ccc2f2ad3434b822a68292'

@functools.lru_cache(maxsize=1)
def policy():
    from els_server.game_data import client_data,CLIENT_SHA
    p=Path(__file__).resolve().parents[1]/'data/normal_fatigue.json';raw=p.read_bytes();d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA or d['client_sha256']!=CLIENT_SHA or d['maximum']!=4800 or d['new_sources']or d['schema_version']!=1:raise ValueError('Ordinary fatigue source policy')
    if len(d['routes'])!=260 or len(d['potions'])!=19 or len({r['template']for r in d['potions']})!=19 or any(type(r['cost'])is not int or not 0<=r['cost']<=4800 for r in d['routes'].values()):raise ValueError('Ordinary fatigue finite source count/value')
    for mid,r in d['routes'].items():
        original=client_data().dungeon(int(mid)).get('m_iDecreaseSpirit')
        if r['basis']=='current_client_explicit'and original!=r['cost']or r['basis']!='current_client_explicit'and original is not None:raise ValueError('Ordinary fatigue current native cost changed')
        if r['basis']=='cobodex_missing_field_total_reference_local_rule':
            costs=r.get('stage_costs',{})
            if (original is not None or r.get('website_total_cost')!=150 or not costs
                or any(type(v)is not int or not 0<=v<=4800 for v in costs.values())
                or sum(costs.values())!=150 or r['cost']!=max(costs.values())):
                raise ValueError('Ordinary fatigue public total/stage source')
    for r in d['potions']:
        i=client_data().item(r['template'])
        if i['record'].hex()!=r['record_hex']or hashlib.sha256(i['record']).hexdigest()!=r['record_sha256']or i['item_type']!=7 or i['metadata']!=r['metadata']or struct.unpack_from('<I',i['record'],16)[0]!=r['raw_max_stack']or r['restore']not in(960,1440,4800):raise ValueError('Ordinary fatigue exact retained potion')
    d['sha256']=hashlib.sha256(raw).hexdigest();return d

def enabled():return policy()['enabled']
def potions():return MappingProxyType({r['template']:MappingProxyType(r)for r in policy()['potions']})
def admitted():return frozenset(potions())if enabled()else frozenset()

def route(mid,run=None):
    r=policy()['routes'].get(str(mid))
    if r is None:return None
    from els_server.domain.dungeon_routes import route_catalog
    c=route_catalog();original=c._data[r['catalog']].get(str(mid))
    if original is None:raise ValueError('Ordinary fatigue original route missing')
    g=c._data['graphs'][original['source']]
    if g['source_sha256']!=r['graph_sha256']or g['source']!=r['source']or run is not None and(run.identity!=mid or run.catalog is not c or run.graph!=g):raise ValueError('Ordinary fatigue original graph identity')
    return r

class _ExistingFatiguePotion(dict):
    __slots__=('_original',)

def read_existing(item):
    keys={'uid','template','metadata','count','group','slot'};rules=potions();r=rules.get(item.get('template'))if type(item)is dict else None
    if r is None or set(item)-{'expires_at','lock_until','sealed','seal_used'}!=keys or any(type(item[k])is not int for k in keys)or not 0<item['uid']<2**63 or(item['metadata'],item['group'])!=(r['metadata'],4)or not 0<item['count']<=r['owned_max_stack']:raise ValueError('Owned ordinary fatigue potion shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0<=item['slot']<wire_limit(4):raise ValueError('Ordinary fatigue bag slot')
    v=dict(item)
    if 'expires_at'in v:
        from els_server.domain.item_expiration import validate
        validate(v['expires_at'])
    if 'lock_until'in v:
        from els_server.domain.item_locks import validate
        validate(v['lock_until'])
    if 'sealed'in v or'seal_used'in v:
        from els_server.storage.item_seals import validate
        validate(v.get('sealed',False),v.get('seal_used',0))
    out=_ExistingFatiguePotion(v);out._original=dict(v);return out

def validate_existing(item):
    if type(item)is not _ExistingFatiguePotion or dict(item)!=item._original:raise ValueError('Unchanged owned ordinary-fatigue reader required')
    read_existing(dict(item));return item


def debit(r,context):
    """Keep native costs; missing-field website totals count once per stage."""
    if r['basis']!='cobodex_missing_field_total_reference_local_rule':return context,r['cost']
    stage=context.get('stage');costs=r['stage_costs']
    if type(stage)is not int or str(stage)not in costs:raise ValueError('Website fatigue original stage')
    keys=('epoch','reward_run','owner','dungeon','stage','graph_sha256')
    if any(k not in context for k in keys)or context['graph_sha256']!=r['graph_sha256']:
        raise ValueError('Website fatigue source context')
    stable={k:context[k]for k in keys};stable['scope']='cobodex-total-once-per-original-stage'
    return stable,costs[str(stage)]
