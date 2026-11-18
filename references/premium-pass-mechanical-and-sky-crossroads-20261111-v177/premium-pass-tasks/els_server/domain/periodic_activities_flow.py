"""Restore current task/pass views through the original stable-town lifecycle."""
import sqlite3,struct,time
from contextlib import closing
from els_server.domain import periodic_activities as rules
from els_server.protocol import season_pass_messages as wire

def handle(session,event,sequence):
    if (event.event_id,event.kind)==(0x202,0xd01):
        from els_server.domain.adventure_checklist_flow import handle as save_checklist
        return save_checklist(session,event,sequence)
    if (event.event_id,event.kind)==(0x202,0x80f):
        return premium_purchase(session,event,sequence)
    if event.event_id!=0x202 or event.kind not in(0x6fb,0xa4d,0xa4f,0xa63,0xbeb):return None
    if event.kind==0xbeb:return daily_query(session,event,sequence)
    if event.kind==0x6fb:return weekly_accept(session,event,sequence)
    if event.kind==0xa63:return weekly_query(session,event,sequence)
    if event.kind==0xa4f:return reward_claim(session,event,sequence)
    category,display=wire.attendance_request(event.payload)
    from els_server.domain.quest_flow import collection_source_guard
    from els_server.storage.seal_quests import QuestState,write_transaction
    from els_server.storage.season_pass import attendance,state
    from els_server.protocol.quest_messages import progress
    from els_server.protocol.protocol_codec import encode_event
    if (event.performers not in((),(0,))or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff
        or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):
        return [wire.attendance_ack(category,False,result=2)]
    try:
        guard=collection_source_guard(session)
        store=QuestState(session.account.store.path,session.account.uid,
                         account_id=session.account.account_id,account_source_guard=guard)
        now=int(time.time())
        with closing(sqlite3.connect(store.path,timeout=10))as db,write_transaction(db):
            guard(db);changed=attendance(store,db,category,now)
            events=[wire.attendance_ack(category,display)]
            if changed:events.append(progress(changed))
            events.extend(wire.status(state(db,store.account_id,int(cat),now))for cat in rules.catalog()['passes'])
            for answer in events:encode_event(answer)
            guard(db)
        return events
    except ValueError:return [wire.attendance_ack(category,False,result=2)]

def premium_purchase(session,event,sequence):
    from els_server.domain.season_pass_shop import SKUS
    from els_server.protocol.shop_messages import ed_purchase_ack,ed_purchase_request
    try:
        products=ed_purchase_request(event.payload)
    except ValueError:
        return None
    if not any(sku in SKUS for sku,_ in products):return None

    from els_server.domain.quest_flow import collection_source_guard
    from els_server.storage.seal_quests import QuestState,write_transaction
    from els_server.storage.season_pass import activate_premium
    from els_server.protocol.quest_messages import accepted
    from els_server.protocol.protocol_codec import encode_event
    from hashlib import sha256
    try:
        if (len(products)!=1 or products[0][1]!=1 or not session.shop_test or not session.ed_catalog_loaded
            or event.performers not in((),(0,)) or event.uid!=2**64-1 or event.target_uid!=2**64-1
            or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):
            raise ValueError('Buy one Magmelia Express activation in the current ED shop')
        guard=collection_source_guard(session)
        actor=session.account
        store=QuestState(actor.store.path,actor.uid,account_id=actor.account_id,account_source_guard=guard)
        operation=f'{session.shop_session_id}:pass-purchase:{store.uid}:{sequence}'
        category=SKUS[products[0][0]]
        with closing(sqlite3.connect(store.path,timeout=10)) as db,write_transaction(db):
            now=int(time.time())
            ed,value,added=activate_premium(store,db,category,operation,sha256(event.payload).hexdigest(),now)
            events=[ed_purchase_ack(0,[],ed)]
            # Add the new tasks through the live quest callback before refreshing the tab.
            events.extend(accepted(row) for row in added)
            events.append(wire.status(value))
            for answer in events:encode_event(answer)
            guard(db)
    except ValueError:
        return [ed_purchase_ack(-1,[],0)]
    previous=getattr(session,'_periodic_activities_restored',None)
    if previous is not None and previous[0][:3]==(session.shop_session_id,store.account_id,store.uid):
        previous[2].update((row['id'],row['generation']) for row in added)
    from els_server.domain.season_pass_online import bind
    bind(session,added)
    return events

