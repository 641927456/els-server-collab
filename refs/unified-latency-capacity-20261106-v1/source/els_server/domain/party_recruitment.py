"""Ephemeral native ordinary recruitment over the existing shared PartyManager.

All mutations run on Application's worker, after complete wire preflight and
current actor revalidation. Recruitment never writes character/account saves.
"""
import struct
from els_server.protocol import party_recruitment_messages as wire
from els_server.protocol import social_messages as social
from els_server.domain.avatar_set_flow import context,validate
from els_server.domain.dungeon_equipment_loot_flow import current_lease
from els_server.domain.party_commands import _prepared_boxes


def actor(world,s):
    app=getattr(s,'application',None)
    if (app is None or not current_lease(s) or app.world is not world
        or not app.registry.enabled(s.account.account_id)):raise ValueError('Recruitment current enabled lease')
    captured=context(s);c=s.account.character()
    if c['uid']!=s.account.uid or c.get('pending_delete'):raise ValueError('Recruitment current character')
    return captured


def lease_binding(s):
    a=s.account
    return ((s,s.identity,a,a.root,a.store,a.characters,s.application,s.application.world),
        (s.identity['id'],a.account_id,a.uid,str(a.store.path),s.shop_session_id,s.client_build))


def same_binding(s,binding):
    try:refs,values=lease_binding(s)
    except (AttributeError,KeyError,TypeError):return False
    return values==binding[1] and len(refs)==len(binding[0]) and all(a is b for a,b in zip(refs,binding[0]))


def waiting(world,party):
    from els_server.domain.normal_party import ordinary
    if (world.parties.get(party['id']) is not party or not ordinary(party)
        or party['run'] is not None or not 1<=len(party['members'])<=4
        or party['leader'] not in party['members']):raise ValueError('Recruitment ordinary waiting party')
    if any(world.party_of.get(m) is not party or world.dungeons.room(m) is not None for m in party['members']):
        raise ValueError('Recruitment current roster')
    return {m:actor(world,m) for m in party['members']}


def source(party,*,single=False):
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import raid_definition
    from els_server.domain.region_quests import account_dungeon_allowed
    from els_server.game_data import client_data
    identity=party['dungeon']
    if not route_catalog().supports(identity):raise ValueError('Recruitment unsupported route')
    definition=client_data().dungeon(identity)
    maximum=party.get('recruitment',{}).get('maximum',4)
    minimum=definition.get('m_MinPlayerCount',1)
    if (not route_catalog().supports(identity) or route_catalog().entry_identity(identity)!=identity
        or raid_definition(identity) is not None or party.get('difficulty',0) or party.get('mode',0)
        or 1 in definition.get('DUNGEON_CHECK_CONDITION',{}).values()
        or type(minimum) is not int or not max(2,minimum)<=maximum<=min(4,definition.get('m_MaxPlayerCount',4))
        or len(party['members'])>maximum
        or not all(account_dungeon_allowed(m.account,identity) for m in party['members'])):
        raise ValueError('Recruitment source or admission')


def signature(world):
    # Include object identities and all new business state, so encode callbacks
    # cannot replace an equal actor/room/mailbox or change the captured source.
    return (id(world.members),id(world.parties),id(world.party_of),id(world.invitations),world.next_party,
        tuple((id(s),key,id(s.mailbox),tuple(s.mailbox.messages),tuple(s.mailbox.moves.items()),s.mailbox.bytes)
            for s,key in world.members.items()),
        tuple((id(s),id(v),repr(v)) for s,v in world.invitations.items()),
        tuple((id(s),id(p)) for s,p in world.party_of.items()),
        tuple((key,id(p),id(p['leader']),tuple(map(id,p['members'])),frozenset(map(id,p['ready'])),
            p['dungeon'],p.get('difficulty',0),p.get('mode',0),id(p['run']),repr(p.get('recruitment')))
            for key,p in world.parties.items()),
        tuple((key,id(v),id(v['party']),id(v['leader']),id(v['applicant']),v['uid'],v['wire'],
            tuple(map(id,v['binding'][0])),v['binding'][1],tuple(map(id,v['leader_binding'][0])),v['leader_binding'][1])
            for key,v in world.recruitment_candidates.items()))


def prepare(world,actors,deliveries,response):
    before=signature(world);boxes=_prepared_boxes(deliveries,response)
    if signature(world)!=before:raise ValueError('Recruitment source changed while encoding')
    for s,captured in actors.items():
        validate(s,captured)
        if (not current_lease(s) or not s.application.registry.enabled(s.account.account_id)
            or s.account.character().get('pending_delete')):
            raise ValueError('Recruitment lease changed while encoding')
    return boxes


