"""Pinned native quest definitions and server-side seal-task conditions."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

# Original FE8460 returns Error outside this legacy RANK_TYPE enum. The
# internal event contract uses these values; modern PVE_RANK needs a verified
# conversion before it can supply quest ranks. Local clear rules use this
# legacy enum directly under the user's explicit local-design authorization.
# CN official current quest guide: at most50 accepted quests per character.
# https://els.ztgame.com/game/m_000-1635-002f7-244910.shtml
ACTIVE_QUEST_LIMIT=50

DUNGEON_RANKS={1:'F',2:'E',3:'D',4:'C',5:'B',6:'A',7:'S',8:'SS'}

def sequence(row):
    return tuple(v for k,v in sorted(row.items(),key=lambda p:int(p[0])) if str(k)!='0' and v is not None)

@functools.lru_cache(maxsize=1)
def seal_catalog():
    raw=(PROJECT_ROOT/'els_server/data/seal_quests.json').read_bytes()
    manifest=json.loads((PROJECT_ROOT/'els_server/data/seal_quests.manifest.json').read_text(encoding='utf8'))
    row=json.loads(raw);data=client_data()
    if hashlib.sha256(raw).hexdigest()!=manifest['sha256'] or row['client_sha256']!=CLIENT_SHA or row['catalog_sha256']!=data.manifest['catalog_sha256']:raise ValueError('Seal quest catalog identity')
    for item in row['reward_definitions']:
        if hashlib.sha256(data.item(item['template'])['record']).hexdigest()!=item['record_sha256'] or item['native']!={'ok':1,'consumed':304}:raise ValueError('Quest reward evidence')
    return row

class QuestCatalog:
    def __init__(self):
        row=seal_catalog();self.quests={int(k):v for k,v in row['quests'].items()};self.subquests={int(k):v for k,v in row['subquests'].items()}
        # Independent region catalog owns map admission policy; the same quest
        # transaction engine can consume its native task definitions.
        from els_server.domain.region_quests import region_catalog
        extension=region_catalog()
        for dest,extra in ((self.quests,extension.quest_definitions()),(self.subquests,extension.subquest_definitions())):
            for k,v in extra.items():
                if k in dest and dest[k]!=v:raise ValueError('Conflicting quest extension')
                dest[k]=v
        from els_server.domain.story_quests import story_catalog
        extension=story_catalog()
        for dest,key in ((self.quests,'quests'),(self.subquests,'subquests')):
            for raw_id,v in extension[key].items():
                k=int(raw_id)
                if k in dest and dest[k]!=v:raise ValueError('Conflicting story quest extension')
                dest[k]=v
        from els_server.domain.artifact_progression import catalog as artifact_catalog
        artifact=artifact_catalog()
        for dest,name in ((self.quests,'quests'),(self.subquests,'subquests')):
            for key,value in artifact[name].items():
                key=int(key)
                if key in dest and dest[key]!=value:raise ValueError('Conflicting Artifact quest')
                dest[key]=value
        from els_server.domain.town_dialogue import catalog as town_dialogue_catalog
        dialogue=town_dialogue_catalog()
        for dest,key in ((self.quests,'quests'),(self.subquests,'subquests')):
            for raw_id,value in dialogue[key].items():
                identity=int(raw_id)
                if identity in dest and dest[identity]!=value:raise ValueError('Conflicting town dialogue quest')
                dest[identity]=value
        from els_server.domain.job_quests import catalog as job_catalog
        jobs=job_catalog()
        for dest,key in ((self.quests,'quests'),(self.subquests,'subquests')):
            for raw_id,value in jobs[key].items():
                identity=int(raw_id)
                if identity in dest and dest[identity]!=value:raise ValueError('Conflicting first-job quest')
                dest[identity]=value
        from els_server.domain.erp_support_quest import catalog as erp_source_catalog
        extension=erp_source_catalog()
        for dest,key in ((self.quests,'quests'),(self.subquests,'subquests')):
            for raw_id,value in extension[key].items():
                identity=int(raw_id)
                if identity in dest and dest[identity]!=value:raise ValueError('Conflicting ERP support quest')
                dest[identity]=value
        from els_server.domain.account_epic_quests import catalog as account_epic_catalog
        account_epic=account_epic_catalog()
        for dest,key in ((self.quests,'quests'),(self.subquests,'subquests')):
            for raw_id,value in account_epic[key].items():
                identity=int(raw_id)
                if identity in dest and dest[identity]!=value:raise ValueError('Conflicting finite account Epic source')
                dest[identity]=value
        for q in self.quests.values():
            if q['m_bRepeat'] or q['m_bIsTimeEvent']:raise ValueError('Unsupported quest schedule')
            from els_server.domain.quest_selection import options
            options(q)
            if len(q['m_vecSubQuest_Group'])!=1:
                from els_server.domain.mainline_subquest_groups import validate
                if not validate(q):raise ValueError('Unsupported alternative objective group')
            for i in sequence(q['m_vecSubQuest']):
                if i not in self.subquests:raise ValueError('Missing native subquest')

    def quest(self,identity):
        if type(identity) is not int or identity not in self.quests:raise ValueError('Unsupported quest identity')
        return self.quests[identity]

    def objectives(self,identity):
        return tuple(self.subquests[i] for i in sequence(self.quest(identity)['m_vecSubQuest']))

@functools.lru_cache(maxsize=1)
def quest_catalog():return QuestCatalog()

# Finite new Rigomor IDs reuse legacy UC_NONE filtering and exact sets.
_RIGOMOR_COLLECTION_QUESTS=frozenset((22730,22740,22750,22770,22780,22790,22810,22820,22830))
def _require_rigomor_collection_class(character,quest):
    if quest.get('m_iID') not in _RIGOMOR_COLLECTION_QUESTS:return
    values=quest['QuestCondition']['m_eUnitClass']
    classes={v for k,v in values.items() if str(k)!='0' and v is not None and v!=0}
    if not classes:return
    if any(type(v) is not int or v<1 for v in classes):
        raise ValueError('Rigomor story class source')
    if character['unit_class'] not in classes:
        raise ValueError('Quest career requirement')
def require_eligible(character,quest,completed,items,*,location=('town',20000)):
    _require_rigomor_collection_class(character,quest)
    from els_server.domain.character_rules import CLASSES
    from els_server.domain.careers import PARENTS
    from els_server.domain.skill_unlocks import unsealed_skills
    from els_server.domain.job_quests import require_base_class
    require_base_class(character,quest)
    c=quest['QuestCondition'];level=character['level'];cls=character['unit_class']
    if level<c['m_iLevel'] or c['m_iLimitLevel']>=0 and level>c['m_iLimitLevel']:raise ValueError('Quest level requirement')
    types=sequence(c['m_eUnitType'])
    if 0 not in types and character['unit_type'] not in types:raise ValueError('Quest character requirement')
    lineage={cls};parent=cls
    while PARENTS.get(parent) is not None and PARENTS[parent] not in lineage:
        parent=PARENTS[parent];lineage.add(parent)
    classes=sequence(c['m_eUnitClass'])
    # Enum QUEST_REWARD_TRAN_CLASS: 1001=transcendence, 1002=Master.
    if not any(i==0 or i in lineage or i==1001 and character['transcendence'] or i==1002 and character['master'] for i in classes):raise ValueError('Quest career requirement')
    stages=sequence(c.get('m_eUnitClassType',{}))
    if stages and CLASSES[cls]['stage'] not in stages:raise ValueError('Quest class stage requirement')
    if any(i and i not in completed for i in sequence(c['m_vecBeforeQuestID'])):raise ValueError('Quest predecessor requirement')
    if c.get('m_iNotBeforeQuestID',0) in completed:raise ValueError('Quest exclusion requirement')
    seals=set(unsealed_skills(character))
    if any(i in seals for i in sequence(quest.get('HIDE_QUEST_SKILL',{}))):raise ValueError('Quest skill already unsealed')
    show=sequence(quest.get('SHOW_QUEST_SKILL',{}))
    if show and not any(i in seals for i in show):raise ValueError('Quest previous skill requirement')
    if c.get('m_iConditionItemID') and sum(i['count'] for i in items if i['template']==c['m_iConditionItemID'])<c['m_iConditionItemNum']:raise ValueError('Quest prerequisite item')
    places={kind:sequence(c.get(key,{})) for kind,key in (('town','m_iEnableVillage'),('field','m_iEnableField'),('dungeon','m_iEnableDungeon'))}
    if any(places.values()):
        allowed=places[location[0]]
        if 0 not in allowed and location[1] not in allowed:raise ValueError('Quest location requirement')

def target(sub):
    c=sub['m_ClearCondition'];kind=sub['m_eClearType']
    if kind==1:
        from els_server.domain.town_dialogue import catalog as town_catalog,target as town_target
        if str(sub.get('m_iID')) in town_catalog()['subquests']:return town_target(sub)
        from els_server.domain.tutorial_dialogue import target as dialogue_target
        return dialogue_target(sub)
    if kind==27:
        from els_server.domain.mainline_find_npc import supported,target as find_target
        if supported(sub):return find_target(sub)
    if kind in (27,80):
        from els_server.domain.tutorial_memory8_finale import target as finale_target
        return finale_target(sub)
    if kind==81:
        from els_server.domain.tutorial_progression import career_target
        return career_target(sub)
    if kind==31:
        level=c.get('m_iCharLevel')
        if type(level) is not int or not 1<=level<=99:raise ValueError('Unsupported native character level objective')
        # Native D01640/D019F0 use a completion flag, not the character level
        # as a progress counter. Storage derives that flag from saved level.
        return 1
    if kind in (24,26,46):return 1
    n=c.get('m_iClearCount') if kind==110 else c.get('m_iCollectionItemNum') if kind in (3,4) else c.get('m_iKillNum') if kind==2 else c.get('m_iDungeonClearCount')
    if type(n) is not int or not 1<=n<=65535 or kind not in (2,3,4,6,8,32,110):raise ValueError('Unsupported native objective')
    return n

def appropriate_level_range(definition):
    """Current native AdequateLevel marker, inclusive (36DC222).

    105B761 decodes m_SuitableLevelFixValue for Dungeon+120; 105B8E0
    supplies 5 when absent. Explicit zero is meaningful. This is separate
    from candidate admission and recommendation text color. See the native
    replay in analysis/seal-quests-20261015/native-adequate-level-proof.json.
    """
    return (definition['m_MinLevel']-definition.get('m_SuitableLevelFixValue',5),
            definition['m_MaxLevel']+2)


def objective_increment(sub,event,proof):
    """Only server accepted deaths/clears reach here, never client quest counts."""
    kind=sub['m_eClearType'];c=sub['m_ClearCondition'];dungeon=event['dungeon']
    if 'tutorial_quest' in event:
        from els_server.domain.tutorial_dialogue import inactive_increment
        return inactive_increment(sub,event)
    ids=sequence(c.get('m_eDungeonID',{}))
    if ids and dungeon not in ids:
        # Some normal tasks retain an old difficulty ID while admission uses
        # the single current icon. Reuse only the explicit current-family
        # aliases; unrelated, removed and unused maps do not become matches.
        from els_server.domain.dungeon_routes import route_catalog
        resolve=route_catalog().entry_identity
        if not any(resolve(i)==resolve(dungeon) for i in ids):return 0
    if kind==27:
        from els_server.domain.mainline_find_npc import supported,increment as find_increment_native
        if supported(sub):return find_increment_native(sub,event)
        from els_server.domain.tutorial_memory8_finale import find_increment
        return find_increment(sub,event)
    if kind==24:return int(event['kind']=='visit_town' and event.get('town') in sequence(c['m_eVillageID']))
    if kind==26:return int(event['kind']=='visit_dungeon')
    if kind in (2,4):
        if event['kind']!='kill':return 0
        npcs=sequence(c.get('m_eKillNPCID',{}))
        if npcs and event['npc'] not in npcs:return 0
        if kind==4:
            rate=c['m_fQuestItemDropRate']
            roll=int.from_bytes(hashlib.sha256(proof+str(sub['m_iID']).encode()).digest()[:8],'big')%1000000
            if not 0<=rate<=100:raise ValueError('Native quest drop rate bound')
            return int(roll<round(rate*10000))
        return 1
    if event['kind']!='clear':return 0
    if kind==8:return 1
    if kind==6:
        # A presentation rank is not authoritative. Unavailable metrics leave
        # this objective pending rather than giving free S/SS clears.
        rank=event.get('rank')
        return int(type(rank) is int and rank in DUNGEON_RANKS and rank>=c['m_eDungeonRank'])
    if kind==32:
        excluded=sequence(c.get('m_eExceptionDungeonID',{}))
        if dungeon in excluded:return 0
        # Align task level range with the current client's AdequateLevel
        # marker. Dungeon admission still belongs to the dungeon controller.
        low,high=appropriate_level_range(client_data().dungeon(dungeon))
        return int(low<=event['level']<=high)
    return 0
