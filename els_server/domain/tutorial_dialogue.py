"""Finite Lithia tutorial interaction, supported by original NPC and FD evidence."""
import functools
QUEST=28030
DIALOGUE_PREDECESSORS={28030:28020,28120:28110,28130:28120,28210:28200,28300:28290,28310:28300,28360:28350,28430:28420,28440:28430,28530:28520,28620:28610,28630:28620,28640:28630,28650:28640,28660:28650,28670:28660,28680:28670,28690:28680}
NPC=10394
TOWN=20014
SCENE=1106
HOUSE=40280
SUBQUEST={'m_iID':28030,'m_eClearType':1,'m_bAutomaticDescription':0,'m_ClearCondition':{'m_eTalkNPCID':10394}}
# Original current-part quest dummies/door have ISACTIVE=false and explicitly
# send their DYING packet. Only their exact source tasks may consume that death.
INACTIVE_TASKS={9468:28050,9469:28070,9304:28090,9470:28110}
SCRIPT_PINS={
    9468:('LITHIA_MEMORY1_QUEST_DUMMY1.lua','18de3bbad5dd2feea4a9597a338281f834534257282d16abd7698b55ee0d2164'),
    9469:('LITHIA_MEMORY1_QUEST_DUMMY2.lua','5b5446f63ce28d91903d900dc00ad4b7f2815bf035be9e11e0e9e90b82ea7591'),
    9304:('LITHIA_MEMORY1_SECRET_DOOR.lua','4a30740cb98fd6e6aac54b6a87e7c699395ac3c243db6ec60229f579ac689cad'),
    9470:('LITHIA_MEMORY1_QUEST_DUMMY3.lua','9a3adace1db852c5bb6c9feb1344c64700ff4a8750f953f65894cd5e5f6b5e03'),
}

@functools.lru_cache(maxsize=1)
def inactive_sources():
    from els_server.game_data import client_data
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.seal_quests import quest_catalog,sequence
    data=client_data();routes=route_catalog();graph=routes.graph(35250)
    def matching(value,npc):
        if isinstance(value,dict):
            if value.get('template')==npc:yield value
            for child in value.values():yield from matching(child,npc)
        elif isinstance(value,list):
            for child in value:yield from matching(child,npc)
    for npc,(script,checksum) in SCRIPT_PINS.items():
        native=data.npc(npc);sub=quest_catalog().objectives(INACTIVE_TASKS[npc])
        spawn=list(matching(graph,npc))
        if (routes.manifest['source_sha256'].get(script)!=checksum or native['script']!=script
            or native['class_id']!=103 or native['is_npc'] is not True or not spawn or any(v['active'] for v in spawn)
            or len(sub)!=1 or sub[0]['m_iID']!=INACTIVE_TASKS[npc] or sub[0]['m_eClearType']!=2
            or sub[0]['m_ClearCondition'].get('m_iKillNum')!=1
            or sequence(sub[0]['m_ClearCondition'].get('m_eKillNPCID',{}))!=(npc,)):
            raise ValueError('Tutorial scripted actor source identity')
    return frozenset(INACTIVE_TASKS)

def target(sub):
    if sub!=SUBQUEST:raise ValueError('Unsupported NPC dialogue objective')
    return 1

def inactive_quest(dungeon,npc):
    if dungeon in (35320,35321,35322):
        from els_server.domain.tutorial_memory8_finale import inactive_quest as finale_quest
        return finale_quest(dungeon,npc)
    if dungeon==35290:
        from els_server.domain.tutorial_memory_continuation import door_quest
        return door_quest(dungeon,npc)
    if dungeon==35270:
        from els_server.domain.tutorial_progression import memory3_quest
        return memory3_quest(dungeon,npc)
    return INACTIVE_TASKS[npc] if dungeon==35250 and npc in INACTIVE_TASKS and npc in inactive_sources() else None

def inactive_increment(sub,event):
    if event.get('dungeon')==35290:
        from els_server.domain.tutorial_memory_continuation import door_increment
        return door_increment(sub,event)
    expected=inactive_quest(event.get('dungeon'),event.get('npc'))
    condition=sub['m_ClearCondition']
    # 9470's own DYING report never arrives inside the stage1/part0 scene
    # (trace 20261024-130855: the client unloads that actor with the scene),
    # so the source-pinned part condition - retiring 9310 - carries the
    # dummy's task event. Only this exact task/dummy pair may consume it.
    retired=(event.get('kind')=='retire' and expected==28110 and event.get('retired_by')==9310)
    return int(expected is not None and event.get('tutorial_quest')==expected
               and (event.get('kind')=='kill' or retired)
               and sub['m_iID']==expected and sub['m_eClearType']==2 and condition.get('m_iKillNum')==1
               and event['npc'] in condition.get('m_eKillNPCID',{}).values()
               and event.get('dungeon') in condition.get('m_eDungeonID',{}).values())

def handle(s,event,sequence):
    from els_server.protocol import tutorial_dialogue_messages as wire
    from els_server.protocol.quest_messages import QUEST_REQUIREMENTS_NOT_MET,QUEST_REWARD_UNAVAILABLE
    from els_server.storage.local_state import TOWN_SCENES
    if event.event_id!=0x202 or event.kind!=0xfd:return None
    try:npc=wire.request(event.payload)
    except ValueError:return [wire.acknowledgement(result=QUEST_REWARD_UNAVAILABLE)]
    # Preserve other NPCs' existing dispatcher paths. This is not a generic
    # NPC service or a way to mark arbitrary dialogue objectives complete.
    if npc!=NPC:return None
    if (TOWN_SCENES.get(TOWN)!=SCENE or s.role!='game' or s.phase!='town_ready' or s.active_map!=TOWN
        or s.account.get_location()['map']!=TOWN or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers!=(0,) or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff
        or event.payload_mode!=0):return [wire.acknowledgement(result=QUEST_REQUIREMENTS_NOT_MET)]
    from els_server.storage.tutorial_dialogue import interact
    from els_server.domain.quest_flow import store
    operation=s.shop_session_id+':npc-talk:'+str(s.account.uid)+':'+str(sequence)
    try:return interact(store(s),npc,operation)
    except ValueError:return [wire.acknowledgement(result=QUEST_REQUIREMENTS_NOT_MET)]