def commit_boxes(boxes):
    for s,box in boxes.items():s.mailbox=box


def published(world,party):
    if not party.get('recruitment',{}).get('published'):return False
    try:waiting(world,party);source(party,single=True)
    except ValueError:return False
    return True


def valid_candidate(world,record):
    p=record['party'];s=record['applicant']
    if (not published(world,p) or p['leader'] is not record['leader']
        or s in world.party_of or s.account.uid!=record['uid']
        or not same_binding(s,record['binding'])
        or not same_binding(p['leader'],record['leader_binding'])):return False
    try:actor(world,s);source({**p,'members':[*p['members'],s]})
    except ValueError:return False
    return True


def candidate_rows(world,party,records=None):
    records=world.recruitment_candidates if records is None else records
    return [v['wire'] for v in records.values() if v['party'] is party and valid_candidate(world,v)]


def removal_plan(world,*,party=None,applicant=None):
    # Used inside an existing normal join/change command's encoding batch.
    old=world.recruitment_candidates
    after={k:v for k,v in old.items() if not (party is not None and v['party'] is party
        or applicant is not None and v['applicant'] is applicant)}
    affected={id(v['party']):v['party'] for k,v in old.items() if k not in after}
    deliveries=[]
    for p in affected.values():
        leader=p['leader']
        if leader in world.members and not leader.released:
            deliveries.append((leader,[wire.candidates(p,records=candidate_rows(world,p,after))]))
    return after,deliveries


