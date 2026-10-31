"""Finite static scene retirements; never infer retirement from class103 alone.

Memory2's flowers, Altera Core's PD timer and the finite source list use pinned
DYING_END scripts and the CX2GUNPC factory. Original expiry DTO/map/writer code establishes the admitted
wire contract; the server only consumes an actual authenticated report. This
module has no persistence, quest or reward consumer.
"""
import copy
import math
import struct
import functools

# Code-first recovery disables only the new admission; keep this reader.
SCENE_ACTOR_RETIREMENTS_ENABLED=True
GRAPH_SHA='3dd4f08d0d5271cc9d83937fddface52ce0730378e0c1f28d13220437ab54821'
SCRIPT='LITHIA_MEMORY2_FLOWER.lua'
SCRIPT_SHA='8498135f543cd12f05694ca1db6d9a7e48519df3e3036472d8a6fa32aa6bca0b'
# Exact stage-wide native instance IDs, original source indexes and start points.
FLOWER_SOURCES={12:(1,10),13:(2,11),14:(3,12),15:(4,13),16:(5,14),17:(6,15)}

CORE_GRAPH_SHA='92fb9a602537def90092736f0403c60aefa3cee613a3947cbc67a4422f8b8b15'
CORE_SCRIPT_SHA='7d7d9b099e03007f3c9a4f90bad0beb3994b07fa0d216dc894423e10433b233f'
CORE_SOURCE=dict(template=343,source_index=1,points=[4],active=True,
    gage=True,ally=False,team=1,no_drop=False,right=False,boss=False,
    boss_lines=1,key_code=1,source_key_code=1,rate=100,offset=[0,0,0])


def core_room(run):
    return run is not None and (run.identity,run.stage,run.part)==(30302,2,0)


@functools.lru_cache(maxsize=1)
def finite_sources():
    from els_server.domain.scene_retirement_sources import RULES
    result={}
    for rule in RULES:
        result.setdefault((rule['dungeon'],rule['stage'],rule['part']),[]).append(rule)
    return result


def claimed_sources(run,npc):
    if run is None or npc.get('dynamic'):return ()
    return tuple(r for r in finite_sources().get((run.identity,run.stage,run.part),())
        if (r['source']['template'],r['source']['source_index'])==(npc.get('template'),npc.get('source_index')))


def finite_source_rule(run,npc):
    rows=[r for r in claimed_sources(run,npc)if all(npc.get(k)==v
        for k,v in r['source'].items()if k!='active')]
    if len(rows)!=1:return None
    r=rows[0];source=r['source']
    if (run.graph['source_sha256']!=r['graph_sha']or run.graph!=run.catalog.graph(run.identity,internal=True)
            or run.catalog.manifest['source_sha256'].get(r['script'])!=r['script_sha']
            or npc.get('start_point')not in source['points']
            or sum(n is npc for n in run.current['npcs'])!=1
            or sum(n.get('key')==npc.get('key')for n in run.current['npcs'])!=1):return None
    from els_server.game_data import client_data
    from els_server.domain.formal_npc_hp import initialized_maximum
    native=client_data().npc(source['template']);hp=initialized_maximum(run,source)
    if(native['class_id']!=103 or native['is_npc']is not True
            or native['script']!=r['native_script']or npc['hp']!=hp):return None
    return dict(source=source,hp=hp)


def scene_room(run):
    return run is not None and(core_room(run)or(run.identity,run.stage,run.part)==(35260,0,1)
        or(run.identity,run.stage,run.part)in finite_sources())


def retirement_shape(report,owners):
    return(report['flag']==255 and report['status']==1
        and report['source']==report['killer']==2**64-1 and report['extra_uid']==0
        and report['last_uid']in(0,2**64-4)and not report['contribution']and not report['counters']
        and set(report['readiness'])==set(owners)and all(v in(0,1)for v in report['readiness'].values()))


