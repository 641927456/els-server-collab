"""Qualified ordinary own-revival and peer lifecycle; no client effect model."""
from els_server.domain.equipment_chip_flow import current_lease
from els_server.protocol.known_resurrection import death_request,death_ack,death_complete,use_request,use_ack,continuation
from els_server.storage.known_resurrection import BOX,open_box,historical_box,spend
from els_server.storage.resurrection_counter import snapshot

def _actor(s,sequence):
    a=s.account
    if (s.role!='game' or s.client_build!='dx11_260923' or not s.item_test
        or a.store is None or a.store.uid!=a.uid or not current_lease(s)
        or type(sequence) is not int or not 1<=sequence<2**32):raise ValueError('Known resurrection current actor')
    return a

def _envelope(event):
    if (event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff
        or event.performers not in((),(0,))or event.payload_mode!=0):raise ValueError('Known resurrection native envelope')

def _town(s,sequence):
    a=_actor(s,sequence)
    if s.phase!='town_ready':raise ValueError('Known resurrection box phase')
    return (a,a.store,getattr(a,'root',a)),(a.uid,a.account_id,s.shop_session_id,s.phase)

def _scene(s,sequence):
    a=_actor(s,sequence)
    from els_server.domain.luciel_dungeon import run_state,canonical
    from els_server.domain.known_resurrection_maps import qualified
    keys=qualified(s);app=getattr(s,'application',None)
    world=app.world if app is not None else None
    room=world.dungeons.transport_room(s) if world is not None else None
    refs=[a,a.store,getattr(a,'root',a)];values=[a.uid,a.account_id,s.shop_session_id,s.phase]
    if (getattr(s,'solo_challenge_party',None)is not None or getattr(s,'active_challenge',None)is not None
        or getattr(s,'challenge_deadline',None)is not None):raise ValueError('Known resurrection special context')
    if room is None:
        if ((world is not None and (s in world.party_of or s in world.members))
            or getattr(s,'dungeon_participants',frozenset((a.uid,)))!=frozenset((a.uid,))):raise ValueError('Known resurrection detached room')
        extra,state=run_state(s);refs.extend(extra);values.append(state)
        epoch=s.reward_run_id;targets=()
    else:
        from els_server.domain.friends_dungeon import Room
        from els_server.domain.friends_world import Mailbox
        from els_server.domain.normal_party import ordinary
        if (type(room)is not Room or world.dungeons.room(s)is not room or room.phase!='active'
            or room.identity!=s.dungeon_id or not 2<=len(room.members)<=4 or not app.config.friends_coop_enabled
            or not ordinary(room.party) or room.party.get('run')is not room
            or room.party.get('difficulty',0)!=0 or room.party.get('mode',0)!=0
            or tuple(room.party['members'])!=room.members or room.party['leader']is not room.leader
            or room.leader not in room.members or s not in room.members):raise ValueError('Known resurrection ordinary room')
        canonical(room.seed,4);epoch=room.seed;participants=frozenset(m.account.uid for m in room.members)
        if len(participants)!=len(room.members):raise ValueError('Known resurrection duplicate actor')
        refs.extend((app,world,room,room.party,room.members));values.extend((room.identity,room.seed,room.phase,room.leader))
        generations=set()
        for member in room.members:
            if (member.application is not app or not current_lease(member) or member.social_overflow or member.coop_error
                or not app.registry.enabled(member.identity['id']) or member.role!='game'
                or member.client_build!='dx11_260923' or not member.item_test
                or world.dungeons.transport_room(member)is not room or world.dungeons.room(member)is not room
                or world.party_of.get(member)is not room.party or member.dungeon_participants!=participants
                or member.gate_stage!=s.gate_stage or type(member.mailbox)is not Mailbox):raise ValueError('Known resurrection room member changed')
            extra,state=run_state(member,room.seed)
            if qualified(member)!=keys:raise ValueError('Known resurrection peer scene changed')
            run=member.dungeon_run
            generations.add((run.run_id,run.stage,run.part,run.visits) if run is not None else (room.seed,member.gate_stage))
            refs.extend((member,member.account,member.account.store,member.identity,*extra))
            values.extend((member.account.uid,member.account.account_id,member.shop_session_id,state))
        if len(generations)!=1:raise ValueError('Known resurrection peer generation changed')
        targets=tuple(m for m in room.members if m is not s)
    return dict(refs=tuple(refs),values=tuple(values),epoch=epoch,keys=keys,targets=targets,shared=room is not None)

def _same(expected,current):
    old,values=(expected['refs'],expected['values'])if isinstance(expected,dict)else expected
    new,now=(current['refs'],current['values'])if isinstance(current,dict)else current
    if len(old)!=len(new)or any(a is not b for a,b in zip(old,new))or values!=now:
        raise ValueError('Known resurrection context changed')

def _mailbox_snapshot(box):return (box,box.bytes,tuple(box.messages),tuple(box.moves.items()))

def _prepare_peers(context,events):
    from collections import deque
    from els_server.domain.friends_world import Mailbox
    from els_server.protocol.protocol_codec import encode_event
    for event in events:encode_event(event)
    prepared=[]
    for target in context['targets']:
        old=target.mailbox
        if type(old)is not Mailbox:raise ValueError('Known resurrection peer mailbox type')
        clone=Mailbox();clone.messages=deque(old.messages);clone.moves=dict(old.moves);clone.bytes=old.bytes
        if clone.bytes!=sum(len(e.payload)for e in clone.messages)+sum(len(e.payload)for e in clone.moves.values()):raise ValueError('Known resurrection invalid peer queue')
        for event in events:clone.append(event)
        prepared.append((target,clone,_mailbox_snapshot(old)))
    return tuple(prepared)

