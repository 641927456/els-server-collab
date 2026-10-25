"""Only six original fifth-memory door deaths advance their source goal."""
import functools,json
SUBQUEST={'m_iID':28390,'m_eClearType':2,'m_bAutomaticDescription':0,
          'm_ClearCondition':{'m_iKillNum':6,'m_eDungeonID':{'0':None,'1':35290},'m_eKillNPCID':{'0':None,'1':9375}}}
SCRIPT='LITHIA_MEMORY5_DOOR.lua'
SCRIPT_SHA='63474b65d05fd6d78b1076be02bc254a4d8796de3a3a5cc0051ddc4699cd0b23'

@functools.lru_cache(maxsize=1)
def source():
    from els_server.game_data import client_data
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.seal_quests import quest_catalog
    routes=route_catalog();native=client_data().npc(9375)
    def matching(value):
        if isinstance(value,dict):
            if value.get('template')==9375:yield value
            for child in value.values():yield from matching(child)
        elif isinstance(value,list):
            for child in value:yield from matching(child)
    actors=list(matching(routes.graph(35290)))
    if (routes.manifest['source_sha256'].get(SCRIPT)!=SCRIPT_SHA or native['script']!=SCRIPT
        or native['class_id']!=103 or native['is_npc'] is not True
        or len(actors)!=6 or any(v['active'] or v.get('ally') or v.get('team')!=1 for v in actors)
        or sorted(v['source_index'] for v in actors)!=list(range(1,7))
        or json.dumps(quest_catalog().objectives(28390),sort_keys=True)!=json.dumps((SUBQUEST,),sort_keys=True)):
        raise ValueError('Tutorial fifth-memory door source identity')
    return True

def door_quest(dungeon,npc):
    return 28390 if dungeon==35290 and npc==9375 and source() else None

def door_increment(sub,event):
    return int(event.get('kind')=='kill' and event.get('tutorial_quest')==28390
               and door_quest(event.get('dungeon'),event.get('npc'))==28390
               and json.dumps(sub,sort_keys=True)==json.dumps(SUBQUEST,sort_keys=True))