def weekly_accept(session,event,sequence):
    from els_server.domain.quest_flow import collection_source_guard
    from els_server.storage.seal_quests import QuestState
    from els_server.protocol.quest_messages import accepted
    # Native 3046250 initializes only the first dword; 1107EA0 copies
    # both. The observed second dword is stack residue, never request data.
    if(len(event.payload)!=8 or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff
       or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):
        return [wire.weekly_accept_ack(187)]
    qid=struct.unpack_from('>i',event.payload)[0]
    if not rules.weekly(qid):return [wire.weekly_accept_ack(187)]
    try:
        guard=collection_source_guard(session)
        store=QuestState(session.account.store.path,session.account.uid,
                         account_id=session.account.account_id,account_source_guard=guard)
        operation=session.shop_session_id+':weekly:'+str(session.account.uid)+':'+str(sequence)
        def encode(result):
            row=next((r for r in result['state']['active']if r['id']==qid),None)
            if row is None and not result['replayed']:raise ValueError('Missing accepted weekly row')
            return [wire.weekly_accept_ack()]+([accepted(row)]if row is not None else [])
        result=store.action('accept',dict(quest=qid,npc=rules.definition(qid)['m_eStartNPCID']),operation,encode,
                            location=('town',session.active_map))
        return result['events']
    except ValueError:return [wire.weekly_accept_ack(187)]

def reward_claim(session,event,sequence):
    from els_server.domain.quest_flow import collection_source_guard
    from els_server.storage.seal_quests import QuestState,write_transaction,load_character,current_slots
    from els_server.storage.season_pass import claim
    from els_server.storage.inventory_state import load_items,InventoryFull
    from els_server.storage.reward_state import validate_balances
    from els_server.protocol.dungeon_messages import return_user_sync
    from els_server.protocol.protocol_codec import encode_event
    import hashlib
    try:
        category,claims,choice=wire.reward_request(event.payload)
        if(event.performers not in((),(0,))or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff
           or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Pass reward request actor')
        guard=collection_source_guard(session);location=session.account.get_location();now=int(time.time())
        store=QuestState(session.account.store.path,session.account.uid,
                         account_id=session.account.account_id,account_source_guard=guard)
        operation=session.shop_session_id+':pass:'+str(session.account.uid)+':'+str(sequence)
        with closing(sqlite3.connect(store.path,timeout=10))as db,write_transaction(db):
            guard(db)
            updates,plan,value=claim(store,db,category,claims,operation,hashlib.sha256(event.payload).hexdigest(),now,choice=choice)
            events=[]
            if updates:
                character=load_character(db,store.uid,store.account_id)
                balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(store.uid,)).fetchone())
                events.append(return_user_sync(location,current_slots(db,character),balances,load_items(db,store.uid),character,inventory_updates=updates))
            events.extend((wire.status(value),wire.reward_ack(plan)))
            for answer in events:encode_event(answer)
            guard(db)
        return events
    except InventoryFull:return [wire.reward_ack(result=165)]
    except ValueError:return [wire.reward_ack(result=187)]

def _query_actor(session):
    from els_server.domain.quest_flow import enabled
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.storage.item_actor import require_active_character
    # Native list queries can occur between225 and227. The original economic
    # writers still require stable-town admission.
    if(not enabled(session)or session.role!='game'or session.phase not in('square_accepted','town_ready','dungeon_active')
       or getattr(session,'released',False)or not current_lease(session)
       or session.account.uid!=session.account.store.uid):raise ValueError('Periodic current account reader')
    refs=(session.account,session.account.store,session.account.characters)
    actor=(session.shop_session_id,session.account.account_id,session.account.uid,session.phase)
    def guard(db):
        if(not current_lease(session)or getattr(session,'released',False)
           or actor!=(session.shop_session_id,session.account.account_id,session.account.uid,session.phase)
           or any(a is not b for a,b in zip(refs,(session.account,session.account.store,session.account.characters)))):
            raise ValueError('Periodic reader actor generation changed')
        require_active_character(db,session.account.uid)
    return guard

