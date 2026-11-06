"""Cooperative time slices on the existing single business worker.

A member remains indivisible: its transaction, read scope and clock observations
finish before a slice is returned. Room polling is shared across the cohort.
"""
import math
import time
from threading import Lock


class PeriodicClaim:
    """Cancel only an unstarted poll, never its SQL or native delivery."""
    def __init__(self):self.lock=Lock();self.state='pending';self._admitted=False;self.upkeep_reserved=False
    def admit(self):
        with self.lock:
            if self.state!='pending':return False
            self._admitted=True;return True
    @property
    def admitted(self):
        with self.lock:return self._admitted
    def start(self):
        with self.lock:
            if self.state!='pending':return False
            self._admitted=True;self.state='running';return True
    def cancel(self):
        with self.lock:
            if self.state!='pending':return False
            self.state='cancelled';return True
    @property
    def cancelled(self):
        with self.lock:return self.state=='cancelled'


def next_poll_deadline(application,session,now,interval=.05):
    """Publish one deadline while this worker still owns the actor/domain.

    Ordinary town and solo static routes have no work between their native
    time condition, pending gate delay, mailbox arrival or one-second upkeep.
    Shared rooms and other live activities retain their original fast poll.
    """
    if (getattr(session,'_periodic_pending',False)or not session._periodic_idle()):return now
    # An idle authenticated frontend has the same one-second upkeep clock.
    # Mailbox arrivals and unfinished slices above still request an immediate turn.
    if session.role=='frontend' and session.phase=='authenticated':
        return max(now,session.next_periodic)
    if (session.released or session.role!='game'
            or application.world.party_of.get(session)is not None
            or application.world.pvp.room(session)is not None
            or application.world.racing.room(session)is not None
            or application.world.field_bosses.room(session)is not None
            or getattr(session,'active_challenge',None)is not None):return now+interval
    due=max(now,session.next_periodic)
    if session.phase=='town_ready':return due
    if(session.phase in('player_initialized','skill_ui_ready','initialization_confirmed','map_loading','square_accepted')
            and session.dungeon_run is None):return due
    if session.phase!='dungeon_active':return now+interval
    run=session.dungeon_run
    if (run is None or not session.dungeon_substage_synced or run.encounter is not None
            or run.clock is not time.monotonic):return now+interval
    from els_server.domain.dungeon_flow import curtain_token
    from els_server.domain.story_controller_retirements import gate_predecessor_blocked
    if curtain_token(session)is not None or gate_predecessor_blocked(run):return now+interval
    if not session.part_end_notified and not session.clear_notified:
        if run.next is not None and not run.next.get('curtain_opened'):
            due=min(due,max(now,run.ready_at))
        elif run.next is None and run.started_at is not None:
            due=min((due,*(max(now,run.started_at+c['seconds'])for c in run.current['conditions']if c['kind']==6)))
    deadline=getattr(session,'challenge_deadline',None)
    if deadline is not None:due=min(due,now+max(0,deadline-time.time()))
    return due


async def periodic_chunks(application, sessions, *, budget_ms=4.0, claims=None):
    from els_server.application import FriendsSession
    sessions = tuple(sessions)
    if len(sessions) > 16:
        raise ValueError('Periodic batch bounds')
    if claims is not None and len(claims)!=len(sessions):raise ValueError('Periodic claim bounds')
    if isinstance(budget_ms, bool) or not math.isfinite(budget_ms) or budget_ms <= 0:
        raise ValueError('Periodic slice budget')
    rooms = set()
    position = 0
    while position < len(sessions):
        submitted = time.perf_counter()
        queue_timing = {}
        session=sessions[position]
        if application.dungeon_workers.candidate(session.periodic_notifications,()):
            queue_timing['lane']='dungeon'
            mailbox_only=application.dungeon_workers.town_mailbox(session.periodic_notifications,())
            def dungeon_poll():
                nonlocal position
                index=position;position+=1
                queue_timing['batch_started_at']=time.perf_counter()
                if claims is not None and not claims[index].start():return [([],None)]
                options={'_rooms':rooms,'_slice':True,'_mailbox_only':mailbox_only}if isinstance(session,FriendsSession)else{}
                try:return [(application._worker_call(session.periodic_notifications,(),options,submitted,queue_timing=queue_timing),None)]
                except Exception as error:return [(None,error)]
                finally:
                    if not getattr(session,'_periodic_pending',False):application.dungeon_workers.publish(dungeon_poll,(),periodic=True,independent=True)
            dungeon_poll._dungeon_session=session
            try:
                if mailbox_only:
                    queue_timing['lane']='town-mailbox'
                    result=await application.dungeon_workers.run(session,dungeon_poll,timing=queue_timing)
                else:
                    town=application.dungeon_workers.town_periodic(session.periodic_notifications,())
                    queue_timing['lane']='town'if town else'dungeon-upkeep'
                    claim=None if claims is None else claims[position]
                    result=await application.dungeon_workers.run_upkeep(session,dungeon_poll,timing=queue_timing,claim=claim,world_background=town)
                    if result is None:
                        assert claim.cancelled
                        position+=1;result=[([],None)]
            finally:dungeon_poll=None
            yield result
            continue

        def invoke():
            nonlocal position
            queue_timing['batch_started_at'] = time.perf_counter()
            deadline = time.monotonic() + budget_ms / 1000
            result = []
            worked = False
            try:
                while position < len(sessions):
                    session = sessions[position]
                    if application.dungeon_workers.candidate(session.periodic_notifications,()):break
                    if claims is not None and not claims[position].start():
                        result.append(([],None));position+=1
                        continue
                    worked = True
                    options = {'_rooms': rooms,'_slice':True} if isinstance(session, FriendsSession) else {}
                    try:
                        messages = application._worker_call(session.periodic_notifications, (), options,
                                                            submitted, queue_timing=queue_timing)
                        result.append((messages, None))
                    except Exception as error:
                        result.append((None, error))
                    position += 1
                    if time.monotonic() >= deadline:
                        break
                return result

            finally:
                if worked:application.dungeon_workers.publish(invoke,(),periodic=True)

        try:
            async with application.world_gate.exclusive():
                result=await application.business_queue.run(invoke, timing=queue_timing)
        finally:invoke=None
        # A queued town slice may become a dungeon before it starts. No
        # claim ran in that case; classify it again on the next iteration.
        if result:yield result
