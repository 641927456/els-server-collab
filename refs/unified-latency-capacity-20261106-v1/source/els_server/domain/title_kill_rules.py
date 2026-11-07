"""Current, source-pinned kill and mixed discovery missions; no old reward tables."""
from dataclasses import dataclass
import functools,hashlib,json
from els_server.domain.titles import catalog
SOURCE_SHA256='9106201b68d628b231952661d3abcd20e002a37e9f12505cd6668d6bfcc2442c'
MISSION_IDS=(40, 310, 320, 330, 350, 360, 370, 440, 450, 612, 613, 30050, 30060, 30070, 30090, 30100, 30110, 30180, 30190, 30590, 30600)
# Elwiki's current global discovery notes: Velder40/Hamel50. Preserve
# current native equipment levels; do not lower discovery to old raw levels.
LEVEL_OVERRIDES={320:40,30100:40,30110:40,440:50,30180:50}

@dataclass(frozen=True)
class Objective:
    submission:int
    target:int
    maps:tuple
    npcs:tuple
    kind:int
    max_seconds:object=None

@dataclass(frozen=True)
class Rule:
    mission:int
    title:int
    level:int
    objectives:tuple
    prerequisites:tuple

@functools.lru_cache(maxsize=1)
def rules():
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.game_data import client_data
    data=catalog();routes=route_catalog()
    selected={str(i):dict(mission=data['missions'][str(i)],submissions=[data['submissions'][str(s)] for s in data['missions'][str(i)]['m_SubMission'].values() if s],title=data['titles'].get(str(i))) for i in MISSION_IDS}
    digest=hashlib.sha256(json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=SOURCE_SHA256:raise ValueError('Reviewed title kill source changed')
    result=[]
    for i in MISSION_IDS:
        m=selected[str(i)]['mission'];t=selected[str(i)]['title'];subs=selected[str(i)]['submissions']
        if (not 1<=len(subs)<=8 or not m['m_bAccountMission'] or m['m_sPeriod'] or m['m_eConditionUnitType'] or m['m_eConditionUnitClass']):raise ValueError('Unsupported kill mission')
        objectives=[]
        for s in subs:
            kind=s['m_eClearType'];c=s['m_ClearCondition']
            if kind not in (2,8) or kind==8 and i!=612:raise ValueError('Unreviewed mixed mission')
            allowed={'m_iKillNum','m_vecDungeonList','m_eKillNPCID','m_bUpperDifficulty'} if kind==2 else {'m_iDungeonClearCount','m_vecDungeonList','m_bUpperDifficulty'}
            if set(c)-allowed:raise ValueError('Unreviewed kill predicate')
            if any(set(v)!={'m_eDungeonID','m_cDifficulty'} for v in c['m_vecDungeonList'].values()):raise ValueError('Unreviewed kill mode')
            maps=tuple(dict.fromkeys(routes.entry_identity(v['m_eDungeonID']) for v in c['m_vecDungeonList'].values()))
            if any(not routes.supports(v) for v in maps):raise ValueError('Unadmitted kill route')
            npcs=tuple(v for v in c.get('m_eKillNPCID',{}).values() if v)
            if kind==2 and (not npcs or any(type(v) is not int or v<=0 for v in npcs)):raise ValueError('Kill target identity')
            for npc in npcs:client_data().npc(npc)
            target=c['m_iKillNum' if kind==2 else 'm_iDungeonClearCount']
            if type(target) is not int or not 1<=target<=32767:raise ValueError('Kill count bound')
            objectives.append(Objective(s['m_iID'],target,maps,npcs,kind))
        prerequisites=tuple(v for v in m['m_iConditionClearMissionID'].values() if v)
        if any(v not in MISSION_IDS for v in prerequisites):raise ValueError('Unreviewed kill discovery')
        level=LEVEL_OVERRIDES.get(i,m['m_iConditionLv'])
        if m['m_iTitleID'] and (not t or m['m_iTitleID']!=i or not t['m_bAccountTitle'] or t['m_eUnitType'] or t['m_eUnitClass'] or t.get('m_eTitleCanUseType',0) or t['m_iOpenLevel']>level):raise ValueError('Unsupported kill title')
        result.append(Rule(i,m['m_iTitleID'],level,tuple(objectives),prerequisites))
    return tuple(result)
