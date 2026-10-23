"""Small session adapter; quest work never mutates dungeon lifecycle state."""
import struct
from els_server.protocol import quest_messages as wire
from els_server.storage.seal_quests import QuestState,QuestIncomplete
from els_server.storage.inventory_state import InventoryFull

def enabled(s):
    return s.item_test and s.client_build=='dx11_260923' and s.account.characters is not None and s.account.store is not None

def account_source_actor(s):
    from els_server.domain.equipment_chip_flow import current_lease
    return (enabled(s) and s.role=='game' and s.phase in ('town_ready','dungeon_active')
        and not getattr(s,'released',False) and s.account.store.uid==s.account.uid and current_lease(s))

def account_source_guard(s,db):
    # Finite53520 lease/actor gate; other quest semantics remain unchanged.
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.storage.item_actor import require_active_character
    if not account_source_actor(s):
        raise ValueError('Obsolete ERP support quest actor/session')
    require_active_character(db,s.account.uid)

def store(s):return QuestState(s.account.store.path,s.account.uid,account_id=s.account.account_id,account_source_guard=lambda db:account_source_guard(s,db))

def initialization(s):
    if enabled(s):
        # Only the validated character-selection path may restore a starter.
        # Failed/abandoned quest requests also use this encoder in town.
        if s.role=='game' and s.phase in ('characters_ready','channels_ready'):
            from els_server.domain.tutorial_quests import restore_initialization
            return restore_initialization(store(s))[0]
        return wire.initialization(store(s).snapshot())
    from els_server.protocol.local_messages import inventory_initialization
    return inventory_initialization()

def observed_run(s):
    """Adapt the admitted El Tree route without changing its lifecycle."""
    if s.dungeon_run is not None:return s.dungeon_run
    if (s.phase!='dungeon_active' or s.dungeon_id!=30000 or not s.population_test
        or not s.reward_test or s.reward_run_id is None):return None
    from types import SimpleNamespace
    from els_server.domain.dungeon_population import population
    import hashlib,json
    cached=getattr(s,'_quest_local_population',None)
    if cached is None or cached[0]!=s.gate_stage:
        stage=population(s.gate_stage)
        digest=hashlib.sha256(json.dumps(stage,sort_keys=True).encode()).hexdigest()
        cached=(s.gate_stage,stage,digest);s._quest_local_population=cached
    _,stage,digest=cached
    return SimpleNamespace(identity=30000,run_id=s.reward_run_id,stage=s.gate_stage,part=stage['part'],
                           current=stage,defeated=s.defeated_npcs,graph={'source_sha256':digest})

