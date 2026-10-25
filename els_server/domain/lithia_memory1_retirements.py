"""Source-bound native retirement of Memory1's opening quest controllers.

The client runs scenes and retires actors. This adapter only authenticates the
report, commits its existing quest event, and acknowledges the resolved actor.
It never grants combat EXP/loot or substitutes a timer for a source condition.
"""
from els_server.domain.formal_npc_hp import initialized_maximum
import copy
import struct

GRAPH_SHA='d71dba419ad369412c4e98a7f0d450f351c0ec533d9d0cb6abec4d50a2251e04'
# Original AddStartPos(1); native floor attachment can add its one-unit offset.
# This is a finite server validation envelope, not a new client movement rule.
POSITIONS={struct.pack('>6f',0,0,0,-2743.94,y,0) for y in (8230.0,8231.0)}
CONTROLLERS={9468:(1,500,False),9294:(0,1000,True)}


def handle(s,event,report):
    run=s.dungeon_run
    if run is None or run.identity!=35250 or report['flag']!=255:return None
    if (run.stage,run.part)!=(0,0):return later(s,event,report)
    if (event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,)
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or run.graph['source_sha256']!=GRAPH_SHA):
        return []
    owner=s.account.uid
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if (not current_lease(s) or getattr(s,'reward_transaction',None) is not None
            or getattr(s,'reward_run_id',None)!=run.run_id
            or frozenset(getattr(s,'dungeon_participants',(owner,)))!=frozenset((owner,))
            or s.account.character()['unit_type']!=15):
        return []
    if (report['status']!=1 or report['source']!=2**64-1 or report['killer']!=2**64-1
            or report['extra_uid']!=0 or report['last_uid'] not in (0,2**64-4)
            or report['contribution'] or report['counters'] or report['readiness']!={owner:0}
            or struct.pack('>6f',*report['xyz']) not in POSITIONS):
        return []
    matches=[]
    for npc in run.current['npcs']:
        expected=CONTROLLERS.get(npc['template'])
        if expected is None:continue
        key,legacy_hp,active=expected
        hp=initialized_maximum(run,npc)
        if (npc['key']==key and npc['start_point']==1 and npc['hp']==hp
                and npc['active'] is active and not npc.get('dynamic')
                and not npc.get('ally') and npc.get('team',1)==1
                and report['index'] in (0,key)
                and report['hp_bits']==struct.unpack('>I',struct.pack('>f',hp))[0]):
            matches.append(npc)
    if len(matches)!=1:return []
    npc=matches[0];key=npc['key']
    from els_server.domain.dungeon_lifecycle import death_ack,empty_reward_death_notice
    previous=run.defeated.get(key)
    if previous is not None:return [death_ack()] if previous==event.payload else []
    from els_server.domain.quest_flow import store
    state=store(s)
    base=run.run_id+':0:0:kill:'+str(key)
    level=s.account.character()['level']
    witness=dict(kind='kill',dungeon=35250,npc=npc['template'],level=level)
    if npc['template']==9468:
        from els_server.domain.tutorial_dialogue import inactive_quest
        if inactive_quest(35250,9468)!=28050:return []
        witness['tutorial_quest']=28050
    shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run)
    shadow.dungeon_run.defeated={**run.defeated,key:bytes(event.payload)}
    shadow.defeated_npcs=shadow.dungeon_run.defeated
    shadow.dungeon_clock=copy.copy(s.dungeon_clock)

    def validate(db):
        done={q for q, in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(owner,))}
        active={q for q, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(owner,))}
        if npc['template']==9468:
            valid=28040 in done and (28050 in active or 28050 in done)
        else:
            # 28060 itself requires this controller's retirement. Requiring
            # its reward first would recreate the original circular gate.
            valid=28050 in done and (28060 in active or 28060 in done)
        if not valid:raise ValueError('Memory1 retirement quest stage')

    def prepare(notices,replayed):
        from els_server.domain.dungeon_flow import periodic
        from els_server.protocol.protocol_codec import encode_event
        replies=[death_ack()]
        if not replayed:replies.append(empty_reward_death_notice(key,report['killer']))
        replies+=notices+periodic(shadow)
        for reply in replies:encode_event(reply)
        return replies

    # Quest receipt, objective update and encodable replies share one SQL
    # transaction. No account/snapshot call occurs inside that writer lock.
    try:replies=state.record(base,witness,event.payload,validate=validate,prepare=prepare)
    except ValueError as error:
        if str(error)=='Memory1 retirement quest stage':return []
        raise
    for name in ('defeated','next','ready_at'):setattr(run,name,getattr(shadow.dungeon_run,name))
    s.defeated_npcs=run.defeated;s.part_end_notified=shadow.part_end_notified
    s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
    seen=getattr(s,'_quest_seen_events',None)
    if seen is None:s._quest_seen_events=seen=set()
    seen.add(base)
    return replies


