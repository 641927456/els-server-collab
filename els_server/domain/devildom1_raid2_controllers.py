"""Finite source-controller retirements for Devildom raid 2 (34140).

Every part of this graph names a class103 script marker as its kind-3
condition: stage 0 requires template 6851, stage 1 requires 6853 and stage 2
requires 6855. Those markers are declared ``active=False``/``no_drop=True`` and
carry the original ``2018_RAID_BOSS2_PHASE*`` scripts, so the client owns the
scene and retires each one with a native 255 expiry (source=killer=2**64-1, one
zero readiness entry, empty contribution/counters). The server never invents
that report: it only authenticates the one the client already sent, so the
existing ``condition_ready`` kind 3 can observe the part as over.

No quest, gate, timer, loot, EXP or synthetic death is added. The admitted rows
are the nine declared static markers of this graph and nothing else; zero is
never an alias for the boss key that shares this population.

This is a shared raid, so unlike the character-specific story controllers there
is no ``unit_type`` gate: the markers are declared by the route, and the same
map's ordinary death path admits every character. Gating on the one observed
character would only strand the others on the same empty dialogue.
"""
import copy
import math
import struct

# Code-first recovery disables only the new admission; keep this reader.
DEVILDOM1_RAID2_CONTROLLERS_ENABLED=True
GRAPH_SHA='e19bb64e80a3788b985b54910c9ad4d29004f29234c68db933bdb395d83930a3'
MAX_UID=2**64-1
# Exact (stage, current npc key) -> (template, source index, start point, script sha).
# The graph is pinned by GRAPH_SHA, so key/template pairing is a fixed fact of
# the admitted resource; every row is re-verified against the declared group.
CONTROLLERS={
 (0,5):(6850,6,89,'f0087de7e426caf0db4ddbe2c8cf9736a5db8d2c849db0403123b1d8cd49d8b2'),
 (0,6):(6856,7,89,'77b6dd224fdbbecead56d842ba552c6286da8c35a637370ed2d72ece8bb2bd2f'),
 (0,7):(6851,8,89,'b4e59bbf3796155a09ea56fd3c2ee92e1563cfdedf8347ad1129231685c5b7c2'),
 (0,8):(6857,9,89,'edbb755ab7e092219b64040c0372efa652dc182e2edf7cbc4605f4dd68d33a84'),
 (1,1):(6852,2,1,'1f1d8d1e70912534a6a373ab65e0e7307891458e4ded3402e024441aa0033182'),
 (1,2):(6853,3,1,'8f4576beedac637a25d0c9b0f505d75c5cd282c5b5bcd62d6e5b732a2e311876'),
 (2,1):(6854,2,1,'fff08f20ab413254c14ec96e443a6eda10749b0e020346f3c1f52fa92bfedc08'),
 (2,2):(6855,3,1,'216d41de584e8593326e48ccb015c449b1fa692487856fa6cc6060a07e89ad90'),
 (2,3):(6849,4,1,'115a691670abb4b0b54b9f00a8800af01057264183ce9815adc741d726b70802'),
}
SCRIPTS={6850:'2018_RAID_BOSS2_PHASE1_START.lua',6856:'2018_RAID_BOSS2_PHASE1_START_2.lua',
         6851:'2018_RAID_BOSS2_PHASE1_END.lua',6857:'2018_RAID_BOSS2_PHASE1_END_2.lua',
         6852:'2018_RAID_BOSS2_PHASE2_START.lua',6853:'2018_RAID_BOSS2_PHASE2_END.lua',
         6854:'2018_RAID_BOSS2_PHASE3_START.lua',6855:'2018_RAID_BOSS2_PHASE3_END.lua',
         6849:'2018_RAID_BOSS2_PHASE3_SUMMONNER.lua'}


