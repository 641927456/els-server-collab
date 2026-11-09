"""One challenge/giant clear writer and complete native peer deliveries."""
import json,sqlite3,time
from pathlib import Path
from contextlib import closing


def _binding(members,room):
    from els_server.domain.friends_spawns import _checked_static_generation
    from els_server.domain.regional_drop_materials import catalog as regional_drops
    challenge=room.party.get('challenge')
    if (room.phase!='part_end' or room.party.get('run')is not room
        or room.members!=members or tuple(room.party['members'])!=members
        or not challenge and str(room.identity)not in regional_drops()['giant_maps']or room.party.get('dungeon')!=room.identity):
        raise ValueError('Challenge original clear room changed')
    generation=_checked_static_generation(members[0].application.world.dungeons,room)
    paths=set();actors=[];state=challenge
    for s in members:
        a=s.account;r=s.dungeon_run
        if (s.role!='game' or s.phase!='dungeon_active' or not s.item_test or not s.reward_test
            or not s.dungeon_substage_synced or s.gate_stage_loading or not s.part_end_notified
            or s.clear_notified or s.dungeon_failed or getattr(s,'reward_transaction',None)is not None
            or s.active_challenge!=({'attempt':state['attempt'],'dungeon':room.identity}if state else None)
            or s.challenge_deadline!=(state['deadline']if state else None)or r is None or r.identity!=room.identity
            or r.next is None or r.next['kind']!=4 or r.ready_at is None or r.clock()<r.ready_at):
            raise ValueError('Challenge original clear actor changed')
        for path in(a.store.path,a.reward_store.path,a.characters.path,s.application.config.state_file):paths.add(Path(path).resolve())
        actors.append((s,a,a.root,a.store,a.reward_store,a.characters,s.identity,s.shop_session_id,
            a.uid,a.account_id,s.reward_run_id,r,r.stage,r.part,r.visits,r.graph['source_sha256'],
            json.dumps(r.next,sort_keys=True),r.ready_at))
    if len(paths)!=1:raise ValueError('Shared challenge requires one database')
    return tuple(actors),generation,next(iter(paths)),(room.party,state,tuple(sorted(state.items()))if state else ())


def settle(members,event,*,room):
    from els_server.domain.dungeon_settlement_commands import settle_clear
    from els_server.domain.challenge_flow import notification
    from els_server.domain.pve_economy_flow import _shadow,_adopt,_prepare_mailboxes,_mailboxes_unchanged
    from els_server.domain.raid_economy_flow import _clear_observers
    from els_server.storage.seal_quests import load_character
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    from els_server.storage.challenge_group import _roster
    from els_server.storage.challenge_state import read
    from els_server.domain.challenge_repeat_rewards import plans
    members=tuple(members);bound=_binding(members,room);shadows=[];deliveries=[]
    with closing(sqlite3.connect(bound[2],timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        def guard(writer):
            if writer is not db or not db.in_transaction or _binding(members,room)!=bound:
                raise ValueError('Challenge original clear writer changed')
            for s in members:
                require_active_character(db,s.account.uid);require_owner(db,s.account.uid,s.account.account_id)
            return True
        guard(db)
        challenge=room.party.get('challenge')
        from els_server.domain.giant_daily_tasks import REWARDS,clock as task_clock
        from els_server.storage.aurora_admissions import day_at
        now=task_clock()if not challenge and room.identity in REWARDS else int(time.time())
        task_day=day_at(now)if not challenge and room.identity in REWARDS else None
        if challenge:_roster(db,challenge['attempt'],tuple(sorted(s.account.uid for s in members)),room.leader.account.uid)
        rewards=plans(db,members,now)if challenge else None
        for s in members:
            before=load_character(db,s.account.uid,s.account.account_id)
            shadow=_shadow(s);shadow.reward_transaction=db
            if challenge:shadow._challenge_repeat_plan=(db,rewards[s],s,guard,now)
            else:shadow._giant_task_actor=s;shadow._giant_task_day=task_day
            messages=settle_clear(shadow,event)
            if not shadow.clear_notified or shadow.reward_receipt is None:
                raise ValueError('Shared settlement did not produce a clear receipt')
            messages=[e for e in messages if e.kind not in(0xbc,0xae6)]
            _clear_observers(db,s,shadow,before,messages,guard,members)
            if challenge:messages.append(notification(shadow,transaction=db))
            shadows.append(shadow);deliveries.append((s,messages))
        state=read(db,room.leader.account.uid)if challenge else None
        boxes,snapshots=_prepare_mailboxes(deliveries,room.leader,all_members=True)
        guard(db);_mailboxes_unchanged(snapshots)
    # All encoding, observations, reads and queue admission succeeded before
    # commit. The serialized worker now adopts only already prepared objects.
    for s,shadow in zip(members,shadows):
        _adopt(s,shadow)
        if challenge:
            s._challenge_weekly_stamp=shadow._challenge_weekly_stamp
            s._raid_progress_initialized=shadow._raid_progress_initialized
    if challenge:room.party['challenge']=state
    for s,box in boxes.items():s.mailbox=box
