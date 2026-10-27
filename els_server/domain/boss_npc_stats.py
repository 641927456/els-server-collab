"""Finite source-bound raw Boss inputs; the original client computes combat.

No HP, damage-reduction, mode/gauge multiplier, actor mutation, or saved state.
"""
from pathlib import Path
import functools,hashlib,json,math,struct
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def policy():
    root=Path(__file__).resolve().parents[1]/'data'
    raw=(root/'boss_npc_stats.json').read_bytes()
    manifest=json.loads((root/'boss_npc_stats.manifest.json').read_bytes())
    result=json.loads(raw)
    if (manifest['payload_sha256']!=hashlib.sha256(raw).hexdigest()
        or manifest['client_sha256']!=CLIENT_SHA or result['client_sha256']!=CLIENT_SHA
        or result['schema_version']!=1 or result['policy']!='finite-native-first-boss-inputs-20261026-v1'):
        raise ValueError('Boss input policy identity')
    return result

def _source(catalog,mid,row):
    if row['kind']=='field':
        if mid!=40046 or getattr(catalog,'_formal_field_sha256',None)!=row['field_payload_sha256']:
            raise ValueError('Boss original field source')
    else:
        route=next((catalog._data[k][str(mid)] for k in ('routes','internal_routes','event_routes','maps')
            if str(mid)in catalog._data.get(k,{})),None)
        if (route is None or route['source']!=row['source']
            or catalog._data['graphs'][row['source']]['source_sha256']!=row['graph_sha256']):
            raise ValueError('Boss original graph source')

def apply(catalog,template,attrs,context,*,dynamic_context=None,field_context=None):
    if sum(x is not None for x in (context,dynamic_context,field_context))>1:
        raise ValueError('Boss ambiguous source context')
    if context is not None:
        if not isinstance(context,tuple)or len(context)!=7:raise ValueError('Boss static context')
        mid,graph,level,stage,part,group,index=context
        if any(type(x)is not int for x in(mid,level,stage,part,group,index,template)):
            raise ValueError('Boss static context types')
        row=policy()['maps'].get(str(mid))
        if row is None:return False
        entry=row['static'].get(':'.join(map(str,(stage,part,group,index,template))))
        if entry is None:return False
    elif dynamic_context is not None:
        if not isinstance(dynamic_context,tuple)or len(dynamic_context)!=4:raise ValueError('Boss dynamic context')
        mid,graph,level,stage=dynamic_context
        if any(type(x)is not int for x in(mid,level,stage,template)):raise ValueError('Boss dynamic context types')
        row=policy()['maps'].get(str(mid))
        if row is None:return False
        entry=row['dynamic'].get(':'.join(map(str,(stage,template))))
        if entry is None:return False
        native_stage=catalog._data['graphs'][row['source']]['stages'].get(str(stage))
        if native_stage is None or template not in native_stage['allowed_summons']:
            raise ValueError('Boss original dynamic whitelist')
    elif field_context is not None:
        if not isinstance(field_context,tuple)or len(field_context)!=2:raise ValueError('Boss field context')
        mid,level=field_context
        if any(type(x)is not int for x in(mid,level,template)):raise ValueError('Boss field context types')
        row=policy()['maps'].get(str(mid))
        if row is None:return False
        entry=row['field'].get(str(template))
        if entry is None:return False
        graph=row['graph_sha256']
    else:return False
    _source(catalog,mid,row)
    if graph!=row['graph_sha256']or level!=entry['npc_level']:
        raise ValueError('Boss original graph or NPC level')
    native=client_data().npc(template)
    if any(native[k]!=entry[k]for k in('enum','script','class_id','is_npc')):
        raise ValueError('Boss exact native template identity')
    if str(template)not in catalog._data['npcs']or len(attrs)!=97:
        raise ValueError('Boss original initialization')
    values=entry['raw_attack_defense'];resistances=entry['six_resistances']
    if (not isinstance(values,list)or len(values)!=4
        or any(type(x)not in(int,float)or not math.isfinite(x)or not 0<=x<=2**31-1 for x in values)
        or not isinstance(resistances,list)or len(resistances)!=6
        or any(type(x)is not int or not 0<=x<=500 for x in resistances)):
        raise ValueError('Boss raw native input bounds')
    # Entire row checked before mutation. No already-active actor is changed.
    struct.pack_into('<4f',attrs,8,*values)
    struct.pack_into('<6i',attrs,52,*resistances)
    return True