def handle(world,s,event):
    kind=event.kind
    if event.event_id!=0x202 or kind not in wire.REQUESTS:return None
    answer=wire.answer_kind(kind)
    denied=lambda:[wire.candidates(None,-1)] if answer==0x8f7 else [wire.ack(answer,-1)]
    try:captured=actor(world,s)
    except ValueError:return []
    try:
        if (event.performers!=(0,) or event.payload_mode!=0
            or event.uid!=2**64-1 or event.target_uid!=2**64-1):raise ValueError('Recruitment envelope')
        actors={s:captured};party=world.party_of.get(s)
        if kind in (0x8f6,0x8f8,0x8ff):wire.empty_request(event.payload)
        if kind==0x8ff:
            rooms=[p for p in world.parties.values() if published(world,p)]
            for p in rooms:actors.update(waiting(world,p))
            response=[wire.ack(answer,party=rooms)]
            prepare(world,actors,[],response);return response
        if kind==0x901:
            target=world.parties.get(wire.target_request(event.payload))
            if target is None or not published(world,target):raise ValueError('Recruitment details source')
            actors.update(waiting(world,target));response=[wire.ack(answer,party=target)]
            prepare(world,actors,[],response);return response
        if kind==0x8ee:
            request=wire.create_request(event.payload)
            if party is not None:
                actors.update(waiting(world,party))
                if party['leader'] is not s:raise ValueError('Recruitment create leader')
            if (request['kind']!=1 or request['fields']!=(0,0,0,0,255,1)
                or request['tail'][:2]!=(0,0) or request['last']!=0
                or not request['title'].strip() or request['region']<=0
                or request['listed']!=request['dungeon']):raise ValueError('Recruitment create configuration')
            meta=dict(title=request['title'],maximum=request['tail'][2],region=request['region'],
                listed=request['listed'],flags=request['tail'][:2],sort_key=party['id'] if party else world.next_party,published=True)
            after={**party,'recruitment':meta,'ready':set()} if party else dict(id=world.next_party,
                leader=s,members=[s],ready=set(),dungeon=request['dungeon'],difficulty=0,mode=0,run=None,
                raid_party=False,recruitment=meta)
            if after['dungeon']!=request['dungeon']:raise ValueError('Recruitment current dungeon')
            source(after,single=True)
            if party is not None and party.get('recruitment')==meta:
                response=[wire.ack(answer)];prepare(world,actors,[],response);return response
            from els_server.domain.normal_party import roster_events
            pending,deliveries=removal_plan(world,party=party,applicant=s)
            notices=[*roster_events(after,reset=party is not None),wire.info_notice(after)]
            response=[wire.ack(answer)];boxes=prepare(world,actors,[*deliveries,*[(m,notices) for m in after['members']]],response)
            if party is None:
                party=after;world.next_party+=1;world.parties[party['id']]=party;world.party_of[s]=party
            else:party['recruitment']=meta;party['ready'].clear();party.pop('admission',None)
            world.recruitment_candidates=pending
            world.invitations={m:v for m,v in world.invitations.items() if v.get('party') is not party and m is not s}
            commit_boxes(boxes);return response
        if kind==0x8f3:
            if party is not None:raise ValueError('Recruitment applicant must have no party')
            target=world.parties.get(wire.target_request(event.payload))
            if target is None or not published(world,target):raise ValueError('Recruitment applicant target')
            actors.update(waiting(world,target));source({**target,'members':[*target['members'],s]})
            leader=target['leader'];key=(target['id'],s.account.uid)
            previous=world.recruitment_candidates.get(key)
            record=previous if previous is not None and valid_candidate(world,previous) else dict(
                party=target,leader=leader,applicant=s,uid=s.account.uid,
                wire=social.party_member(target['id'],s,0),binding=lease_binding(s),leader_binding=lease_binding(leader))
            notices=[] if record is previous else [(leader,[social.Event(0x201,kind=0x8f4,payload=record['wire'])])]
            response=[wire.ack(answer)];boxes=prepare(world,actors,notices,response)
            world.recruitment_candidates[key]=record;commit_boxes(boxes);return response
        if party is None or party['leader'] is not s:raise ValueError('Recruitment current leader')
        actors.update(waiting(world,party));meta=party.get('recruitment')
        if meta is None:raise ValueError('Recruitment room has no advertisement')
        if kind==0x8f1:
            request=wire.edit_request(event.payload)
            # 35D6CC0 fills only the title and room flag into a fresh ctor.
            if not request['title'].strip():raise ValueError('Recruitment title')
            after={**party,'recruitment':{**meta,'title':request['title']}}
            response=[wire.ack(answer,party=after)]
            boxes=prepare(world,actors,[(m,[wire.info_notice(after)]) for m in party['members']],response)
            party['recruitment']=after['recruitment'];commit_boxes(boxes);return response
        if kind==0x8f6:
            response=[wire.candidates(party,records=candidate_rows(world,party))]
            prepare(world,actors,[],response);return response
        if kind==0x8f8:
            after={**party,'recruitment':{**meta,'published':False}}
            pending,deliveries=removal_plan(world,party=party)
            response=[wire.ack(answer)];notices=[wire.info_notice(after),wire.stopped()]
            boxes=prepare(world,actors,[*deliveries,*[(m,notices) for m in party['members']]],response)
            party['recruitment']=after['recruitment'];world.recruitment_candidates=pending
            commit_boxes(boxes);return response
        if kind==0x8fd:
            uid=wire.target_request(event.payload)
            record=world.recruitment_candidates.get((party['id'],uid))
        else:
            # 234CE20 ->235D0D0 ->DA0420 writes the complete cached DTO.
            # It is an opaque echo binding, never authority for another actor.
            wire.candidate_payload(event.payload)
            record=next((v for v in world.recruitment_candidates.values()
                if v['party'] is party and v['wire']==event.payload),None)
        if record is None or not valid_candidate(world,record):raise ValueError('Recruitment candidate echo or source')
        target=record['applicant'];actors[target]=actor(world,target)
        if kind==0x8fd:
            pending=dict(world.recruitment_candidates);pending.pop((party['id'],record['uid']))
            response=[wire.ack(answer)]
            boxes=prepare(world,actors,[(s,[wire.candidates(party,records=candidate_rows(world,party,pending))])],response)
            world.recruitment_candidates=pending;commit_boxes(boxes);return response
        members=[*party['members'],target];after={**party,'members':members,'ready':set()}
        source(after)
        from els_server.domain.normal_party import roster_events
        pending,deliveries=removal_plan(world,applicant=target,
            party=party if len(members)>=meta['maximum'] else None)
        notices=[*roster_events(after,reset=True),wire.info_notice(after)]
        response=[wire.ack(answer)]
        boxes=prepare(world,actors,[*deliveries,*[(m,notices) for m in members]],response)
        party['members'][:]=members;party['ready'].clear();party.pop('admission',None)
        world.party_of[target]=party;world.recruitment_candidates=pending;world.invitations.pop(target,None)
        commit_boxes(boxes);return response
    except (ValueError,UnicodeError,struct.error):
        response=denied()
        # Even errors carry the native consumer's entire default DTO/vector.
        from els_server.protocol.protocol_codec import encode_event
        for e in response:encode_event(e)
        try:
            validate(s,captured)
            if not current_lease(s):return []
        except ValueError:return []
        return response