def source_rule(run,npc):
    """Pure identity check for the current declared marker; no family alias."""
    spec=CONTROLLERS.get((run.stage,npc.get('key')))
    if spec is None or npc.get('dynamic'):return None
    template,index,point,script_sha=spec
    source=dict(template=template,source_index=index,points=[point],active=False,
        gage=False,ally=False,team=1,no_drop=True,right=False,boss=False,
        boss_lines=1,key_code=-1,source_key_code=-1,rate=100,offset=[0,0,0])
    if (run.graph['source_sha256']!=GRAPH_SHA or run.graph!=run.catalog.graph(run.identity)
            or run.catalog.manifest['source_sha256'].get(SCRIPTS[template])!=script_sha
            or any(npc.get(k)!=v for k,v in source.items() if k!='active')
            or npc.get('start_point')!=point):return None
    groups=run.graph['stages'][str(run.stage)]['parts'][str(run.part)]['groups']
    declared=[(g['index'],n) for g in groups for n in g['npcs'] if n.get('source_index')==index]
    if declared!=[(-1,source)]:return None
    actors=[n for n in run.current['npcs'] if n.get('key')==npc['key']
            or n.get('template')==template and n.get('source_index')==index]
    if len(actors)!=1 or actors[0] is not npc:return None
    from els_server.game_data import client_data
    native=client_data().npc(template)
    if native['class_id']!=103 or native['script']!=SCRIPTS[template] or native['is_npc'] is not True:return None
    from els_server.domain.formal_npc_hp import initialized_maximum
    hp=initialized_maximum(run,source)
    if npc.get('hp')!=hp:return None
    return dict(source=source,hp=hp)


def handle(s,event,report):
    """Acknowledge only an admitted original retirement, after encoding all replies."""
    if not DEVILDOM1_RAID2_CONTROLLERS_ENABLED:return None
    run=s.dungeon_run
    if run is None or run.identity!=34140 or report['flag']!=255:return None
    if (run.stage,report['index'])not in CONTROLLERS:return None
    actors=[n for n in run.current['npcs'] if n.get('key')==report['index']]
    if len(actors)!=1:return []
    npc=actors[0]
    rule=source_rule(run,npc)
    if rule is None:return []
    owner=s.account.uid
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    from els_server.domain.summons import valid_sentry_death
    if (event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,)
            or event.uid!=MAX_UID or event.target_uid!=MAX_UID or event.payload_mode!=0
            or s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or not current_lease(s)
            or getattr(s,'reward_transaction',None) is not None
            or getattr(s,'reward_run_id',None)!=run.run_id
            or frozenset(getattr(s,'dungeon_participants',(owner,)))!=frozenset((owner,))
            or npc.get('active') is not False
            or not valid_sentry_death(report,owner)
            or any(not math.isfinite(v) or abs(v)>1e7 for v in report['xyz'])
            or report['hp_bits']!=struct.unpack('>I',struct.pack('>f',rule['hp']))[0]):return []
    key=npc['key']
    from els_server.domain.dungeon_lifecycle import death_ack,empty_reward_death_notice
    from els_server.protocol.protocol_codec import encode_event
    previous=run.defeated.get(key)
    if previous is not None:return [death_ack()] if previous==bytes(event.payload) else []
    shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run)
    shadow.dungeon_clock=copy.copy(s.dungeon_clock)
    shadow.dungeon_run.defeated={**run.defeated,key:bytes(event.payload)}
    shadow.defeated_npcs=shadow.dungeon_run.defeated
    from els_server.domain.dungeon_flow import periodic
    # The marker is already inactive; retirement changes no spawn, wave or HP.
    # The original kind-3 condition still decides the part, and the portal
    # request still requires every active hostile of the part to be dead.
    replies=[death_ack(),empty_reward_death_notice(key,report['killer'])]+periodic(shadow)
    for reply in replies:encode_event(reply)
    for name in ('defeated','next','ready_at'):setattr(run,name,getattr(shadow.dungeon_run,name))
    s.defeated_npcs=run.defeated;s.part_end_notified=shadow.part_end_notified
    s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
    return replies
