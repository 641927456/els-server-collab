"""Bind the two original gate outcomes to daily clear/failure transactions."""
import copy,sqlite3,time,uuid
from contextlib import closing
from pathlib import Path

def gates(run):
    from els_server.domain.dungeon_routes import DungeonRun
    from els_server.domain.ariel_daily_special_rules import rule
    r=rule(38300)
    if (type(run)is not DungeonRun or run.identity!=38300 or (run.stage,run.part)!=(0,0)
        or run.graph['source_sha256']!=r['graph_sha256'] or run.graph!=run.catalog.graph(38300)):
        raise ValueError('Dark Gate original scene required')
    result=[]
    for template,index,point,ally in ((1368,1,2,True),(1367,2,1,False)):
        matches=[n for n in run.current['npcs']if (n['template'],n.get('source_index'))==(template,index)]
        if len(matches)!=1:raise ValueError('Dark Gate original gate actor missing')
        n=matches[0]
        if n.get('dynamic') or n.get('ally')is not ally or n['start_point']!=point:
            raise ValueError('Dark Gate actor source changed')
        result.append(n)
    return tuple(result)

def require_victory(run):
    ally,enemy=gates(run)
    if ally['key']in run.defeated or type(run.defeated.get(enemy['key']))is not bytes or not run.defeated[enemy['key']]:
        raise ValueError('Dark Gate requires enemy gate victory with allied gate intact')

def settle_failures(prepared,deliveries,boxes,key,proof):
    """Preflight every member and wire queue before committing any daily count."""
    from els_server.domain.ariel_attendance_flow import authority
    from els_server.protocol.protocol_codec import encode_event
    from els_server.storage.dark_gate_rewards import consume
    from els_server.storage.ariel_daily_special import notification
    from els_server.storage.sqlite_timing import begin_write,commit_write,end_write
    members=tuple(prepared)
    if not members:raise ValueError('Dark Gate empty failure roster')
    paths={Path(m.account.store.path).resolve()for m in members}
    runs={m.dungeon_run.run_id for m in members}
    owners=frozenset(m.account.uid for m in members)
    if len(paths)!=1 or len(runs)!=1 or len(owners)!=len(members):raise ValueError('Dark Gate failure roster/save')
    def validate():
        for m,shadow in prepared.items():
            authority(m);run=m.dungeon_run;ally,enemy=gates(run)
            if (m.phase!='dungeon_active' or not m.dungeon_substage_synced or m.clear_notified
                or getattr(m,'dungeon_failed',False) or not m.reward_test or not m.item_test
                or m.dungeon_id!=38300 or ally['key']!=key or key in run.defeated
                or enemy['key']in run.defeated or not shadow.clear_notified or not shadow.dungeon_failed
                or shadow.dungeon_run.defeated.get(key)!=proof
                or frozenset(getattr(m,'dungeon_participants',(m.account.uid,)))!=owners):
                raise ValueError('Dark Gate accepted allied gate failure required')
            expected=run.run_id if len(members)==1 else str(uuid.uuid5(uuid.UUID(run.run_id),'reward:'+str(m.account.uid)))
            if m.reward_run_id!=expected:raise ValueError('Dark Gate failure reward identity')
            if len(members)>1:
                room=m.application.world.dungeons.room(m)
                if room is None or frozenset(room.members)!=frozenset(members) or room.seed!=run.run_id or room.phase!='active':
                    raise ValueError('Dark Gate current shared failure roster')
    validate()
    with closing(sqlite3.connect(next(iter(paths)),timeout=10))as db:
        acquired=None
        try:
            db.execute('PRAGMA foreign_keys=ON')
            acquired=begin_write(db);validate();moment=int(time.time())
            for m in members:
                consume(db,m.account.account_id,m.account.uid,m.reward_run_id,proof,moment)
                notice=notification(db,m.account.account_id,m.account.uid,moment)
                encode_event(notice);deliveries[m].append(notice)
                if m in boxes:boxes[m].append(notice)
            validate();commit_write(db)
        except BaseException:db.rollback();raise
        finally:
            if acquired is not None:end_write(acquired,failed=__import__('sys').exc_info()[0]is not None)

def failed_death(s,event,npc,expired,notice):
    from els_server.domain.dungeon_flow import failed,death_ack
    from els_server.protocol.protocol_codec import encode_event
    run=s.dungeon_run;ally,_=gates(run)
    if ally is not npc:raise ValueError('Dark Gate failure must use original allied gate')
    room=None;members=(s,)
    if frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=frozenset((s.account.uid,)):
        dispatcher=s.application.world.dungeons;room=dispatcher.room(s)
        if room is None or room.leader is not s:raise ValueError('Dark Gate master failure required')
        from els_server.domain.friends_spawns import _checked_static_generation
        _checked_static_generation(dispatcher,room);members=tuple(room.members)
    prepared={};deliveries={};allies={}
    for m in members:
        allies[m]=gates(m.dungeon_run)[0]
        shadow=copy.copy(m);trial=copy.copy(m.dungeon_run)
        trial.defeated={**trial.defeated,npc['key']:bytes(event.payload)}
        shadow.dungeon_run=trial;shadow.dungeon_clock=copy.copy(m.dungeon_clock)
        replies=([death_ack()]if m is s else [])+[notice]+failed(shadow)
        for message in replies:encode_event(message)
        prepared[m]=shadow;deliveries[m]=replies
    from els_server.domain.party_commands import _prepared_boxes
    boxes=_prepared_boxes([(m,deliveries[m])for m in members if m is not s],deliveries[s])if room else {}
    settle_failures(prepared,deliveries,boxes,npc['key'],bytes(event.payload))
    for m,shadow in prepared.items():
        m.dungeon_run.defeated=shadow.dungeon_run.defeated;m.defeated_npcs=m.dungeon_run.defeated
        if expired:allies[m]['active']=False
        for name in ('clear_notified','dungeon_failed','reward_receipt','dungeon_clock'):
            setattr(m,name,getattr(shadow,name))
    for m,box in boxes.items():m.mailbox=box
    if room is not None:room.phase='clear';room.deadline=0
    return deliveries[s]