def core_source_rule(run,npc):
    """The original hidden PD timer, never a class-wide retirement rule."""
    if (npc.get('dynamic') or npc.get('key')!=0
            or run.graph['source_sha256']!=CORE_GRAPH_SHA
            or run.graph!=run.catalog.graph(run.identity)
            or run.catalog.manifest['source_sha256'].get('PD_Monster.lua')!=CORE_SCRIPT_SHA
            or any(npc.get(k)!=v for k,v in CORE_SOURCE.items() if k!='active')
            or npc.get('start_point')!=4):return None
    if run.graph['stages']['2']['parts']['0']['groups']!=[dict(index=-1,npcs=[CORE_SOURCE])]:return None
    actors=[n for n in run.current['npcs'] if n.get('key')==0
            or n.get('template')==343 and n.get('source_index')==1]
    if len(actors)!=1 or actors[0] is not npc:return None
    from els_server.game_data import client_data
    from els_server.domain.formal_npc_hp import initialized_maximum
    native=client_data().npc(343);hp=initialized_maximum(run,CORE_SOURCE)
    if (native['class_id']!=103 or native['is_npc'] is not True
            or native['script']!='PD_Monster.lua' or npc.get('hp')!=hp):return None
    return dict(source=CORE_SOURCE,hp=hp)


def source_rule(run,npc):
    """Pure identity check; no class-wide, zero-ID or filename-family alias."""
    if core_room(run):return core_source_rule(run,npc)
    if claimed_sources(run,npc):return finite_source_rule(run,npc)
    if (run is None or (run.identity,run.stage,run.part)!=(35260,0,1)
            or npc.get('dynamic') or npc.get('key') not in FLOWER_SOURCES):return None
    index,point=FLOWER_SOURCES[npc['key']]
    source=dict(template=9323,source_index=index,points=[point],active=True,
        gage=True,ally=False,team=1,no_drop=False,right=False,boss=False,
        boss_lines=1,key_code=-1,source_key_code=-1,rate=100,offset=[0,0,0])
    if (run.graph['source_sha256']!=GRAPH_SHA or run.graph!=run.catalog.graph(run.identity)
            or run.catalog.manifest['source_sha256'].get(SCRIPT)!=SCRIPT_SHA
            or any(npc.get(k)!=v for k,v in source.items() if k!='active')
            or npc.get('start_point')!=point):return None
    groups=run.graph['stages']['0']['parts']['1']['groups']
    declared=[(g['index'],n) for g in groups for n in g['npcs'] if n.get('source_index')==index]
    if declared!=[(-1,source)]:return None
    actors=[n for n in run.current['npcs'] if n.get('key')==npc['key']
            or n.get('template')==9323 and n.get('source_index')==index]
    if len(actors)!=1 or actors[0] is not npc:return None
    from els_server.game_data import client_data
    native=client_data().npc(9323)
    if native['class_id']!=103 or native['script']!=SCRIPT or native['is_npc'] is not True:return None
    from els_server.domain.formal_npc_hp import initialized_maximum
    hp=initialized_maximum(run,source)
    if npc.get('hp')!=hp:return None
    return dict(source=source,hp=hp)


def handle(s,event,report):
    """Acknowledge only an admitted original report, after encoding all replies."""
    if not SCENE_ACTOR_RETIREMENTS_ENABLED:return None
    run=s.dungeon_run
    core=core_room(run)
    if not scene_room(run):return None
    flower=(run.identity,run.stage,run.part)==(35260,0,1)
    keys=(0,) if core else FLOWER_SOURCES if flower else ()
    actors=[n for n in run.current['npcs'] if n.get('key')==report['index']]
    if len(actors)!=1:return [] if report['index'] in keys else None
    npc=actors[0]
    if npc.get('dynamic'):return None
    if report['index'] not in keys and not claimed_sources(run,npc):return None
    rule=source_rule(run,npc)
    if rule is None:return []
    owner=s.account.uid
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    from els_server.domain.summons import valid_sentry_death
    if (event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,)
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or not current_lease(s)
            or getattr(s,'reward_transaction',None) is not None
            or getattr(s,'reward_run_id',None)!=run.run_id
            or frozenset(getattr(s,'dungeon_participants',()))!=frozenset((owner,))
            or flower and s.account.character()['unit_type']!=15
            or not(valid_sentry_death(report,owner)if core or flower else retirement_shape(report,(owner,)))
            or any(not math.isfinite(v) or abs(v)>1e7 for v in report['xyz'])
            or report['hp_bits']!=struct.unpack('>I',struct.pack('>f',rule['hp']))[0]):return []
    key=npc['key']
    from els_server.domain.dungeon_lifecycle import death_ack,empty_reward_death_notice
    from els_server.protocol.protocol_codec import encode_event
    previous=run.defeated.get(key)
    if previous is not None:
        if previous!=event.payload or npc.get('active') is not False:return []
        replies=[death_ack()]
        for reply in replies:encode_event(reply)
        return replies
    if npc.get('active')is not rule['source']['active']:return []
    shadow,replies=prepare_retirement(s,event,npc)
    adopt_retirement(s,shadow,npc)
    return replies


