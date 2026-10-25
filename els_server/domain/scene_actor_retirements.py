"""Finite static scene retirements; never infer retirement from class103 alone.

Memory2's six original flower sources use the pinned DYING_END script and
CX2GUNPC factory. Original expiry DTO/map/writer code establishes the admitted
wire contract; the server only consumes an actual authenticated report. This
module has no persistence, quest or reward consumer.
"""
import copy
import math
import struct

# Code-first recovery disables only the new admission; keep this reader.
SCENE_ACTOR_RETIREMENTS_ENABLED=True
GRAPH_SHA='3dd4f08d0d5271cc9d83937fddface52ce0730378e0c1f28d13220437ab54821'
SCRIPT='LITHIA_MEMORY2_FLOWER.lua'
SCRIPT_SHA='8498135f543cd12f05694ca1db6d9a7e48519df3e3036472d8a6fa32aa6bca0b'
# Exact stage-wide native instance IDs, original source indexes and start points.
FLOWER_SOURCES={12:(1,10),13:(2,11),14:(3,12),15:(4,13),16:(5,14),17:(6,15)}


def source_rule(run,npc):
    """Pure identity check; no class-wide, zero-ID or filename-family alias."""
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
    if run is None or (run.identity,run.stage,run.part)!=(35260,0,1):return None
    actors=[n for n in run.current['npcs'] if n.get('key')==report['index']]
    if len(actors)!=1:return [] if report['index'] in FLOWER_SOURCES else None
    npc=actors[0]
    if npc.get('dynamic'):return None
    if report['index'] not in FLOWER_SOURCES:return None
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
            or s.account.character()['unit_type']!=15
            or not valid_sentry_death(report,owner)
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
    if npc.get('active') is not True:return []
    shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run)
    shadow.dungeon_clock=copy.copy(s.dungeon_clock)
    shadow.dungeon_run.defeated={**run.defeated,key:bytes(event.payload)}
    shadow.defeated_npcs=shadow.dungeon_run.defeated
    from els_server.domain.dungeon_flow import periodic
    # The original source gate still requires 9324. Never manufacture its
    # report, quest progress, actors, wave, movement, timing or clear result.
    replies=[death_ack(),empty_reward_death_notice(key,report['killer'])]+periodic(shadow)
    for reply in replies:encode_event(reply)
    for name in ('defeated','next','ready_at'):setattr(run,name,getattr(shadow.dungeon_run,name))
    npc['active']=False;s.defeated_npcs=run.defeated
    s.part_end_notified=shadow.part_end_notified
    s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
    return replies