def leave(world,s,*,forced=False):
    party=world.party_of.get(s)
    if party is None or not party.get('recruitment'):return False
    old=tuple(party['members']);remaining=[m for m in old if m is not s]
    after={**party,'members':remaining,'leader':remaining[0] if party['leader'] is s and remaining else party['leader'],
        'ready':set(),'recruitment':{**party['recruitment'],'published':False}}
    # Source revocation must never depend on another departing peer's profile
    # still being readable. Build all optional forced notices inside preflight.
    pending={k:v for k,v in world.recruitment_candidates.items()
        if v['party'] is not party and v['applicant'] is not s}
    def notifications():
        _,deliveries=removal_plan(world,party=party,applicant=s)
        if remaining:
            from els_server.domain.normal_party import roster_events
            notices=[*roster_events(after,reset=True),wire.info_notice(after),wire.stopped()]
            deliveries.extend((m,notices) for m in remaining)
        if not forced:deliveries.append((s,[social.party_removed(s.account.uid),wire.stopped()]))
        return deliveries
    response=[] if forced else [social.Event(0x201,kind=0x140,payload=bytes(4))]
    if forced:
        # Disconnect must revoke membership even if the peer queue is full.
        # Encoding/queue copies are still attempted before this forced cleanup.
        try:boxes=_prepared_boxes(notifications(),response)
        except Exception as error:
            world.recruitment_cleanup_errors.append(('leave',type(error).__name__,str(error)))
            boxes={}
    else:
        actors=waiting(world,party);boxes=prepare(world,actors,notifications(),response)
    world.party_of.pop(s,None);party['members'][:]=remaining;party['ready'].clear();party.pop('admission',None)
    party['recruitment']=after['recruitment'];party['leader']=after['leader']
    if not remaining:world.parties.pop(party['id'],None)
    world.recruitment_candidates=pending
    world.invitations={m:v for m,v in world.invitations.items() if m is not s and v.get('party') is not party and v.get('inviter') is not s}
    commit_boxes(boxes);return response if not forced else True


def invalidate(world,s):
    """Withdraw ephemeral sources when the existing lifecycle leaves town."""
    party=world.party_of.get(s)
    pending={k:v for k,v in world.recruitment_candidates.items()
        if v['applicant'] is not s and (party is None or v['party'] is not party)}
    changed=party is not None and party.get('recruitment',{}).get('published')
    if pending==world.recruitment_candidates and not changed:return
    if changed:after={**party,'recruitment':{**party['recruitment'],'published':False}}
    try:
        _,deliveries=removal_plan(world,applicant=s,party=party)
        if changed:deliveries.extend((m,[wire.info_notice(after),wire.stopped()]) for m in party['members'] if not m.released)
        boxes=_prepared_boxes(deliveries,[])
    except Exception as error:
        world.recruitment_cleanup_errors.append(('invalidate',type(error).__name__,str(error)))
        boxes={}
    world.recruitment_candidates=pending
    if changed:party['recruitment']=after['recruitment']
    commit_boxes(boxes)


def select(world,s,event):
    """Preserve native145/147 while atomically withdrawing a changed advert."""
    denied=lambda:[social.Event(0x201,kind=0x146,payload=struct.pack('>i',-1))]
    try:
        party=world.party_of.get(s)
        if party is None or not party.get('recruitment') or party['leader'] is not s:raise ValueError('Recruitment select leader')
        actors=waiting(world,party)
        if len(event.payload)!=6 or event.payload_mode!=0:raise ValueError('Recruitment select body')
        identity,difficulty,mode=struct.unpack('>ibb',event.payload)
        from els_server.domain.dungeon_routes import route_catalog
        identity=route_catalog().entry_identity(identity)
        if difficulty or mode:raise ValueError('Recruitment normal selection')
        changed=(party['dungeon'],party.get('difficulty',0),party.get('mode',0))!=(identity,difficulty,mode)
        after={**party,'dungeon':identity,'difficulty':difficulty,'mode':mode}
        if changed:after.update(ready=set(),recruitment={**party['recruitment'],'published':False,'listed':identity})
        source(after,single=True)
        notice=social.Event(0x201,kind=0x147,payload=struct.pack('>ibb',identity,difficulty,mode))
        notices=[notice]
        pending=world.recruitment_candidates;deliveries=[]
        if changed:
            notices.extend(social.party_ready_notice(m.account.uid,False) for m in party['members'])
            notices.extend((wire.info_notice(after),wire.stopped()))
            pending,deliveries=removal_plan(world,party=party)
        response=[social.Event(0x201,kind=0x146,payload=bytes(4))]
        boxes=prepare(world,actors,[*deliveries,*[(m,notices) for m in party['members']]],response)
        if changed:
            party.update(dungeon=identity,difficulty=difficulty,mode=mode,recruitment=after['recruitment'])
            party['ready'].clear();party.pop('admission',None)
            world.recruitment_candidates=pending
            world.invitations={m:v for m,v in world.invitations.items() if v.get('party') is not party}
        commit_boxes(boxes);return response
    except (ValueError,struct.error):return denied()
