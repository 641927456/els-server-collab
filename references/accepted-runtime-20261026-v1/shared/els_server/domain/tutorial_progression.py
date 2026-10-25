"""Finite Lithia career target and original third-memory observation.

The saved stage>=FIRST_CLASS threshold is an explicit local compatibility
policy. Native completion flags and source enums do not recover retail server
career predicates. No career, location, inventory or completed quest is written.
"""
import functools,json

CAREER_SUBQUEST={'m_iID':28210,'m_eClearType':81,'m_bAutomaticDescription':0,
                 'm_ClearCondition':{'m_iUnitClassType':1,'m_iTranscendentalClassType':None}}
LOCAL_CAREER_POLICY='saved_valid_lithia_stage_at_least_first'
MEMORY3_TASKS={9338:28250,9342:28290}
SCRIPT_PINS={
    9338:('LITHIA_MEMORY3_1_STORY_DUMMY4.lua','526661db5f40a1643e97e6abf66dde1f3b574d2aa3ed934b90bc3c2f328396a6'),
    9342:('LITHIA_MEMORY3_2_END.lua','874f309542553d8cee2c72eede43e2251e8d78bd5e1e3a2d3af7b36c35fa1675'),
}

def career_target(sub):
    # JSON equality preserves bool/int distinctions in the source contract.
    if json.dumps(sub,sort_keys=True)!=json.dumps(CAREER_SUBQUEST,sort_keys=True):
        raise ValueError('Unsupported native tutorial career objective')
    return 1

def career_progress(sub,character):
    career_target(sub)
    from els_server.domain.character_rules import validate_career_state,CLASSES
    validate_career_state(character)
    return int(character['unit_type']==15 and CLASSES[character['unit_class']]['stage']>=1)

@functools.lru_cache(maxsize=1)
def memory3_sources():
    from els_server.game_data import client_data
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.seal_quests import quest_catalog,sequence
    data=client_data();routes=route_catalog();graph=routes.graph(35270)
    if SCRIPT_PINS.keys()!=MEMORY3_TASKS.keys():raise ValueError('Tutorial third-memory source set')
    def matching(value,npc):
        if isinstance(value,dict):
            if value.get('template')==npc:yield value
            for child in value.values():yield from matching(child,npc)
        elif isinstance(value,list):
            for child in value:yield from matching(child,npc)
    for npc,(script,digest) in SCRIPT_PINS.items():
        native=data.npc(npc);spawns=list(matching(graph,npc));subs=quest_catalog().objectives(MEMORY3_TASKS[npc])
        if (routes.manifest['source_sha256'].get(script)!=digest or native['script']!=script
            or native['class_id']!=103 or native['is_npc'] is not True or not spawns
            or not any(not row['active'] for row in spawns)
            or len(subs)!=1 or subs[0]['m_iID']!=MEMORY3_TASKS[npc] or subs[0]['m_eClearType']!=2
            or subs[0]['m_ClearCondition'].get('m_iKillNum')!=1
            or sequence(subs[0]['m_ClearCondition'].get('m_eKillNPCID',{}))!=(npc,)
            or 35270 not in sequence(subs[0]['m_ClearCondition'].get('m_eDungeonID',{}))):
            raise ValueError('Tutorial third-memory source identity')
    return frozenset(MEMORY3_TASKS)

def memory3_quest(dungeon,npc):
    return MEMORY3_TASKS[npc] if dungeon==35270 and npc in MEMORY3_TASKS and npc in memory3_sources() else None
