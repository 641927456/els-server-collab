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
            return restore_initialization(store(s),defer_starter_arrival=s.enter_dungeon)[0]
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

def collection_source_guard(s):
    # A finite new economic operation binds the exact current native scene,
    # actor graph and session generation before waiting on its SQL writer.
    def capture():
        if (not account_source_actor(s) or s.phase!='town_ready' or not s.enter_town
            or s.dungeon_return_pending or not {0x225,0x227}.issubset(s.completed)
            or s.pending_map!=s.active_map or s.account.get_location()['map']!=s.active_map):raise ValueError('Collection stable scene required')
        return ((s.account,s.account.store,s.account.characters,getattr(s.account,'root',None),getattr(s,'application',None)),
                (s.shop_session_id,s.account.account_id,s.account.uid,s.phase,s.active_map,s.pending_map))
    captured=capture()
    def guard(db):
        account_source_guard(s,db)
        refs,values=capture()
        if values!=captured[1] or any(a is not b for a,b in zip(refs,captured[0])):raise ValueError('Collection actor generation changed')
        if db.execute('SELECT town FROM location WHERE uid=?',(s.account.uid,)).fetchone()!=(s.active_map,):raise ValueError('Collection SQL scene mismatch')
    return guard

def handle(s,event,sequence):
    if event.event_id==0x202 and event.kind==0xfd and enabled(s):
        from els_server.domain.guild_task_flow import dialogue as guild_dialogue
        guild_reply=guild_dialogue(s,event,sequence)
        if guild_reply is not None:return guild_reply
        from els_server.domain.account_fishing25600 import handle as fishing_handle
        fishing_reply=fishing_handle(s,event,sequence)
        if fishing_reply is not None:return fishing_reply
        from els_server.domain.town_dialogue import handle as town_dialogue_handle
        town_reply=town_dialogue_handle(s,event,sequence)
        if town_reply is not None:return town_reply
        from els_server.domain.tutorial_dialogue import handle as dialogue_handle
        return dialogue_handle(s,event,sequence)
    if event.event_id!=0x202 or event.kind not in (0xee,0xfa,0xf4) or not enabled(s):return None
    qid=struct.unpack_from('>i',event.payload)[0] if len(event.payload)>=4 else 0
    if qid in (26770,25600,25601,25602,26780,37100,53500,53510,53520,53530,54600,52700) and not account_source_actor(s):return []
    housing_binding=None
    if qid==26770:
        housing_binding=(s.account,s.account.store,s.account.characters,s.account.root,getattr(s,'application',None),s.account.uid,s.account.account_id,s.shop_session_id,s.phase,s.active_map,s.pending_map)
    guild_reply_guard=None
    if qid==35630:
        from els_server.domain.guild_license_flow import reply_capture, guarded_reply
        guild_reply_guard=reply_capture(s)
        if guild_reply_guard is None:return []
    fishing_binding=None
    if qid in(25600,25601,25602):
        from els_server.domain.account_fishing_tasks import actor_binding,current_actor,actor_guard
        try:fishing_binding=actor_binding(s)
        except(ValueError,AttributeError,KeyError,TypeError):return []
    skip_binding=None
    def current_skip_binding():
        run=s.dungeon_run
        return (s.account,s.account.store,s.account.uid,s.account.account_id,s.shop_session_id,s.phase,
                s.active_map,s.account.get_location()['map'],s.dungeon_id,run,None if run is None else run.identity)
    def failure(result=wire.QUEST_REWARD_UNAVAILABLE):
        if qid==35630:return guarded_reply(guild_reply_guard,lambda:failure_events(result))
        return failure_events(result)
    def failure_events(result):
        if housing_binding is not None:
            def still_housing_actor():
                if not account_source_actor(s):return False
                current=(s.account,s.account.store,s.account.characters,s.account.root,getattr(s,'application',None),s.account.uid,s.account.account_id,s.shop_session_id,s.phase,s.active_map,s.pending_map)
                return all(a is b for a,b in zip(housing_binding[:5],current[:5])) and housing_binding[5:]==current[5:]
            if not still_housing_actor():return []
            if event.kind==0xee:events=[wire.accept_ack(result)]
            elif event.kind==0xfa:events=[initialization(s)]
            else:
                snapshot=s.account.get_inventory_snapshot()
                events=[wire.reward_ack(qid,s.account.character(),s.account.get_location(),s.account.get_skills(),snapshot['balances'],snapshot['items'],result=result)]
            from els_server.protocol.protocol_codec import encode_event
            for reply in events:encode_event(reply)
            return events if still_housing_actor() else []
        if fishing_binding is not None:
            if not current_actor(s,fishing_binding):return []
            try:
                if event.kind==0xee:events=[wire.accept_ack(result)]
                elif event.kind==0xfa:events=[initialization(s)]
                else:
                    snapshot=s.account.get_inventory_snapshot()
                    events=[wire.reward_ack(qid,s.account.character(),s.account.get_location(),s.account.get_skills(),snapshot['balances'],snapshot['items'],result=result)]
                from els_server.protocol.protocol_codec import encode_event
                for reply in events:encode_event(reply)
                return events if current_actor(s,fishing_binding)else[]
            except(ValueError,AttributeError,KeyError,TypeError):return []
        if skip_binding is not None and (not account_source_actor(s) or current_skip_binding()!=skip_binding):return []
        if qid in (26770,25600,25601,25602,26780,37100,53500,53510,53520,53530,54600,52700) and not account_source_actor(s):return []
        if event.kind==0xee:return [wire.accept_ack(result)]
        if event.kind==0xfa:return [initialization(s)]
        snapshot=s.account.get_inventory_snapshot()
        return [wire.reward_ack(qid,s.account.character(),s.account.get_location(),s.account.get_skills(),snapshot['balances'],snapshot['items'],result=result)]
    if (s.role!='game' or s.phase not in ('town_ready','dungeon_active') or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers!=(0,) or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return failure()
    try:
        request=wire.request(event.kind,event.payload)
        if qid in (53520,52700):
            from els_server.domain.equipment_chip_flow import current_lease
            if s.account.store.uid!=s.account.uid or not current_lease(s):return []
        kind={0xee:'accept',0xfa:'abandon',0xf4:'claim'}[event.kind]
        from els_server.domain.epic_skip import requested as skip_requested
        selected_store=store(s)
        if qid==35630:
            from els_server.domain.guild_task_flow import guarded_store
            selected_store=guarded_store(s)
        if fishing_binding is not None:selected_store.account_source_guard=actor_guard(s,fishing_binding)
        if kind=='claim' and skip_requested(request):
            if not account_source_actor(s):return []
            skip_binding=current_skip_binding()
            def guarded_skip(db):
                if fishing_binding is not None:actor_guard(s,fishing_binding)(db)
                if not account_source_actor(s) or current_skip_binding()!=skip_binding:
                    raise ValueError('Retired Epic skip actor/session')
                account_source_guard(s,db)
            selected_store=QuestState(s.account.store.path,s.account.uid,account_id=s.account.account_id,account_source_guard=guarded_skip)
        def encode(r):
            state=r['state']
            if kind=='accept':
                active=next((v for v in state['active'] if v['id']==qid),None)
                events=[wire.accept_ack()]+([wire.accepted(active)] if active else [])
                from els_server.domain.tutorial_memory8_finale import ready_hidden_receipt
                ready=ready_hidden_receipt([active] if active else [])
                if ready:events.append(wire.progress(ready))
                return events
            if kind=='abandon':return [wire.initialization(state)]
            done=next(v for v in state['completed'] if v['id']==qid)
            # The original2B consumer resets live tutorial guide state. These
            # four source town quests use F5+F0; cold login still uses2B.
            lithia_town_live=(qid in (28000,28010,28020,28030)
                and r['character']['unit_type']==15 and s.phase=='town_ready'
                and s.active_map==20014 and s.account.get_location()['map']==20014)
            # F5's final boolean FORCES its native completion callback. A
            # stored replay is not permission to replay the scene without a wait.
            result=wire.reward_ack(qid,r['character'],s.account.get_location(),r['slots'],r['balances'],r['items'],r['updates'],consumed=r['consumed'],replayed=False if lithia_town_live else r['replayed'],completed_at=done['completed_at'])
            from els_server.protocol.local_messages import skill_slots_initialization
            events=[result]
            if r.get('stage_changed'):
                from els_server.protocol.career_messages import stage_notice
                events.append(stage_notice(r['character']))
            # F0 is the original live new-task callback, distinct from the
            # absolute login snapshot. Encode it inside the reward transaction.
            if not lithia_town_live:events.append(wire.initialization(state))
            events.extend(wire.accepted(row) for row in r.get('accepted_after',()))
            # Original F3 triggers native AutoClearQuest -> A02D -> F4.
            # Construct it inside the parent's claim transaction, never claim here.
            from els_server.domain.tutorial_memory8_finale import ready_hidden_receipt
            ready=ready_hidden_receipt(r.get('accepted_after',()))
            if ready:events.append(wire.progress(ready))
            # Rebuild from the current committed career on first success and
            # completed-receipt retries; never repeat a transition or reward.
            if r.get('class_changed') and not r['replayed']:
                from els_server.protocol.career_messages import career_notice
                events.append(career_notice(r['character'],s.account.get_location(),r['slots'],r['balances'],r['items']))
            if r.get('career_refresh') or r.get('stage_changed'):
                # Same-class stage changes and receipt replays restore current
                # skills without29F's ordinary career auto-entry side effects.
                from els_server.protocol.career_messages import current_skill_notices
                rebuild=bool(r.get('stage_changed'))and not r['replayed']
                events.extend(current_skill_notices(r['character'],r['slots'],rebuild=rebuild))
            events.append(skill_slots_initialization(r['slots'],s.account.uid,r['character']))
            if qid==52700 and 'el_search_collection' in r['character']:
                from els_server.protocol.el_search_collection_messages import notice as collection_notice
                events.append(collection_notice(r['character']['el_search_collection']))
            if qid==54580:
                from els_server.protocol.artifact_messages import notice as artifact_notice
                events.append(artifact_notice(r['character'],not r['replayed']))
            return events
        location=('dungeon',s.dungeon_run.identity if s.dungeon_run else s.dungeon_id) if s.phase=='dungeon_active' else ('town',s.account.get_location()['map'])
        if qid in (52700,26770):selected_store.account_source_guard=collection_source_guard(s)
        result=selected_store.action(kind,request,s.shop_session_id+':quest:'+str(s.account.uid)+':'+str(sequence),encode,location=location)
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
    # Existing active hidden receipt needs live F0/F3 after a validated arrival;
    # a login 2B alone does not invoke the current F3 auto-claim callback.
    # The exact generation is announced once per current authenticated session.
    if (arrived or any(e.kind==0xf0 for e in tuple(replies)+tuple(notices))) and account_source_actor(s):
        from els_server.domain.tutorial_memory8_finale import ready_hidden_receipt
        announced=getattr(s,'_hidden54600_ready_announced',frozenset())
        for row in ready_hidden_receipt(store(s).notification_snapshot()['active']):
            key=(str(s.account.store.path),s.account.account_id,s.account.uid,row['id'],row['generation'])
            if key in announced:continue
            progress=wire.progress([row])
            if not any(e.kind==0xf3 and e.payload==progress.payload for e in tuple(replies)+tuple(notices)):
                accepted=wire.accepted(row)
                from els_server.protocol.protocol_codec import encode_event
                encode_event(accepted);encode_event(progress)
                notices.extend([accepted,progress])
            announced=announced|{key};s._hidden54600_ready_announced=announced
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
            from els_server.domain.lithia_first_entry import record_visit
            notices+=record_visit(s,run,store(s),base,event,proof)
            s._quest_discovery_cursor=cursor
    elif 24 in passive[1] and s.phase=='town_ready':
        owner=(str(s.account.store.path),s.account.uid)
        town=s.account.get_location()['map'];cursor=(owner,town)
        if getattr(s,'_quest_town_cursor',None)!=cursor:
            import uuid
            token=uuid.uuid4().hex
            from els_server.domain.tutorial_quests import first_arrival_pending,STARTERS
            selected_store=store(s)
            if account_source_actor(s) and not first_arrival_pending(selected_store):
                arrival={};qid,starter_town=STARTERS[s.account.character()['unit_type']]
                def validate_arrival(db):
                    account_source_guard(s,db)
                    if (s.phase!='town_ready' or s.active_map!=town
                        or not {0x225,0x227}.issubset(s.completed)
                        or db.execute('SELECT town FROM location WHERE uid=?',(s.account.uid,)).fetchone()!=(town,)):
                        raise ValueError('Quest arrival scene changed')
                    arrival['db']=db
                    arrival['before']=db.execute('SELECT accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(s.account.uid,qid)).fetchone() if town==starter_town else None
                def prepare_arrival(events,replayed):
                    # The full original F0 seeds the right-side task name;
                    # F3 then carries the actual committed objective edge.
                    # No F4/F5, reward or forced main-window open is added.
                    import json
                    before=arrival.get('before')
                    if events and before is not None and not any(json.loads(before[2]).values()):
                        after=arrival['db'].execute('SELECT accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(s.account.uid,qid)).fetchone()
                        if after is not None and after[:2]==before[:2] and all(json.loads(after[2]).values()):
                            row=dict(id=qid,owner=s.account.uid,accepted_at=after[0],generation=after[1],objectives={int(k):v for k,v in json.loads(after[2]).items()})
                            events=[wire.accepted(row)]+events
                    from els_server.protocol.protocol_codec import encode_event
                    for event in events:encode_event(event)
                    return events
                notices+=selected_store.record('town:'+token,dict(kind='visit_town',town=town,dungeon=0,level=s.account.character()['level']),token.encode(),validate=validate_arrival,prepare=prepare_arrival)
                s._quest_town_cursor=cursor
        s._quest_discovery_cursor=None
    if 27 in passive[1] and run is not None:
        from els_server.domain.mainline_find_npc import observe as observe_mainline_find
        notices+=observe_mainline_find(s,run,replies,store(s))
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
            signature=(row['generation'],{sub['m_iID']:row['objectives'][sub['m_iID']] for sub in quest_catalog().objectives(row['id']) if sub['m_eClearType'] in (3,31,38,80,81,110,121)})
            current[row['id']]=signature
            if row['id'] in old and old[row['id']]!=signature:changed.append(row)
        if changed:notices.append(wire.progress(changed))
        s._quest_collection_view=(owner,current)
    return notices
