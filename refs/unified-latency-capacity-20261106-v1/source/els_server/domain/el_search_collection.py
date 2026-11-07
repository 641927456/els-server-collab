"""Finite original52700 registration and native CollectionData fields."""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA

QUEST=52700
SUB=52701
COST=500

@functools.lru_cache(maxsize=1)
def classes():
    path=PROJECT_ROOT/'els_server/data/el_search_collection.json'
    raw=path.read_bytes();m=json.loads(path.with_suffix('.manifest.json').read_bytes());d=json.loads(raw)
    if (m!={'schema_version':1,'payload_sha256':hashlib.sha256(raw).hexdigest(),'classes':195,'quest':QUEST,'subquest':SUB}
        or d['schema_version']!=1 or d['client_sha256']!=CLIENT_SHA
        or d['image_sha256']!='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
        or len(d['classes'])!=195):raise ValueError('Collection native class source')
    from els_server.domain.character_rules import CLASSES
    for k,r in d['classes'].items():
        if (int(k) not in CLASSES or set(r)!={'unit_type','line','job_stage','transcendental_stages'}
            or any(type(r[n])is not int for n in ('unit_type','line','job_stage'))
            or not 1<=r['unit_type']<=15 or not 0<=r['line']<=4
            or r['job_stage']!=CLASSES[int(k)]['stage']
            or (r['line']==0)!=(r['job_stage']==0)
            or r['transcendental_stages']!={0:[],1:[0],2:[0,1],3:[1,2]}[r['job_stage']]):raise ValueError('Collection source identity')
    return {int(k):r for k,r in d['classes'].items()}

def entry(unit_class,transcendental):
    if type(unit_class)is not int or type(transcendental)is not int:raise ValueError('Collection career fields')
    r=classes().get(unit_class)
    if r is None or not r['line'] or transcendental not in r['transcendental_stages']:raise ValueError('Collection requires a registered job')
    rank=1 if r['job_stage'] in (1,2) else 3 if transcendental==2 else 2
    return dict(unit_type=r['unit_type'],line=r['line'],unit_class=unit_class,transcendental=transcendental,stage=rank)

def current_entry(character):
    from els_server.domain.character_rules import validate_career_state,transcendental_stage
    validate_career_state(character)
    value=entry(character['unit_class'],transcendental_stage(character))
    if value['unit_type']!=character['unit_type']:raise ValueError('Collection role identity')
    return value

def canonical(value):
    if not isinstance(value,dict) or set(value)!={'unit_type','line','unit_class','transcendental','stage'}:raise ValueError('Collection entry fields')
    if any(type(v)is not int for v in value.values()) or value!=entry(value['unit_class'],value['transcendental']):raise ValueError('Collection entry integrity')
    return value

def priority(value):
    canonical(value)
    return value['stage'],classes()[value['unit_class']]['job_stage'],value['transcendental']

def ep_target(sub):
    if (sub.get('m_iID')!=SUB or sub.get('m_eClearType')!=121 or sub.get('m_ClearCondition')!={'m_iClearCount':COST}):raise ValueError('Unsupported EP collection objective')
    return COST

def career_target(sub):
    expected={'m_iID':52702,'m_eClearType':81,'m_bAutomaticDescription':0,'m_ClearCondition':{'m_iClearCount':1,'m_iUnitClassType':1,'m_iTranscendentalClassType':None}}
    if json.dumps(sub,sort_keys=True)!=json.dumps(expected,sort_keys=True):raise ValueError('Unsupported collection career objective')
    return 1

def career_progress(sub,character):
    career_target(sub)
    from els_server.domain.character_rules import validate_career_state,CLASSES
    validate_career_state(character)
    return int(CLASSES[character['unit_class']]['stage']>=1)

def wire(value):
    if (not isinstance(value,dict) or set(value)!={'active','registered','expiry','expansion','field1d','field21','presets'}
        or type(value['active'])is not bool or not isinstance(value['registered'],list)
        or type(value['expiry'])is not int or not 0<=value['expiry']<2**63 or type(value['expansion'])is not int or not 0<=value['expansion']<=4 or value['field1d']!=1 or value['field21']!=1):raise ValueError('Collection native snapshot')
    entries=value['registered']
    keys=[(canonical(r)['unit_type'],r['line'])for r in entries]
    if len(keys)>60 or keys!=sorted(set(keys)):raise ValueError('Collection canonical account keys')
    out=bytes([value['active']])+struct.pack('>I',len(entries))
    for r in entries:out+=struct.pack('>5HiH',r['unit_type'],r['line'],r['unit_type'],r['line'],r['unit_class'],r['transcendental'],r['stage'])
    from els_server.storage.collection_synergy import choices,slots_wire
    presets=value['presets']
    if not isinstance(presets,dict)or any(type(k)is not int or k!=1 for k in presets):raise ValueError('Unqualified synergy preset page')
    out+=struct.pack('>qiI',value['expiry'],value['expansion'],len(presets))
    for page,selected in sorted(presets.items()):out+=struct.pack('>i',page)+slots_wire(choices(selected,entries,value['expansion']))
    return out+struct.pack('>ii',value['field1d'],value['field21'])