def _validate_peers(prepared):
    for target,clone,before in prepared:
        if _mailbox_snapshot(target.mailbox)!=before:raise ValueError('Known resurrection peer queue changed')

def _deliver_peers(prepared):
    # No callbacks or encoding after the economic commit. Application serializes
    # all participating sessions, as with the existing active-state broadcasts.
    for target,clone,before in prepared:target.mailbox=clone

def _operation(s,sequence):return s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence)

def _source(s,request):
    sentinel=0xffffffffffffffff
    if request['user']not in(sentinel,s.account.uid)or request['maximum']not in(sentinel,s.account.uid):
        raise ValueError('Foreign solo death source')
    if request['a']!=0 or request['b']!=0 or request['extra']!=-1:
        raise ValueError('Unsupported specialized death context')
    if request['killer']!=-1:
        run=s.dungeon_run
        if run is None:
            from els_server.domain.dungeon_population import population
            entries=population(s.gate_stage)['npcs'];dead=s.defeated_npcs
        else:entries=run.current['npcs'];dead=run.defeated
        if not any(n['key']==request['killer']and n['active']and n['key']not in dead for n in entries):
            raise ValueError('Unknown current solo killer instance')

def _life(s,context):
    state=getattr(s,'known_resurrection_life',None)
    previous=state
    if state is not None:
        try:_same(state['context'],context)
        except ValueError:state=None
    if state is None:
        number=previous['number'] if previous is not None and previous.get('epoch')==context['epoch']else 0
        state=dict(context=context,epoch=context['epoch'],number=number,phase='alive',death_sequence=None,death_payload=None)
        s.known_resurrection_life=state
    return state

def handle(s,event,sequence):
    if event.event_id!=0x202:return None
    kind=event.kind
    if kind in(0x559,0x196):
        from els_server.protocol.ice_messages import preview_request,preview_ack,use_request as box_request
        from els_server.protocol.cube_messages import result as box_error
        a=s.account
        if getattr(a,'store',None)is None:return None
        try:req=preview_request(event.payload)if kind==0x559 else box_request(event.payload)
        except ValueError:return None
        if kind==0x559 and req.template!=BOX:return None
        try:
            if kind==0x196:
                item=next((i for i in a.get_inventory_snapshot()['items']if i['uid']==req.uid),None)
                known=item is not None and item['template']==BOX
                if not known and not historical_box(a.store.path,a.uid,event.payload,_operation(s,sequence)):return None
            expected=_town(s,sequence);_envelope(event)
            guard=lambda:_same(expected,_town(s,sequence))
            if kind==0x559:
                if req.keys not in((),(0,))or req.flag1 not in(0,1)or req.flag2 not in(0,1):raise ValueError('Known stone preview mode')
                item=next((i for i in a.get_inventory_snapshot()['items']if i['template']==BOX and i['group']==4),None)
                if item is None:raise ValueError('Known stone preview requires owned box')
                from els_server.domain.item_expiration import require_current
                from els_server.domain.item_locks import require_unlocked
                require_current(item);require_unlocked(item);guard()
                return [preview_ack(0,BOX)]
            return open_box(a.store.path,a.uid,event.payload,_operation(s,sequence),account_id=a.account_id if a.characters is not None else None,guard=guard)
        except ValueError:
            return [preview_ack(-1,BOX)]if kind==0x559 else box_error(0,code=-1)
    if kind not in(0xa7,0xaa,0x160):return None
    try:
        context=_scene(s,sequence);_envelope(event);state=_life(s,context)
        if kind==0xa7:
            req=death_request(event.payload);_source(s,req)
            if state['phase']=='alive':
                state.update(number=state['number']+1,phase='dying',death_sequence=sequence,death_payload=event.payload)
            return [death_ack()]
        if kind==0xaa:
            if event.payload:raise ValueError('Native AA must be empty')
            if state['phase']=='dead':return []
            if state['phase']!='dying':raise ValueError('Native AA has no current A7')
            notice=death_complete(s.account.uid);prepared=_prepare_peers(context,[notice])
            _same(context,_scene(s,sequence));_validate_peers(prepared)
            state['phase']='dead';_deliver_peers(prepared);return [notice]
        use_request(event.payload,s.account.uid)
        if state['phase']!='dead':raise ValueError('Native160 has no completed current death')
        life=state['number'];prepared=[]
        from els_server.domain.known_resurrection_maps import shared_position
        position=shared_position(context['epoch'],s.account.uid,life,context['keys'])if context['shared']else -1
        def prepare(events):
            answer=_prepare_peers(context,[events[-1]])
            prepared.extend(answer);return answer
        def guard():
            _same(context,_scene(s,sequence));_validate_peers(prepared)
            if getattr(s,'known_resurrection_life',None)is not state or state['phase']!='dead'or state['number']!=life:
                raise ValueError('Known resurrection life changed')
        result=spend(s.account.store.path,s.account.uid,event.payload,_operation(s,sequence),context['epoch'],life,
            account_id=s.account.account_id if s.account.characters is not None else None,guard=guard,
            dungeon=s.dungeon_id,position=position,prepare=prepare)
        if result['replayed']:
            # A commit followed by an unknown handoff is reconciled by a fresh
            # entry; replaying162 could heal an already living native actor.
            raise ConnectionError('Known resurrection handoff needs fresh entry')
        state['phase']='alive';_deliver_peers(result['prepared'])
        return result['events']
    except ValueError:
        if kind==0xa7:return [death_ack(-1)]
        if kind==0xaa:return []
        value=snapshot(s.account.store.path,s.account.uid) if getattr(s.account,'store',None)is not None else 0
        dungeon=s.dungeon_id if type(s.dungeon_id)is int and 0<s.dungeon_id<2**31 else 30000
        return [use_ack(s.account.uid,value,-1,dungeon=dungeon)]
