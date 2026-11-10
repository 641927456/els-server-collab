"""Source-pinned34320 static retirements for one admitted shared room.

The native master supplies its original complete UID/byte map unchanged.
Only authority checks, one all-member quest writer and existing notices run.
No AI, timer, gate, loot/EXP or client packet is synthesized.
"""
import copy, math, sqlite3, struct, uuid
from contextlib import closing
from pathlib import Path


class SharedStoryRefusal(ValueError):
    """A current room/earned-stage gate refused before external commit."""


def _roster_report(report,members):
    readiness=report['readiness']
    uids={m.account.uid for m in members}
    return (isinstance(readiness,dict) and set(readiness)==uids
        and all(type(k) is int and type(v) is int and v in (0,1) for k,v in readiness.items())
        and report['flag']==255 and report['status']==1 and report['source']==2**64-1
        and report['killer']==2**64-1 and report['extra_uid']==0
        and report['last_uid'] in (0,2**64-4) and not report['contribution'] and not report['counters']
        and all(math.isfinite(v) and abs(v)<=1e7 for v in report['xyz']))


def _checked(dispatcher,r,s,event):
    from els_server.domain.friends_spawns import _checked_static_generation
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if (s is not r.leader or r.identity!=34320 or not 2<=len(r.members)<=4
            or r.phase not in ('active','part_end') or r.party.get('run') is not r
            or any(r.party.get(k) for k in ('raid_party','challenge','challenge_pending','solo_challenge'))
            or event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,)
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
        raise ValueError('Shared story room unavailable')
    generation=_checked_static_generation(dispatcher,r)
    seed=uuid.UUID(r.seed)
    if str(seed)!=r.seed or seed.version!=4:raise ValueError('Shared story seed identity')
    paths=set()
    for m in r.members:
        account=m.account
        if (dispatcher.world.party_of.get(m) is not r.party or m in dispatcher.world.members
                or getattr(m,'application',None) is None or not current_lease(m)
                or account.store is None or account.store.uid!=account.uid
                or not m.reward_test or not m.item_test or m.client_build!='dx11_260923'
                or getattr(m,'reward_transaction',None) is not None
                or m.reward_run_id!=str(uuid.uuid5(seed,'reward:'+str(account.uid)))
                or getattr(m,'active_challenge',None) is not None
                or getattr(m,'challenge_deadline',None) is not None
                or getattr(m,'dungeon_failed',False) or m.clear_notified):
            raise ValueError('Shared story member lease')
        paths.add(Path(account.store.path).resolve())
    if len(paths)!=1:raise ValueError('Shared story requires one database')
    return generation,next(iter(paths))


def retire(dispatcher,r,s,event):
    # A nonmatching static actor still follows the original dispatcher. This
    # module owns only these three source tuples, including rejected combat AD.
    if r.identity!=34320 or s.dungeon_run is None:return None
    from els_server.domain.dungeon_lifecycle import death_report,death_ack,empty_reward_death_notice
    try:report=death_report(event.payload)
    except ValueError:return []
    run=s.dungeon_run
    npc=next((n for n in run.current['npcs'] if n['key']==report['index']),None)
    if (npc is None or npc.get('dynamic') or (run.stage,run.part,npc['template']) not in
            ((1,1,7523),(2,0,7524),(3,0,7513))):return None
    from els_server.domain.story_controller_retirements import shared_34320_rule
    try:
        generation,path=_checked(dispatcher,r,s,event)
        if not _roster_report(report,r.members):return []
        rules={}
        for m in r.members:
            actor=next((n for n in m.dungeon_run.current['npcs'] if n['key']==report['index']),None)
            if actor is None or actor!=npc or report['index'] in m.summon_keys:return []
            rule=shared_34320_rule(m.dungeon_run,actor,m.account.character()['unit_type'])
            if rule is None or report['hp_bits']!=struct.unpack('>I',struct.pack('>f',rule['hp']))[0]:return []
            rules[m]=rule
    except ValueError:return []
    key=npc['key'];previous=run.defeated.get(key)
    if previous is not None:
        return [death_ack()] if previous==event.payload else []
    if r.phase!='active':return []
    from els_server.domain.quest_flow import store
    from els_server.domain.dungeon_flow import periodic
    from els_server.domain.party_commands import _prepared_boxes
    prepared={};deliveries={};seen={}
    base=run.run_id+':'+str(run.stage)+':'+str(run.part)+':kill:'+str(key)
    for m in r.members:
        shadow=copy.copy(m);shadow.dungeon_run=copy.copy(m.dungeon_run)
        shadow.dungeon_run.defeated={**m.dungeon_run.defeated,key:bytes(event.payload)}
        shadow.defeated_npcs=shadow.dungeon_run.defeated;shadow.dungeon_clock=copy.copy(m.dungeon_clock)
        prepared[m]=shadow;seen[m]=set(getattr(m,'_quest_seen_events',None) or ())|{base}
    try:
        with closing(sqlite3.connect(path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            for m in r.members:
                owner=m.account.uid;rule=rules[m];shadow=prepared[m]
                def validate(connection):
                    try:current=_checked(dispatcher,r,s,event)
                    except ValueError as error:raise SharedStoryRefusal(str(error)) from error
                    if current!=(generation,path):raise SharedStoryRefusal('Shared story generation changed')
                    current={q for q, in connection.execute('SELECT quest FROM completed_quests WHERE owner=?',(owner,))}
                    current.update(q for q, in connection.execute('SELECT quest FROM character_quests WHERE owner=?',(owner,)))
                    if not current.intersection(rule['map_quests']):raise SharedStoryRefusal('Story retirement quest stage')
                def prepare(notices,replayed):
                    messages=[] if m is not s else [death_ack()]
                    if not replayed:messages.append(empty_reward_death_notice(key,report['killer']))
                    return messages+notices+periodic(shadow)
                witness=dict(kind='kill',dungeon=run.identity,npc=npc['template'],level=m.account.character()['level'])
                deliveries[m]=store(m).record(base,witness,event.payload,validate=validate,prepare=prepare,transaction=db)
            boxes=_prepared_boxes([(m,deliveries[m]) for m in r.members if m is not s],deliveries[s])
            try:current=_checked(dispatcher,r,s,event)
            except ValueError as error:raise SharedStoryRefusal(str(error)) from error
            if current!=(generation,path):raise SharedStoryRefusal('Shared story generation changed')
    except SharedStoryRefusal:return []
    # All SQL, source gates, real encoders and bounded mailbox preparations have
    # succeeded before any run, clock, observer set or delivery is published.
    for m,shadow in prepared.items():
        for name in ('defeated','next','ready_at'):setattr(m.dungeon_run,name,getattr(shadow.dungeon_run,name))
        m.defeated_npcs=m.dungeon_run.defeated;m.part_end_notified=shadow.part_end_notified
        m.dungeon_clock=shadow.dungeon_clock;m._quest_seen_events=seen[m]
    for m,box in boxes.items():m.mailbox=box
    dispatcher.part_wait(r)
    return deliveries[s]
