"""Current Ruben and Dark Forest clears; other condition families stay separate."""
import functools
from els_server.domain.titles import catalog

@functools.lru_cache(maxsize=1)
def rules():
    # Current source and Elwiki Titles/Ruben agree on discovery and clear maps.
    # Main type is not the subcondition type (Ann is main12, sub8).
    # CN 2023-08-02 update removes rating requirements; BWIKI's title page
    # also records one Dark Forest clear (see the frozen source audit).
    # Light in the Dark is level8 + one Dark Forest clear, without a rank gate.
    # Retain source IDs/type6 as evidence, not as a reason to require old rank.
    expected=((10,1,12,((10,(30000,)),)),(20,1,8,((20,(30000,)),(22,(30090,)))),(30,2,8,((30,(30000,30090)),)),(50,8,6,((50,(30070,)),)))
    from els_server.domain.dungeon_routes import route_catalog
    routes=route_catalog()
    data=catalog();result=[]
    for identity,level,main_type,subs in expected:
        m=data['missions'][str(identity)];t=data['titles'][str(identity)]
        if (m['m_iTitleID']!=identity or m['m_iConditionLv']!=level or m['m_eClearType']!=main_type
            or m['m_sPeriod'] or not m['m_bAccountMission'] or m['m_eConditionUnitType'] or m['m_eConditionUnitClass']
            or any(m['m_iConditionClearMissionID'].values()) or tuple(v for v in m['m_SubMission'].values() if v)!=tuple(s for s,maps in subs)
            or not t['m_bAccountTitle'] or t['m_iOpenLevel']!=level or t['m_eUnitType'] or t['m_eUnitClass'] or t.get('m_eTitleCanUseType',0)):
            raise ValueError('Ruben title source conditions changed')
        for sub,maps in subs:
            row=data['submissions'][str(sub)];c=row['m_ClearCondition']
            fields={'m_iDungeonClearCount','m_vecDungeonList'} if identity==50 else {'m_iDungeonClearCount','m_vecDungeonList','m_bUpperDifficulty'}
            if (row['m_eClearType']!=8 or set(c)!=fields
                or c['m_iDungeonClearCount']!=1 or identity!=50 and c['m_bUpperDifficulty']!=1
                or tuple(x['m_eDungeonID'] for x in c['m_vecDungeonList'].values())!=maps
                or any(set(x)!={'m_eDungeonID','m_cDifficulty'} or x['m_cDifficulty']!=(2 if identity==50 else 0 if identity in (10,20) else -1) for x in c['m_vecDungeonList'].values())):
                raise ValueError('Unsupported current title clear predicate')
        # Authenticated clears use admitted current route IDs (e.g. 30092),
        # while retained title tables name the family's old base ID (30090).
        # Only RouteCatalog's evidence-bound aliases qualify; removed maps do not.
        current=tuple((sub,tuple(dict.fromkeys(routes.entry_identity(m) for m in maps))) for sub,maps in subs)
        if any(not routes.supports(m) for sub,maps in current for m in maps):raise ValueError('Title map is not a current admitted route')
        result.append((identity,level,current))
    return tuple(result)
