"""Keep actual predicate results and rejected inputs for one loaded scene."""
from collections import deque
import sys
import time

from els_server.diagnostic_evidence import code_identity,recording,record_observation


def scene(run):
    return (run.run_id,run.stage,run.part,run.visits)


def state(run):
    population=tuple((n['key'],n['template'],n['active'],n.get('team',1),n.get('key_code'))for n in run.current['npcs'])
    return (scene(run),run.graph.get('source_sha256'),population,tuple(sorted(run.defeated)),run.portal_requested,run.started_at,
            tuple(sorted(getattr(run,'completed_stages',()))),getattr(run,'round',None))


def static_actor(run,key):
    actors=[n for n in run.current['npcs'] if n['key']==key and not n.get('dynamic')]
    if len(actors)!=1:return None
    npc=actors[0]
    return dict(key=key,template=npc['template'],source_index=npc.get('source_index'),key_code=npc.get('key_code'))


def condition_result(run,condition,result,reason,*,keys=(),mode='all'):
    """Return the existing result unchanged; never reevaluate a predicate."""
    if not recording():return result
    # Quiet combat does not build a population snapshot on each periodic poll.
    if not getattr(run,'_diagnostic_actor_rejections',()) and (run.started_at is None or run.clock()-run.started_at<30):return result
    index=next((i for i,c in enumerate(run.current['conditions']) if c is condition),None)
    if index is None:return result
    previous=getattr(run,'_diagnostic_conditions',None)
    observed=time.monotonic();rejected=getattr(run,'_diagnostic_actor_rejections',())
    last_rejection=rejected[-1]['observed_monotonic'] if rejected else None
    prior=previous[1].get(index) if previous is not None and previous[0][0]==scene(run) else None
    if (prior is not None and prior['ready']==bool(result) and prior.get('last_rejection')==last_rejection
        and observed-prior['observed_monotonic']<1):return result
    current_state=state(run)
    rows=dict(previous[1]) if previous is not None and previous[0]==current_state else {}
    if index>=16:return result
    selected=list(keys);missing=[key for key in selected if key not in run.defeated]
    caller=sys._getframe(1)
    rows[index]=dict(index=index,kind=condition['kind'],ready=bool(result),reason=reason,mode=mode,
        required_count=len(selected),missing_count=len(missing),missing_keys=missing[:24],
        missing_actors=[static_actor(run,key)for key in missing[:24]],
        keys_omitted=max(0,len(missing)-24),observed_monotonic=observed,last_rejection=last_rejection,
        site=dict(code_identity(caller.f_code),line=caller.f_lineno))
    # Replacement, not mutation: prepared shallow copies must not alter the live run's evidence.
    run._diagnostic_conditions=(current_state,rows)
    return result


def reject_actor(session,report,reason,sequence=None,*,facts=None):
    """Only called on a branch that actually returns a rejected retirement."""
    if not recording():return
    run=session.dungeon_run
    caller=sys._getframe(1)
    row=dict(scene=list(scene(run)),actor=report['index'],flag=report['flag'],status=report['status'],
        actor_identity=static_actor(run,report['index']),
        reason=reason,sequence=sequence,observed_monotonic=time.monotonic(),
        site=dict(code_identity(caller.f_code),line=caller.f_lineno))
    if facts is not None:row['facts']=facts
    rows=deque(getattr(run,'_diagnostic_actor_rejections',()),maxlen=64)
    if rows and rows[-1]['scene']==row['scene'] and rows[-1]['actor']==row['actor'] and rows[-1]['sequence']==sequence:return
    rows.append(row);run._diagnostic_actor_rejections=tuple(rows)
    record_observation('dungeon_actor','retirement_rejected',row,stacklevel=2)


def scene_evidence(run):
    current_scene=scene(run)
    previous=getattr(run,'_diagnostic_conditions',None)
    checks=list(previous[1].values()) if previous is not None and previous[0]==state(run) else []
    rejected=[row for row in getattr(run,'_diagnostic_actor_rejections',())
              if row['scene']==list(current_scene) and row['actor'] not in run.defeated]
    return dict(scene=list(current_scene),condition_checks=checks,condition_count=len(run.current['conditions']),
                actor_rejections=rejected[-24:])


def failed_check(rule,facts):
    """Call only inside the original failing branch, before its unchanged exception."""
    record_observation('business_condition',rule,dict(facts,passed=False),stacklevel=2)
