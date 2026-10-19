"""Finite current first/second/third job and transcendence definitions; native quest UI and effects remain native."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

TRANSCENDENCE_IDS=frozenset((41990, 42000, 42010, 42020, 42030, 51031, 51032, 51033, 51034, 51035, 52870, 52880, 52890, 52900, 52910, 53710, 53720, 53730, 53731, 53732))

@functools.lru_cache(maxsize=1)
def catalog():
    path=PROJECT_ROOT/'els_server/data/job_quests.json'
    raw=path.read_bytes();row=json.loads(raw)
    manifest=json.loads(path.with_suffix('.manifest.json').read_bytes());data=client_data()
    if (row['schema_version']!=1 or manifest['schema_version']!=1
        or row['client_sha256']!=CLIENT_SHA or manifest['client_sha256']!=CLIENT_SHA
        or row['catalog_sha256']!=data.manifest['catalog_sha256']
        or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']
        or len(row['quests'])!=824 or manifest['quests']!=824
        or len(row['subquests'])!=manifest['subquests']
        or set(row['quests'])!=set(row['targets'])):raise ValueError('Job catalog identity')
    from els_server.domain.character_rules import CLASSES
    from els_server.domain.careers import PARENTS
    from els_server.domain.acquisition_policy import require_acquirable
    from els_server.storage.local_state import TOWN_SCENES
    for identity,quest in row['quests'].items():
        target=row['targets'][identity]
        if int(identity) in TRANSCENDENCE_IDS:
            if (quest['m_iID']!=int(identity) or quest['m_eQuestType']!=9 or target!=1001
                or quest['QuestCondition']['m_iLevel']!=70 or quest['m_bRepeat'] or quest['m_bIsTimeEvent']
                or quest['Reward'].get('m_eChangeUnitClass',0) not in (0,1001)):
                raise ValueError('Transcendence source identity')
            continue
        if (quest['m_iID']!=int(identity) or quest['m_eQuestType']!=2
            or quest['QuestCondition']['m_iLevel']!={1:15,2:35,3:99}.get(CLASSES[target]['stage']) or quest['m_bRepeat'] or quest['m_bIsTimeEvent']
            or CLASSES[target]['stage'] not in (1,2,3) or CLASSES[PARENTS[target]]['stage']!=CLASSES[target]['stage']-1
            or quest['Reward'].get('m_eChangeUnitClass',0) not in (0,target)):
            raise ValueError('Job source transition')
    for sub in row['subquests'].values():
        if sub['m_eClearType'] not in (1,2,4,8,24,32):raise ValueError('Job objective source')
        if sub['m_eClearType']==1 and str(sub['m_ClearCondition']['m_eTalkNPCID']) not in row['npc_bindings']:
            raise ValueError('Job NPC binding missing')
    for binding in row['npc_bindings'].values():
        if not binding['houses'] or not binding['towns'] or any(TOWN_SCENES.get(int(t))!=scene for t,scene in binding['towns'].items()):
            raise ValueError('Job NPC source scene')
    if {r['template'] for r in row['reward_definitions']}!={109999,300645,110850,300646,300647,135867,135869,300648}:raise ValueError('Job reward set')
    for rule in row['reward_definitions']:
        item=data.item(rule['template']);require_acquirable(rule['template'])
        if (hashlib.sha256(item['record']).hexdigest()!=rule['record_sha256'] or item['item_type']!=7
            or item['metadata']!=rule['metadata'] or rule['metadata']!=2
            or rule['group']!=4 or rule['max_stack']!=1):raise ValueError('Job reward identity')
    return row

def require_base_class(character,quest):
    row=catalog();identity=str(quest['m_iID'])
    if identity not in row['quests']:return False
    if quest!=row['quests'][identity]:raise ValueError('Job source quest mismatch')
    from els_server.domain.character_rules import validate_career_state
    from els_server.domain.careers import PARENTS
    validate_career_state(character)
    if int(identity) in TRANSCENDENCE_IDS:
        from els_server.domain.character_rules import CLASSES
        if CLASSES[character['unit_class']]['stage']!=2 or character['transcendence'] or character['master']:
            raise ValueError('Transcendence requires an untranscended second class')
        return True
    if character['unit_class']!=PARENTS[row['targets'][identity]]:
        raise ValueError('Job requires current immediate parent class')
    from els_server.domain.character_rules import CLASSES
    if CLASSES[row['targets'][identity]]['stage']==3 and not character['transcendence']:
        raise ValueError('Third job requires existing transcendence')
    return True

def quest_transition(character,quest):
    if not require_base_class(character,quest):raise ValueError('Outside curated job transition scope')
    target=quest['Reward'].get('m_eChangeUnitClass',0)
    if not target or character['level']<quest['QuestCondition']['m_iLevel']:
        raise ValueError('Job terminal reward requirement')
    from els_server.domain.character_rules import validate_career_state
    if quest['m_iID'] in TRANSCENDENCE_IDS:
        if target!=1001:raise ValueError('Transcendence terminal enum')
        return validate_career_state(dict(character,transcendence=True,revision=character['revision']+1))
    return validate_career_state(dict(character,unit_class=target,revision=character['revision']+1))

def extend_town_dialogue(base):
    """Reuse FD receipts only for these exact source NPC subquests."""
    row=catalog()
    from els_server.domain.seal_quests import sequence
    quests={key:q for key,q in row['quests'].items()
            if any(row['subquests'][str(s)]['m_eClearType']==1 for s in sequence(q['m_vecSubQuest']))}
    subquests={str(s):row['subquests'][str(s)] for q in quests.values() for s in sequence(q['m_vecSubQuest'])}
    result=dict(base)
    for key,extra in [('quests',quests),('subquests',subquests),('npc_bindings',row['npc_bindings'])]:
        for identity,value in extra.items():
            if identity in base[key] and base[key][identity]!=value:raise ValueError('Job town source conflict')
        result[key]={**base[key],**extra}
    return result
