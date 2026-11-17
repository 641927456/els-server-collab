"""Small projections of values already read by the gameplay handler."""
from els_server.diagnostic_evidence import recording,record_observation


def item_snapshot(item,*,owner=None,level=None):
    if not recording():return
    fields={key:item[key] for key in ('uid','template','group','slot','count','sealed','expires_at','lock_until','activation_seconds') if key in item}
    if owner is not None:fields['owner']=owner
    if level is not None:fields['level']=level
    record_observation('item_use','selected_instance',fields,include_site=False)


def quest_snapshot(kind,quest,character,active,done,location,*,completed=None,items=None,objectives=()):
    if not recording():return
    from els_server.domain.seal_quests import sequence,target
    cond=quest['QuestCondition']
    details=dict(action=kind,quest=quest['m_iID'],location=list(location),
        active=active is not None,completed=done is not None,
        character={key:character.get(key) for key in ('level','unit_type','unit_class','transcendence','master')},
        requirement={key:cond[key] for key in ('m_iLevel','m_iLimitLevel','m_iConditionItemID','m_iConditionItemNum') if key in cond},
        predecessor_ids=list(sequence(cond.get('m_vecBeforeQuestID',{})))[:32])
    if completed is not None:details['missing_predecessors']=[qid for qid in details['predecessor_ids'] if qid and qid not in completed]
    if items is not None and cond.get('m_iConditionItemID'):
        details['prerequisite_item_count']=sum(i['count'] for i in items if i['template']==cond['m_iConditionItemID'])
    if active is not None and objectives:
        details['objectives']=[dict(id=sub['m_iID'],current=active['objectives'].get(sub['m_iID']),required=target(sub)) for sub in objectives][:24]
    record_observation('quest','qualification_snapshot',details,include_site=False)


def gate_snapshot(session,reason):
    if not recording():return
    run=session.dungeon_run
    if run is None:return
    current=run.current
    pending=[dict(key=n['key'],template=n['template'],active=n['active'],team=n.get('team',1),
                  no_drop=n.get('no_drop',False),
                  source_index=n.get('source_index'),key_code=n.get('key_code'))
             for n in current['npcs'] if n['key'] not in run.defeated]
    target=run.next
    details=dict(dungeon=run.identity,stage=run.stage,part=run.part,
        graph_sha256=run.graph.get('source_sha256'),
        synced=session.dungeon_substage_synced,loading=session.gate_stage_loading,
        part_end=session.part_end_notified,cleared=session.clear_notified,
        portal_requested=run.portal_requested,started=run.started_at is not None,
        next={k:target[k] for k in ('kind','stage','part') if k in target} if target else None,
        pending_count=len(pending),pending_actors=pending[:24],
        missing_quest_barrier=list(set(getattr(run,'memory1_quest_barrier',()))-set(run.defeated))[:24],
        source_conditions=[{k:c[k] for k in ('kind','required','seconds','delay') if k in c} for c in current['conditions'][:16]])
    from els_server.gameplay_causes import scene_evidence
    details.update(scene_evidence(run))
    record_observation('dungeon_gate',reason,details,stacklevel=2)


def observe_dungeon_wait(session):
    """A long unchanged scene is evidence, not a stalled-mechanism verdict."""
    if not recording():return
    run=session.dungeon_run
    if run is None or session.phase!='dungeon_active' or not session.dungeon_substage_synced or session.clear_notified:return
    if run.started_at is None or run.clock()-run.started_at<30:return
    rejected=getattr(run,'_diagnostic_actor_rejections',())
    latest=(rejected[-1]['actor'],rejected[-1]['reason']) if rejected else None
    key=(run.run_id,run.stage,run.part,run.visits,latest)
    if getattr(session,'_diagnostic_wait_scene',None)==key:return
    session._diagnostic_wait_scene=key
    gate_snapshot(session,'scene_unchanged_at_least_30s')
