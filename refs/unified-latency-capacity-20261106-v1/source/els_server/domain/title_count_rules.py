"""Reviewed ordinary and bounded timed title objectives; current catalog and route IDs only.

Discovery, obtain counts and equipment effects are separate responsibilities.
Elwiki Titles (2026-10-19 snapshot) agrees with these admitted obtain predicates.
Legacy rank-era selector IDs are resolved by the existing current route catalog.
Only the explicit 240-second title is timed; kill/solo/resurrection/weekly and chance predicates stay closed.
"""
from dataclasses import dataclass
import functools,hashlib,json
from els_server.domain.titles import catalog

SOURCE_SHA256='483dc6d47c87f976e02ee345fb6091c813ae7b31f59a9465642675d39cfccceb'
MISSION_IDS=(90,100,130,140,150,180,210,240,30002,30003,30004,30007,30009,160,30006,340,30080,380,30120,410,30150,430,30170,614,30610,850,37860,870,37880,890,37900,910,37920,930,37940,960,37960,970,37970,1000,38000,1010,38010,1030,38030,1050,38050,1090,31090)
# Elwiki's global discovery notes require Velder40 and Hamel50. These
# explicit overrides do not alter lower equipment/display levels or old data.
LEVEL_OVERRIDES={380:40,430:50,30170:50}

@dataclass(frozen=True)
class Objective:
    submission:int
    target:int
    maps:tuple
    max_seconds:object=None

@dataclass(frozen=True)
class ClearRule:
    mission:int
    title:int
    level:int
    objectives:tuple
    prerequisites:tuple

@functools.lru_cache(maxsize=1)
def rules():
    from els_server.domain.dungeon_routes import route_catalog
    data=catalog();routes=route_catalog()
    selected={str(i):dict(mission=data['missions'][str(i)],
                         submissions=[data['submissions'][str(s)] for s in data['missions'][str(i)]['m_SubMission'].values() if s],
                         title=data['titles'].get(str(i))) for i in MISSION_IDS}
    digest=hashlib.sha256(json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=SOURCE_SHA256:raise ValueError('Reviewed title count source changed')
    result=[]
    for identity in MISSION_IDS:
        m=selected[str(identity)]['mission'];subs=selected[str(identity)]['submissions']
        if (not 1<=len(subs)<=8 or not m['m_bAccountMission'] or m['m_sPeriod'] or m['m_eConditionUnitType'] or m['m_eConditionUnitClass']):
            raise ValueError('Unsupported title count mission')
        objectives=[]
        for s in subs:
            condition=s['m_ClearCondition'];kind=s['m_eClearType']
            allowed={'m_iDungeonClearCount','m_vecDungeonList','m_bUpperDifficulty'}
            if kind==5:allowed.add('m_iDungeonClearTime')
            if kind not in (5,8) or set(condition)-allowed:raise ValueError('Unsupported title count predicate')
            if any(set(d)!={'m_eDungeonID','m_cDifficulty'} for d in condition['m_vecDungeonList'].values()):
                raise ValueError('Unreviewed dungeon mode predicate')
            maps=tuple(dict.fromkeys(routes.entry_identity(d['m_eDungeonID']) for d in condition['m_vecDungeonList'].values()))
            if not maps or any(not routes.supports(d) for d in maps):raise ValueError('Unadmitted title count route')
            target=condition['m_iDungeonClearCount']
            # Only this exact retained marker is corrected by the current Wiki:
            # Harpy Harpy discovery requires a Barren Sander clear, never zero.
            if identity==30610 and s['m_iID']==30610 and target==0:target=1
            if type(target) is not int or not 1<=target<=32767:raise ValueError('Title count bound')
            seconds=condition.get('m_iDungeonClearTime') if kind==5 else None
            if kind==5 and (identity!=160 or type(seconds) is not int or seconds!=240):
                raise ValueError('Unreviewed timed title')
            objectives.append(Objective(s['m_iID'],target,maps,seconds))
        prerequisites=tuple(p for p in m['m_iConditionClearMissionID'].values() if p)
        if any(p not in MISSION_IDS for p in prerequisites):raise ValueError('Unadmitted title discovery predecessor')
        t=selected[str(identity)]['title'];level=LEVEL_OVERRIDES.get(identity,m['m_iConditionLv'])
        if m['m_iTitleID']:
            if (not t or m['m_iTitleID']!=identity or not t['m_bAccountTitle'] or t['m_eUnitType'] or t['m_eUnitClass']
                or t.get('m_eTitleCanUseType',0) or t['m_iOpenLevel']>level):
                raise ValueError('Unsupported counted title definition')
        # m_iTitleID=0, rather than absence of an equal numeric title ID,
        # marks a discovery-only mission. It never creates ownership.
        result.append(ClearRule(identity,m['m_iTitleID'],level,tuple(objectives),prerequisites))
    return tuple(result)
