"""Finish the original zero-reward 28040 handoff on a real loaded first entry.

The current client starts Quest_28040_end itself, then retires9468 after
Quest_28050_end. It does not send F4 for28040 in this path. The server must
commit that already-earned entry before admitting the original28050 actor.
No script, actor retirement, timer or reward value is synthesized here.
"""
from contextlib import closing
import sqlite3

GRAPH_SHA='d71dba419ad369412c4e98a7f0d450f351c0ec533d9d0cb6abec4d50a2251e04'


def _binding(s,run):
    from els_server.domain.quest_flow import account_source_actor
    account=s.account
    if (not account_source_actor(s) or s.phase!='dungeon_active'
        or run is not s.dungeon_run or run.identity!=35250 or s.dungeon_id!=35250
        or not s.dungeon_substage_synced or s.clear_notified
        or getattr(s,'reward_transaction',None) is not None
        or getattr(s,'reward_run_id',None)!=run.run_id or run.started_at is None
        or run.graph.get('source_sha256')!=GRAPH_SHA or (run.stage,run.part)!=(0,0)
        or frozenset(getattr(s,'dungeon_participants',(account.uid,)))!=frozenset((account.uid,))
        or account.character()['unit_type']!=15):
        raise ValueError('Lithia first entry is not current loaded source')
    return (account,account.store,account.uid,account.account_id,s.shop_session_id,
            run,run.run_id,run.stage,run.part,run.visits)


def _source():
    from els_server.domain.seal_quests import quest_catalog,sequence
    catalog=quest_catalog();q=catalog.quest(28040)
    if (q['m_iID']!=28040 or q['m_eQuestType']!=5 or q.get('m_bIsAccount',0)
        or q['m_bRepeat'] or q['m_bIsTimeEvent']
        or sequence(q['QuestCondition']['m_eUnitType'])!=(15,)
        or sequence(q['QuestCondition']['m_vecBeforeQuestID'])!=(28030,)
        or sequence(q['m_iAfterQuestID'])!=(28050,)
        or catalog.objectives(28040)!=({'m_iID':28040,'m_eClearType':26,
            'm_bAutomaticDescription':0,'m_ClearCondition':{'m_eDungeonID':{'0':None,'1':35250}}},)
        or q['Reward']!={'m_iSP':0,'m_iBuff':0,'m_iEP':0,'m_iED':0,'m_iEXP':0,
                        'm_bEnable':1,'m_eChangeUnitClass':0}
        or q['SelectReward']!={'m_iSelectionCount':0}):
        raise ValueError('Lithia first entry source changed')


def record_visit(s,run,state,event_id,event,proof):
    """Keep the ordinary visit path, with one finite same-writer handoff."""
    if run.identity!=35250 or s.account.character()['unit_type']!=15 or (run.stage,run.part)!=(0,0):
        return state.record(event_id,event,proof)
    expected=_binding(s,run);_source()
    if (state.uid!=s.account.uid or state.account_id!=s.account.account_id
        or state.path!=s.account.store.path or event!=dict(kind='visit_dungeon',dungeon=35250,level=s.account.character()['level'])
        or proof!=(run.run_id+':'+run.graph['source_sha256']+':0:0').encode()
        or event_id!='discovery:'+run.run_id+':0:0:'+str(getattr(s,'_quest_discovery_epoch',0))):
        raise ValueError('Lithia first entry witness changed')
    from els_server.storage.seal_quests import load_character
    from els_server.storage.item_actor import require_active_character
    from els_server.protocol import quest_messages as wire
    from els_server.protocol.local_messages import skill_slots_initialization
    from els_server.protocol.protocol_codec import encode_event
    def guard(db):
        if _binding(s,run)!=expected:raise ValueError('Lithia first entry actor changed')
        require_active_character(db,state.uid)
        character=load_character(db,state.uid,state.account_id)
        if character['unit_type']!=15:raise ValueError('Lithia first entry saved actor changed')
    with closing(sqlite3.connect(state.path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');guard(db)
        notices=state.record(event_id,event,proof,transaction=db)
        active=db.execute('SELECT generation,objectives FROM character_quests WHERE owner=? AND quest=28040',(state.uid,)).fetchone()
        done=db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=28040',(state.uid,)).fetchone()
        if active is not None and not done:
            import json
            if json.loads(active[1])!={'28040':1}:raise ValueError('Lithia first entry objective not earned')
            operation='lithia-entry:'+str(state.uid)+':'+run.run_id+':28040:'+str(active[0])
            def encode(result):
                guard(db)
                completed=next(row for row in result['state']['completed'] if row['id']==28040)
                replies=[wire.reward_ack(28040,result['character'],s.account.get_location(),result['slots'],
                    result['balances'],result['items'],result['updates'],consumed=result['consumed'],
                    replayed=result['replayed'],completed_at=completed['completed_at']),wire.initialization(result['state'])]
                replies.extend(wire.accepted(row) for row in result['accepted_after'])
                replies.append(skill_slots_initialization(result['slots'],state.uid,result['character']))
                return replies
            result=state.action('claim',dict(quest=28040,npc=0,flags=(0,0,1,1,0)),operation,
                                encode,location=('dungeon',35250),transaction=db)
            notices+=result['events']
        elif active is not None:
            raise ValueError('Lithia first entry conflicting saved state')
        for notice in notices:encode_event(notice)
        guard(db)
        return notices