def prepare_retirement(s,event,npc):
    run=s.dungeon_run;key=npc['key']
    shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run)
    shadow.dungeon_clock=copy.copy(s.dungeon_clock)
    shadow.dungeon_run.defeated={**run.defeated,key:bytes(event.payload)}
    shadow.defeated_npcs=shadow.dungeon_run.defeated
    from els_server.domain.dungeon_flow import periodic
    # Evaluate the existing source gate from the reported actor only; no
    # quest, reward, actor, timer or separate gate report is manufactured.
    from els_server.domain.dungeon_lifecycle import death_ack,empty_reward_death_notice
    from els_server.protocol.protocol_codec import encode_event
    replies=[death_ack(),empty_reward_death_notice(key,2**64-1)]+periodic(shadow)
    for reply in replies:encode_event(reply)
    return shadow,replies


def adopt_retirement(s,shadow,npc):
    run=s.dungeon_run
    for name in ('defeated','next','ready_at'):setattr(run,name,getattr(shadow.dungeon_run,name))
    npc['active']=False;s.defeated_npcs=run.defeated
    s.part_end_notified=shadow.part_end_notified
    s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started


def shared_retirement(dispatcher,room,s,event):
    """Consume the master's source-pinned retirement for loaded participants."""
    if not SCENE_ACTOR_RETIREMENTS_ENABLED or not scene_room(s.dungeon_run):return None
    if(s.dungeon_run.identity,s.dungeon_run.stage,s.dungeon_run.part)==(35260,0,1):return None
    from els_server.domain.dungeon_lifecycle import death_report,death_ack
    from els_server.domain.friends_spawns import _checked_static_generation
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.protocol.protocol_codec import encode_event
    import uuid
    try:report=death_report(event.payload)
    except ValueError:return []
    actor=next((n for n in s.dungeon_run.current['npcs']if n['key']==report['index']),None)
    if actor is None:return None
    if not core_room(s.dungeon_run)and not claimed_sources(s.dungeon_run,actor):return None
    if (s is not room.leader or room.phase not in ('active','part_end')
            or not 2<=len(room.members)<=6 or event.event_id!=0x202 or event.kind!=0xad
            or event.performers!=(0,) or event.uid!=2**64-1 or event.target_uid!=2**64-1
            or event.payload_mode!=0):return []
    try:_checked_static_generation(dispatcher,room)
    except ValueError:return []
    owners=frozenset(m.account.uid for m in room.members)
    if (not retirement_shape(report,owners)
            or any(not math.isfinite(v) or abs(v)>1e7 for v in report['xyz'])):return []
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    actors=[]
    for member in room.members:
        run=member.dungeon_run
        npc=next((n for n in run.current['npcs'] if n['key']==report['index']),None)
        rule=source_rule(run,npc) if npc is not None else None
        if (rule is None or not current_lease(member) or member.clear_notified
                or member.dungeon_failed or member.gate_stage_loading
                or getattr(member,'reward_transaction',None) is not None
                or member.reward_run_id!=str(uuid.uuid5(uuid.UUID(room.seed),'reward:'+str(member.account.uid)))
                or report['hp_bits']!=struct.unpack('>I',struct.pack('>f',rule['hp']))[0]):return []
        actors.append((member,npc))
    previous=[m.dungeon_run.defeated.get(report['index']) for m,_ in actors]
    if any(v is not None for v in previous):
        if not all(v==event.payload and n['active'] is False for v,(_,n) in zip(previous,actors)):return []
        reply=[death_ack()]
        for e in reply:encode_event(e)
        return reply
    if room.phase!='active' or any(n['active']is not source_rule(m.dungeon_run,n)['source']['active'] or m.part_end_notified for m,n in actors):return []
    prepared=[(m,n,*prepare_retirement(m,event,n)) for m,n in actors]
    deliveries=[(m,[e for e in replies if m is s or e.kind!=0xae]) for m,_,_,replies in prepared]
    response=next(events for m,events in deliveries if m is s)
    boxes=_prepared_boxes([(m,events) for m,events in deliveries if m is not s],response)
    for member,npc,shadow,_ in prepared:adopt_retirement(member,shadow,npc)
    for member,box in boxes.items():member.mailbox=box
    dispatcher.part_wait(room)
    return response