def daily_query(session,event,sequence):
    from els_server.storage.ariel_daily_special import notification
    from els_server.protocol.protocol_codec import Event,encode_event
    if(event.payload or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff
       or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0
       or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Daily reward list request')
    guard=_query_actor(session);actor=session.account;now=int(time.time())
    with closing(sqlite3.connect(actor.store.path,timeout=10))as db:
        db.execute('BEGIN');guard(db)
        snapshot=notification(db,actor.account_id,actor.uid,now)
        # BDBD60 replaces the whole map; share the existing21-row provider.
        # Its result field does not gate replacement, so failure must not
        # synthesize an empty success/placeholder map.
        answer=Event(0x201,kind=0xbec,payload=bytes(4)+snapshot.payload)
        encode_event(answer);guard(db)
    return [answer]

def weekly_query(session,event,sequence):
    from els_server.storage.seal_quests import _state,load_character
    from els_server.storage import periodic_quest_scope as scope
    from els_server.domain.seal_quests import quest_catalog,target
    from els_server.protocol.protocol_codec import encode_event
    if (event.payload or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff
        or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0
        or type(sequence)is not int or not 1<=sequence<2**32):return [wire.weekly_list([],result=2)]
    try:
        guard=_query_actor(session);now=int(time.time())
        with closing(sqlite3.connect(session.account.store.path,timeout=10))as db:
            db.execute('BEGIN')
            guard(db)
            # Town startup can query before the client has a visible actor.
            if load_character(db,session.account.uid,session.account.account_id,identity_only=True)['level']<99:
                answer=wire.weekly_list([],limit=0)
            else:
                weekly_ids=rules.catalog()['weekly_ids']
                saved=_state(db,session.account.uid,None,now=now,progress_only=True,quest_ids=set(weekly_ids))
                active={r['id']:r for r in saved['active']}
                done={q for q,at in scope.completed_rows(db,session.account.uid)if rules.visible(q,at,now,active=False)}
                rows=[]
                for index,qid in enumerate(weekly_ids):
                    state=0
                    if qid in done:state=3
                    elif qid in active:
                        counts=active[qid]['objectives']
                        state=2 if all(counts[s['m_iID']]>=target(s)for s in quest_catalog().objectives(qid))else 1
                    rows.append((qid,index,state))
                answer=wire.weekly_list(rows)
            encode_event(answer);guard(db)
        return [answer]
    except ValueError:return [wire.weekly_list([],result=2)]

def restore(session,*,observed_level=None,refresh_active=()):
    from els_server.domain.quest_flow import collection_source_guard
    from els_server.storage.seal_quests import QuestState,_state,load_character,write_transaction
    from els_server.storage.inventory_state import load_items
    from els_server.storage.season_pass import restore as restore_pass,state
    from els_server.protocol.quest_messages import accepted,initialization
    from els_server.protocol.protocol_codec import encode_event
    now=int(time.time())
    period_key=(session.shop_session_id,session.account.account_id,session.account.uid,
                rules.period(now,1),rules.period(now,3))
    previous=getattr(session,'_periodic_activities_restored',None)
    if previous is not None and previous[0]==period_key:
        if observed_level is None or previous[1]==(observed_level>=rules.PASS_MIN_LEVEL):
            return []
    guard=collection_source_guard(session)
    store=QuestState(session.account.store.path,session.account.uid,
                     account_id=session.account.account_id,account_source_guard=guard)
    with closing(sqlite3.connect(store.path,timeout=10))as db,write_transaction(db):
        guard(db)
        character=load_character(db,store.uid,store.account_id,identity_only=True)
        restore_pass(store,db,now,character=character)
        quests=_state(db,store.uid,load_items(db,store.uid),now=now)
        events=[initialization(quests)]
        pass_generations={row['id']:row['generation'] for row in quests['active'] if rules.pass_task(row['id'])}
        refresh=set(refresh_active)
        if previous is not None and previous[0][:3]==period_key[:3]:
            # 2B remains the complete login projection. A live reset or level
            # change also needs F0 for each newly active generation.
            refresh.update(qid for qid,generation in pass_generations.items()
                           if previous[2].get(qid)!=generation)
        events.extend(accepted(row) for row in quests['active'] if row['id'] in refresh)
        for category in (rules.catalog()['passes']if rules.active_season(now)is not None else ()):
            value=state(db,store.account_id,int(category),now)
            events.extend((wire.period(value),wire.status(value)))
        for event in events:encode_event(event)
        guard(db)
    session._periodic_activities_restored=(period_key,character['level']>=rules.PASS_MIN_LEVEL,pass_generations)
    session._quest_passive_kinds=None
    from els_server.domain.season_pass_online import bind
    bind(session,quests['active'])
    return events