# Pinned original DYING_END controllers; later parts use only their exact BD
# instance IDs. No opening zero-ID alias or guessed position match is reused.
LATER_CONTROLLERS={(0, 1, 9295): {'stage': 0, 'part': 1, 'template': 9295, 'key': 8, 'hp': 1000, 'active': True, 'start_point': 8, 'script': 'LITHIA_MEMORY1_MINIGAME_MANAGER.lua', 'script_sha256': 'b48c3ffc6542259b7fa1890444b6dbb8a0eabd64892b0d62b569e9d2cb739632'}, (0, 1, 9469): {'stage': 0, 'part': 1, 'template': 9469, 'key': 9, 'hp': 500, 'active': False, 'start_point': 8, 'script': 'LITHIA_MEMORY1_QUEST_DUMMY2.lua', 'script_sha256': '5b5446f63ce28d91903d900dc00ad4b7f2815bf035be9e11e0e9e90b82ea7591'}, (0, 2, 9304): {'stage': 0, 'part': 2, 'template': 9304, 'key': 15, 'hp': 1000, 'active': False, 'start_point': 28, 'script': 'LITHIA_MEMORY1_SECRET_DOOR.lua', 'script_sha256': '4a30740cb98fd6e6aac54b6a87e7c699395ac3c243db6ec60229f579ac689cad'}, (0, 2, 9294): {'stage': 0, 'part': 2, 'template': 9294, 'key': 16, 'hp': 1000, 'active': True, 'start_point': 16, 'script': 'LITHIA_MEMORY1_STORY_DUMMY.lua', 'script_sha256': '3ea4519ac259c171d2e3590ec684eb4cfdf8a8718d53e4d05867f9a7396d0453'}, (0, 3, 9310): {'stage': 0, 'part': 3, 'template': 9310, 'key': 27, 'hp': 1000, 'active': True, 'start_point': 20, 'script': 'LITHIA_MEMORY1_STORY_DUMMY2.lua', 'script_sha256': '527d015d4f866de3eb0544452e243c24d709bd0a27aad28bc9c7e972e033b4f9'}, (0, 4, 9461): {'stage': 0, 'part': 4, 'template': 9461, 'key': 33, 'hp': 30000, 'active': True, 'start_point': 27, 'script': 'LITHIA_MEMORY1_START.lua', 'script_sha256': '6c58bb7c3eb4b107b7dda010f1fc5610f55a7cdcaaea7c17b7ca6df7eca9d469'}, (0, 4, 9462): {'stage': 0, 'part': 4, 'template': 9462, 'key': 34, 'hp': 30000, 'active': True, 'start_point': 27, 'script': 'LITHIA_MEMORY1_END.lua', 'script_sha256': '0dd8d9217f0a54fdade86fa1bb81cadeb7531ff90e5821fd5d9e513fa3901f3e'}, (0, 4, 9310): {'stage': 0, 'part': 4, 'template': 9310, 'key': 35, 'hp': 1000, 'active': True, 'start_point': 27, 'script': 'LITHIA_MEMORY1_STORY_DUMMY2.lua', 'script_sha256': '527d015d4f866de3eb0544452e243c24d709bd0a27aad28bc9c7e972e033b4f9'}, (1, 0, 9470): {'stage': 1, 'part': 0, 'template': 9470, 'key': 1, 'hp': 500, 'active': False, 'start_point': 2, 'script': 'LITHIA_MEMORY1_QUEST_DUMMY3.lua', 'script_sha256': '9a3adace1db852c5bb6c9feb1344c64700ff4a8750f953f65894cd5e5f6b5e03'}, (1, 0, 9310): {'stage': 1, 'part': 0, 'template': 9310, 'key': 2, 'hp': 1000, 'active': True, 'start_point': 2, 'script': 'LITHIA_MEMORY1_STORY_DUMMY2.lua', 'script_sha256': '527d015d4f866de3eb0544452e243c24d709bd0a27aad28bc9c7e972e033b4f9'}}
def later(s,event,report):
    """Consume an original later controller's retirement, never solve its scene."""
    run=s.dungeon_run
    npc=next((n for n in run.current['npcs'] if n['key']==report['index']),None)
    rule=None if npc is None else LATER_CONTROLLERS.get((run.stage,run.part,npc['template']))
    if rule is None:return []
    if (event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,)
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or run.graph['source_sha256']!=GRAPH_SHA):return []
    owner=s.account.uid
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if (not current_lease(s) or getattr(s,'reward_transaction',None) is not None
            or getattr(s,'reward_run_id',None)!=run.run_id
            or frozenset(getattr(s,'dungeon_participants',(owner,)))!=frozenset((owner,))
            or s.account.character()['unit_type']!=15):return []
    if (npc['key']!=rule['key'] or npc['start_point']!=rule['start_point']
            or npc['hp']!=initialized_maximum(run,npc) or npc['active'] is not rule['active']
            or npc.get('dynamic') or npc.get('ally') or npc.get('team',1)!=1
            or run.catalog.manifest['source_sha256'].get(rule['script'])!=rule['script_sha256']
            or report['status']!=1 or report['source']!=2**64-1 or report['killer']!=2**64-1
            or report['extra_uid']!=0 or report['last_uid'] not in (0,2**64-4)
            or report['contribution'] or report['counters'] or report['readiness']!={owner:0}
            or report['hp_bits']!=struct.unpack('>I',struct.pack('>f',initialized_maximum(run,npc)))[0]):return []
    key=npc['key']
    from els_server.domain.dungeon_lifecycle import death_ack,empty_reward_death_notice
    previous=run.defeated.get(key)
    if previous is not None:return [death_ack()] if previous==event.payload else []
    from els_server.domain.quest_flow import store
    state=store(s);base=run.run_id+':'+str(run.stage)+':'+str(run.part)+':kill:'+str(key)
    witness=dict(kind='kill',dungeon=35250,npc=npc['template'],level=s.account.character()['level'])
    from els_server.domain.tutorial_dialogue import inactive_quest
    identity=inactive_quest(35250,npc['template']) if not npc['active'] else None
    if identity is not None:witness['tutorial_quest']=identity
    shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run)
    shadow.dungeon_run.defeated={**run.defeated,key:bytes(event.payload)}
    shadow.defeated_npcs=shadow.dungeon_run.defeated;shadow.dungeon_clock=copy.copy(s.dungeon_clock)
    guard={}

    def validate(db):
        import json
        done={q for q, in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(owner,))}
        active={q:json.loads(raw) for q,raw in db.execute('SELECT quest,objectives FROM character_quests WHERE owner=?',(owner,))}
        def current(q):return q in done or q in active
        def satisfied(q):return q in done or active.get(q,{}).get(str(q),0)>=1
        task={9469:(28060,28070),9295:(28070,28080),9304:(28080,28090),9470:(28100,28110)}.get(npc['template'])
        if task is not None:valid=task[0] in done and current(task[1])
        elif (run.stage,run.part)==(0,2):valid=28080 in done and current(28090)
        elif (run.stage,run.part)==(0,3):valid=satisfied(28090)
        elif (run.stage,run.part)==(0,4):
            valid=28090 in done and current(28100)
            if npc['template'] in (9462,9310):
                valid=valid and satisfied(28100) and any(n['template']==9291 and n['key'] in run.defeated for n in run.current['npcs'])
        else:valid=28100 in done and current(28110)
        if not valid:raise ValueError('Memory1 later retirement quest stage')
        # Native scripts can retire the gate actor before the task dummy in
        # the same frame. Keep the stage pending until its real task event is
        # committed; do not fabricate that event or an earned reward.
        guard['barrier']=frozenset((15,)) if (run.stage,run.part)==(0,2) and 28090 not in done else frozenset((1,)) if (run.stage,run.part)==(1,0) and 28110 not in done else frozenset()

    def prepare(notices,replayed):
        from els_server.domain.dungeon_flow import periodic
        from els_server.protocol.protocol_codec import encode_event
        shadow.dungeon_run.memory1_quest_barrier=guard['barrier']
        replies=[death_ack()]
        if not replayed:replies.append(empty_reward_death_notice(key,report['killer']))
        replies+=notices+periodic(shadow)
        for reply in replies:encode_event(reply)
        return replies

    try:replies=state.record(base,witness,event.payload,validate=validate,prepare=prepare)
    except ValueError as error:
        if str(error)=='Memory1 later retirement quest stage':return []
        raise
    for name in ('defeated','next','ready_at','memory1_quest_barrier'):setattr(run,name,getattr(shadow.dungeon_run,name))
    s.defeated_npcs=run.defeated;s.part_end_notified=shadow.part_end_notified
    s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
    seen=getattr(s,'_quest_seen_events',None)
    if seen is None:s._quest_seen_events=seen=set()
    seen.add(base)
    return replies

