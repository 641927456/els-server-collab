"""Source-bound native retirement of Memory1's opening quest controllers.

The client runs scenes and retires actors. This adapter only authenticates the
report, commits its existing quest event, and acknowledges the resolved actor.
It never grants combat EXP/loot or substitutes a timer for a source condition.
"""
import copy
import struct

GRAPH_SHA='d71dba419ad369412c4e98a7f0d450f351c0ec533d9d0cb6abec4d50a2251e04'
# Original AddStartPos(1); native floor attachment can add its one-unit offset.
# This is a finite server validation envelope, not a new client movement rule.
POSITIONS={struct.pack('>6f',0,0,0,-2743.94,y,0) for y in (8230.0,8231.0)}
CONTROLLERS={9468:(1,500,False),9294:(0,1000,True)}


def handle(s,event,report):
    run=s.dungeon_run
    if run is None or run.identity!=35250 or run.stage!=0 or run.part!=0 or report['flag']!=255:
        return None
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
        key,hp,active=expected
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
