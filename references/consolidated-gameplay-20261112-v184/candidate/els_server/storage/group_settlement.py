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
    from els_server.storage.challenge_group import _roster, striker_binding
    from els_server.storage.challenge_state import read, commit_clear, eligible
    from els_server.domain.challenge_repeat_rewards import plans

    parent=room.owner_party
    striker=parent is not room.party
    roster=tuple(parent['members'])
    actors=tuple(members)
    bound=_binding(actors,room)
    challenge=room.party.get('challenge')
    shadows=[];deliveries=[]
    with closing(sqlite3.connect(bound[2],timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        def guard(writer):
            if writer is not db or not db.in_transaction or _binding(actors,room)!=bound:
                raise ValueError('Challenge original clear writer changed')
            if striker and (tuple(parent['members'])!=roster or parent.get('challenge') is not challenge
                or parent.get('union_runs',{}).get(room.party['striker_group']) is not room
                or room.party.get('challenge') is not challenge
                or any(m.application.world.party_of.get(m) is not parent for m in roster)):
                raise ValueError('Challenge striker roster changed')
            for s in roster:
                require_active_character(db,s.account.uid);require_owner(db,s.account.uid,s.account.account_id)
            return True
        guard(db)
        from els_server.domain.giant_daily_tasks import REWARDS,clock as task_clock
        from els_server.storage.aurora_admissions import day_at
        now=task_clock()if not challenge and room.identity in REWARDS else int(time.time())
        task_day=day_at(now)if not challenge and room.identity in REWARDS else None
        if challenge:
            _roster(db,challenge['attempt'],tuple(sorted(s.account.uid for s in roster)),parent['leader'].account.uid)
        if striker:
            striker_binding(db,challenge['attempt'],parent['union_groups'])
            if (eligible(challenge,room.identity,now) is None
                or any(read(db,m.account.uid)!=challenge for m in roster)):
                raise ValueError('Challenge striker progress changed')
            effect=dict(attempt=challenge['attempt'],dungeon=room.identity,now=now)
        rewards=plans(db,actors,now)if challenge else None
        for s in actors:
            before=load_character(db,s.account.uid,s.account.account_id)
            shadow=_shadow(s);shadow.reward_transaction=db
            ground=[]
            if challenge:
                from els_server.domain.raid_mark_drops import issue
                plan,ground=issue(db,shadow,rewards[s],guard)
                shadow._challenge_repeat_plan=(db,plan,s,guard,now)
                if striker:shadow.challenge_clear_effect=effect
            else:shadow._giant_task_actor=s;shadow._giant_task_day=task_day
            messages=settle_clear(shadow,event)
            if not shadow.clear_notified or shadow.reward_receipt is None:
                raise ValueError('Shared settlement did not produce a clear receipt')
            messages=[*ground, *(e for e in messages if e.kind not in (0xbc,0xae6))]
            _clear_observers(db,s,shadow,before,messages,guard,actors)
            if challenge and not striker:messages.append(notification(shadow,transaction=db))
            shadows.append(shadow);deliveries.append((s,messages))
        if striker:
            for s in roster:
                if s not in actors:commit_clear(db,s.account.uid,effect)
        state=read(db,room.leader.account.uid)if challenge else None
        if striker:
            from els_server.protocol.challenge_messages import phase_notice
            notice=phase_notice() if state['complete'] else phase_notice(
                state['challenge'],state['phase'],state['progress'],state['deadline'],
                actor=parent['leader'].account.uid,members=tuple(m.account.uid for m in roster))
            by_member=dict(deliveries)
            deliveries=[(m,[*by_member.get(m,()),notice]) for m in roster]
        boxes,snapshots=_prepare_mailboxes(deliveries,room.leader,all_members=True)
        guard(db);_mailboxes_unchanged(snapshots)
    # Adopt only the shadows and notifications encoded before commit.
    for s,shadow in zip(actors,shadows):
        _adopt(s,shadow)
        if challenge and not striker:
            s._challenge_weekly_stamp=shadow._challenge_weekly_stamp
            s._raid_progress_initialized=shadow._raid_progress_initialized
    if striker:
        parent['challenge']=state
        for running in parent['union_runs'].values():running.party['challenge']=state
        for s in roster:
            s._challenge_weekly_stamp=(s.account.uid,state['attempt'],state['progress'],state['complete'])
            s._raid_progress_initialized=None
    elif challenge:room.party['challenge']=state
    for s,box in boxes.items():s.mailbox=box