def handle(s,event,sequence):
    if event.event_id==0x202 and event.kind==0xfd and enabled(s):
        from els_server.domain.town_dialogue import handle as town_dialogue_handle
        town_reply=town_dialogue_handle(s,event,sequence)
        if town_reply is not None:return town_reply
        from els_server.domain.tutorial_dialogue import handle as dialogue_handle
        return dialogue_handle(s,event,sequence)
    if event.event_id!=0x202 or event.kind not in (0xee,0xfa,0xf4) or not enabled(s):return None
    qid=struct.unpack_from('>i',event.payload)[0] if len(event.payload)>=4 else 0
    if qid==53520 and not account_source_actor(s):return []
    def failure(result=wire.QUEST_REWARD_UNAVAILABLE):
        if qid==53520 and not account_source_actor(s):return []
        if event.kind==0xee:return [wire.accept_ack(result)]
        if event.kind==0xfa:return [initialization(s)]
        snapshot=s.account.get_inventory_snapshot()
        return [wire.reward_ack(qid,s.account.character(),s.account.get_location(),s.account.get_skills(),snapshot['balances'],snapshot['items'],result=result)]
    if (s.role!='game' or s.phase not in ('town_ready','dungeon_active') or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers!=(0,) or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return failure()
    try:
        request=wire.request(event.kind,event.payload)
        if qid==53520:
            from els_server.domain.equipment_chip_flow import current_lease
            if s.account.store.uid!=s.account.uid or not current_lease(s):return []
        kind={0xee:'accept',0xfa:'abandon',0xf4:'claim'}[event.kind]
        def encode(r):
            state=r['state']
            if kind=='accept':
                active=next((v for v in state['active'] if v['id']==qid),None)
                return [wire.accept_ack()]+([wire.accepted(active)] if active else [])
            if kind=='abandon':return [wire.initialization(state)]
            done=next(v for v in state['completed'] if v['id']==qid)
            result=wire.reward_ack(qid,r['character'],s.account.get_location(),r['slots'],r['balances'],r['items'],r['updates'],consumed=r['consumed'],replayed=r['replayed'],completed_at=done['completed_at'])
            from els_server.protocol.local_messages import skill_slots_initialization
            events=[result]
            if r.get('stage_changed'):
                from els_server.protocol.career_messages import stage_notice
                events.append(stage_notice(r['character']))
            # F0 is the original live new-task callback, distinct from the
            # absolute login snapshot. Encode it inside the reward transaction.
            events.append(wire.initialization(state))
            events.extend(wire.accepted(row) for row in r.get('accepted_after',()))
            events.append(skill_slots_initialization(r['slots'],s.account.uid,r['character']))
            if qid==54580:
                from els_server.protocol.artifact_messages import notice as artifact_notice
                events.append(artifact_notice(r['character'],not r['replayed']))
            return events
        location=('dungeon',s.dungeon_run.identity if s.dungeon_run else s.dungeon_id) if s.phase=='dungeon_active' else ('town',s.account.get_location()['map'])
        result=store(s).action(kind,request,s.shop_session_id+':quest:'+str(s.account.uid)+':'+str(sequence),encode,location=location)
        return result['events']
    except QuestIncomplete:return failure(wire.QUEST_REQUIREMENTS_NOT_MET)
    except InventoryFull:return failure(wire.QUEST_REWARD_BAG_FULL)
    except ValueError:return failure()

def observe(s,replies=()):
    if not enabled(s) or s.role!='game' or s.phase not in ('town_ready','dungeon_active'):return []
    notices=[];run=observed_run(s);starter_restored=False
    if s.phase=='town_ready' and any(e.event_id==0x201 and e.kind==0x228 and e.payload==bytes(4) for e in replies):
        # 228 follows successful scene parsing and committed saved location;
        # neither map selection nor a rejected request supplies this witness.
        from els_server.domain.tutorial_quests import restore_initialization
        events,starter_restored=restore_initialization(store(s),live=True)
        if starter_restored:notices.extend(events)
    # Recover the earlier snapshot-only28060 notification on validated scene
    # arrival. This reuses original F0/F3; it does not send F4 or alter SQL.
    arrived=(s.phase=='town_ready' and any(e.kind==0x228 and e.payload==bytes(4) for e in replies))
    loaded=(run is not None and run.identity==35250 and s.dungeon_substage_synced and any(e.kind==0xbd for e in replies))
    if arrived or loaded:
        announced=getattr(s,'_memory1_ready_announced',frozenset())
        for row in store(s).notification_snapshot()['active']:
            if row['id']!=28060:continue
            from els_server.domain.seal_quests import quest_catalog,target
            q=quest_catalog().quest(28060)
            key=(str(s.account.store.path),s.account.uid,row['id'],row['generation'])
            if key in announced or not q.get('m_bAutoClearQuest') or s.account.character()['unit_type']!=15:continue
            if not all(row['objectives'][sub['m_iID']]>=target(sub) for sub in quest_catalog().objectives(28060)):continue
            if not (loaded or s.account.get_location()['map']==20014):continue
            notices.extend([wire.accepted(row),wire.progress([row])])
            announced=announced|{key};s._memory1_ready_announced=announced
    owner=(str(s.account.store.path),s.account.uid)
    passive=getattr(s,'_quest_passive_kinds',None)
    if starter_restored or passive is None or passive[0]!=owner or any(e.kind in (0xf0,0x2b,0xf5) for e in replies):
        passive=(owner,store(s).passive_objective_kinds());s._quest_passive_kinds=passive
    if any(e.kind==0xf0 for e in replies):
        s._quest_discovery_cursor=None;s._quest_town_cursor=None
        s._quest_discovery_epoch=getattr(s,'_quest_discovery_epoch',0)+1
    if s.phase=='dungeon_active':s._quest_town_cursor=None
    else:s._quest_discovery_cursor=None
    # Only admitted, fully loaded dungeon state supplies visit/discovery
    # evidence. Map-panel selection and unvalidated client counters do not.
    if 26 in passive[1] and run is not None and s.phase=='dungeon_active' and s.dungeon_substage_synced:
        s._quest_town_cursor=None
        owner=(str(s.account.store.path),s.account.uid)
        cursor=(owner,run.run_id,run.stage,run.part)
        if getattr(s,'_quest_discovery_cursor',None)!=cursor:
            proof=(run.run_id+':'+run.graph['source_sha256']+':'+str(run.stage)+':'+str(run.part)).encode()
            base='discovery:'+run.run_id+':'+str(run.stage)+':'+str(run.part)+':'+str(getattr(s,'_quest_discovery_epoch',0))
            event=dict(kind='visit_dungeon',dungeon=run.identity,level=s.account.character()['level'])
            notices+=store(s).record(base,event,proof)
            s._quest_discovery_cursor=cursor
    elif 24 in passive[1] and s.phase=='town_ready':
        owner=(str(s.account.store.path),s.account.uid)
        town=s.account.get_location()['map'];cursor=(owner,town)
        if getattr(s,'_quest_town_cursor',None)!=cursor:
            import uuid
            token=uuid.uuid4().hex
            notices+=store(s).record('town:'+token,dict(kind='visit_town',town=town,dungeon=0,level=s.account.character()['level']),token.encode())
            s._quest_town_cursor=cursor
        s._quest_discovery_cursor=None
    if 27 in passive[1] and run is not None:
        from els_server.domain.tutorial_memory8_finale import encounter
        witness=encounter(s,run,store(s).snapshot())
        if witness is not None:notices+=store(s).record(*witness)
    if run is not None:
        seen=getattr(s,'_quest_seen_events',None)
        if seen is None:s._quest_seen_events=seen=set()
        levels=getattr(s,'_quest_run_levels',None)
        if levels is None:s._quest_run_levels=levels={}
        if run.run_id not in levels:levels[run.run_id]=s.account.character()['level']
        level=levels[run.run_id];base=run.run_id+':'+str(run.stage)+':'+str(run.part)
        for npc in run.current['npcs']:
            key=npc['key'];identity=base+':kill:'+str(key)
            if npc.get('team',1)==0 or npc.get('ally') or key not in run.defeated or identity in seen:continue
            tutorial_quest=None
            if not npc['active']:
                from els_server.domain.tutorial_dialogue import inactive_quest
                tutorial_quest=inactive_quest(run.identity,npc['template'])
                if tutorial_quest is None:continue
            event=dict(kind='kill',dungeon=run.identity,npc=npc['template'],level=level)
            if tutorial_quest is not None:event['tutorial_quest']=tutorial_quest
            notices+=store(s).record(identity,event,run.defeated[key]);seen.add(identity)
        identity=run.run_id+':clear'
        if s.clear_notified and identity not in seen:
            # Only committed receipts advance tasks; local ranks carry their
            # policy identity in the matching authoritative assessment.
            if s.reward_test and s.reward_receipt is not None:
                from els_server.storage.local_clear_rules import lookup as local_assessment
                committed=local_assessment(s.account.store.path,s.account.uid,s.reward_receipt['run_id'])
                event=dict(kind='clear',dungeon=run.identity,level=level,rank=committed['assessment']['rank'] if committed else None)
                proof=(run.run_id+':'+run.graph['source_sha256']).encode()
                notices+=store(s).record(identity,event,proof);seen.add(identity)
    # D9 and career snapshots carry empty legacy quest vectors. Restore the
    # authoritative task state immediately after those existing messages.
    if not starter_restored and any(e.kind in (0xd9,0x29f) for e in replies):
        state=store(s).snapshot()
        if state['active'] or state['completed']:notices.append(wire.initialization(state))
    # Inventory writers already send their ordinary acknowledgements. Refresh
    # collection, level and Artifact counters afterward, including decreases after use/discard,
    # locking and expiration. No inventory writer needs a quest dependency.
    # The first call primes a per-character view; idle/no-reply packets do not
    # open another database connection. New tasks have their own F0/2B state.
    owner=(str(s.account.store.path),s.account.uid)
    previous=getattr(s,'_quest_collection_view',None)
    if replies or previous is None or previous[0]!=owner:
        from els_server.domain.seal_quests import quest_catalog
        rows=store(s).collection_snapshot();current={};changed=[]
        old=previous[1] if previous is not None and previous[0]==owner else {}
        for row in rows:
            signature=(row['generation'],{sub['m_iID']:row['objectives'][sub['m_iID']] for sub in quest_catalog().objectives(row['id']) if sub['m_eClearType'] in (3,31,80,81,110)})
            current[row['id']]=signature
            if row['id'] in old and old[row['id']]!=signature:changed.append(row)
        if changed:notices.append(wire.progress(changed))
        s._quest_collection_view=(owner,current)
    return notices
