"""Source-bound initialization policy. Estimated values are server-local rules.

This module supplies maximum HP to the original NPC initialization consumer.
It never changes an already spawned actor or implements native combat effects.
"""
import functools, hashlib, json, math, struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA, client_data


@functools.lru_cache(maxsize=1)
def policy():
    directory=Path(__file__).resolve().parents[1]/'data'
    raw=(directory/'formal_npc_hp.json').read_bytes()
    manifest=json.loads((directory/'formal_npc_hp.manifest.json').read_bytes())
    result=json.loads(raw)
    if (manifest['client_sha256']!=CLIENT_SHA
        or manifest['payload_sha256']!=hashlib.sha256(raw).hexdigest()
        or result['client_sha256']!=CLIENT_SHA or result['schema_version']!=1
        or result['policy']!='formal-server-npc-hp-20261025-v1'):
        raise ValueError('Formal NPC HP policy identity')
    return result


def source_map(catalog, dungeon):
    row=policy()['maps'].get(str(dungeon))
    if row is None:raise ValueError('NPC HP map outside finite policy')
    if row.get('role')=='field':
        if getattr(catalog,'_formal_field_sha256',None)!=row['field_payload_sha256']:
            raise ValueError('NPC HP exact field source identity')
        return row
    graph=catalog._data['graphs'].get(row['source'])
    if graph is None or graph['source_sha256']!=row['graph_sha256']:
        raise ValueError('NPC HP original graph identity')
    return row


def level(catalog, dungeon):
    value=source_map(catalog,dungeon)['level']
    if type(value)is not int or not 1<=value<=127:
        raise ValueError('NPC HP source level not established')
    return value


def f32(value):
    value=struct.unpack('<f',struct.pack('<f',value))[0]
    if not math.isfinite(value):raise ValueError('NPC HP float32 bound')
    return value


@functools.lru_cache(maxsize=1)
def raid_policy():
    raw=(Path(__file__).resolve().parents[1]/'data/raid_npc_hp.json').read_bytes()
    result=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=policy()['sources']['raid_local_policy']
        or result['client_sha256']!=CLIENT_SHA or result['schema_version']!=1
        or result['policy']!='finite-raid-hp-local-reference-20261025-v1'
        or sorted(map(int,result['maps']))!=policy()['raid_maps']):
        raise ValueError('Raid HP policy identity')
    return result


def raid_maximum(catalog,template,dungeon,npc_level):
    row=raid_policy()['maps'].get(str(dungeon));meta=source_map(catalog,dungeon)
    if (row is None or row['source']!=meta['source'] or row['graph_sha256']!=meta['graph_sha256']
        or type(npc_level)is not int or npc_level!=row['level']):
        raise ValueError('Raid HP exact mode graph and NPC level')
    item=row['templates'].get(str(template));definition=client_data().npc(template)
    if (item is None or item['enum']!=definition['enum']
        or item['script']!=(definition['script']or'').lower()
        or item['class_id']!=definition['class_id'] or item['is_npc']!=definition['is_npc']):
        raise ValueError('Raid HP exact finite template identity')
    result=f32(item['hp'])
    if result<=0:raise ValueError('Raid HP positive maximum')
    return result


def maximum(catalog, template, *, dungeon, npc_level=None, boss=False):
    data=policy();row=data['templates'].get(str(template))
    if type(template)is not int or row is None:raise ValueError('NPC HP unknown template')
    definition=client_data().npc(template)
    if (definition['enum']!=row['enum'] or (definition['script']or'').lower()!=row['script']
        or definition['class_id']!=row['class_id'] or definition['is_npc']!=row['is_npc']):
        raise ValueError('NPC HP exact current identity')
    native=catalog._data['npcs'].get(str(template))
    if native is None:raise ValueError('NPC HP missing native initialization')
    meta=source_map(catalog,dungeon)
    explicit=native['script_max_hp']
    if explicit is not None:
        if row.get('source')!='current_client_explicit' or row.get('fixed')!=explicit:
            raise ValueError('NPC HP explicit source changed')
        result=f32(explicit)
    else:
        if 'fixed'in row:raise ValueError('NPC HP explicit field disappeared')
        value=level(catalog,dungeon) if npc_level is None else npc_level
        if type(value)is not int or not 1<=value<=127:raise ValueError('NPC HP NPC level bound')
        if dungeon in data['raid_maps']:
            return raid_maximum(catalog,template,dungeon,value)
        if 'base'in row:base,growth=row['base'],row['growth']
        else:
            role='boss'if boss else'ordinary'
            profile=data['profiles'].get(meta['region']+':'+role,data['profiles']['default:'+role])
            base,growth=profile['base'],profile['growth']
        if base<=0 or growth<0:raise ValueError('NPC HP source coefficient bound')
        result=f32(f32(base)+f32(f32(growth)*f32(value)))
    if result<=0:raise ValueError('NPC HP positive maximum required')
    return result


def summoned_maximum(run,template):
    stage=run.graph['stages'][str(run.stage)]
    meta=source_map(run.catalog,run.identity)
    if run.graph['source_sha256']!=meta['graph_sha256'] or template not in stage['allowed_summons']:
        raise ValueError('NPC HP original summon whitelist')
    roles=set()
    def visit(row):
        if 'options'in row:
            for child in row['options']:visit(child)
        elif row['template']==template:roles.add(bool(row['boss']))
    for part in stage['parts'].values():
        for group in part['groups']:
            for row in group['npcs']:visit(row)
    # The incoming boss flag is not numeric authority. Reuse a unique original
    # static role when present; otherwise ordinary is the declared local rule.
    boss=next(iter(roles))if len(roles)==1 else False
    value=level(run.catalog,run.identity)
    return maximum(run.catalog,template,dungeon=run.identity,npc_level=value,boss=boss),value


def initialized_maximum(run,source):
    """Expected original actor HP for existing finite retirement receivers."""
    value=run.catalog.static_npc_level(run.identity,run.graph,run.stage,run.part,source)
    if value is None:value=level(run.catalog,run.identity)
    return maximum(run.catalog,source['template'],dungeon=run.identity,npc_level=value,boss=source['boss'])


def legacy_population(stage,npcs):
    """Apply only after the existing original El Tree fixture verification."""
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.dungeon_hp_c1 import LEGACY_SOURCES,LEVEL_IDENTITIES,_fingerprint
    from els_server.domain.dungeon_npcs import resource_dto,encode_npc
    catalog=route_catalog();source_map(catalog,30000);graph=catalog.graph(30000)
    result=[]
    for original in npcs:
        row=dict(original);template=row['template'];witness=LEGACY_SOURCES.get((stage,row['key']))
        if witness is None or witness[1]!=template:raise ValueError('NPC HP legacy instance identity')
        groups=graph['stages'][str(stage)]['parts']['0']['groups']
        if len(groups)!=1 or groups[0]['index']!=-1:raise ValueError('NPC HP legacy original group')
        source=next((s for s in groups[0]['npcs']if s['source_index']==witness[0]),None)
        if source is None or _fingerprint(source)!=witness[3]:raise ValueError('NPC HP legacy original source')
        # C1 may already have changed only maximum HP and the four exact
        # basic NPC levels. The verified fixture remains the identity witness.
        raw=bytearray.fromhex(row['resource_hex'])
        if len(raw)!=0x98 or struct.unpack_from('<ii',raw)!=(row['key'],template):
            raise ValueError('NPC HP legacy native resource')
        value=catalog.static_npc_level(30000,graph,stage,0,source)
        if template in LEVEL_IDENTITIES:
            raw[0xc]=value
            row['resource_hex']=raw.hex();row['wire_hex']=encode_npc(resource_dto(raw),0).hex()
        hp=maximum(catalog,template,dungeon=30000,npc_level=value,boss=source['boss'])
        init=bytearray.fromhex(row['init_hex']);cursor=5
        if struct.unpack_from('>i',init)[0]!=template:raise ValueError('NPC HP legacy initializer identity')
        for i in range(6):
            if i==4:
                if init[cursor]!=1:raise ValueError('NPC HP legacy init flag')
                cursor+=1
            length=struct.unpack_from('>I',init,cursor)[0];cursor+=4+length
        if len(init)-cursor!=98:raise ValueError('NPC HP legacy stat boundary')
        struct.pack_into('>f',init,cursor+4,hp)
        row['init_hex']=init.hex();row['hp']=hp;result.append(row)
    return result
