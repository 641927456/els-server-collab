"""Finite native own-report/known-C lane: solo30000stage0, no effect model."""
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
    if s.dungeon_id!=30000 or s.gate_stage!=0:raise ValueError('Known resurrection finite map')
    from els_server.domain.luciel_dungeon import run_state
    refs,values=run_state(s)
    if getattr(s,'dungeon_participants',frozenset((a.uid,)))!=frozenset((a.uid,)):
        raise ValueError('Known resurrection requires solo native selector')
    app=getattr(s,'application',None)
    if app is not None:
        world=app.world
        if (world.dungeons.transport_room(s)is not None or world.dungeons.room(s)is not None
            or s in world.party_of or s in world.members):raise ValueError('Known resurrection shared context')
    if (getattr(s,'solo_challenge_party',None)is not None or getattr(s,'active_challenge',None)is not None
        or getattr(s,'challenge_deadline',None)is not None):raise ValueError('Known resurrection special context')
    return (a,a.store,getattr(a,'root',a),*refs),(a.uid,a.account_id,s.shop_session_id,s.phase,values)

def _same(expected,current):
    old,values=expected;new,now=current
    if len(old)!=len(new)or any(a is not b for a,b in zip(old,new))or values!=now:
        raise ValueError('Known resurrection context changed')

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
            entries=population(0)['npcs'];dead=s.defeated_npcs
        else:entries=run.current['npcs'];dead=run.defeated
        if not any(n['key']==request['killer']and n['active']and n['key']not in dead for n in entries):
            raise ValueError('Unknown current solo killer instance')

def _life(s,context):
    state=getattr(s,'known_resurrection_life',None)
    if state is not None:
        try:_same(state['context'],context)
        except ValueError:state=None
    if state is None:
        state=dict(context=context,number=0,phase='alive',death_sequence=None,death_payload=None)
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
            state['phase']='dead';return [death_complete(s.account.uid)]
        use_request(event.payload,s.account.uid)
        if state['phase']!='dead':raise ValueError('Native160 has no completed current death')
        life=state['number']
        def guard():
            _same(context,_scene(s,sequence))
            if getattr(s,'known_resurrection_life',None)is not state or state['phase']!='dead'or state['number']!=life:
                raise ValueError('Known resurrection life changed')
        result=spend(s.account.store.path,s.account.uid,event.payload,_operation(s,sequence),s.reward_run_id,life,
            account_id=s.account.account_id if s.account.characters is not None else None,guard=guard)
        if result['replayed']:
            # A commit followed by an unknown handoff is reconciled by a fresh
            # entry; replaying162 could heal an already living native actor.
            raise ConnectionError('Known resurrection handoff needs fresh entry')
        state['phase']='alive'
        return result['events']
    except ValueError:
        if kind==0xa7:return [death_ack(-1)]
        if kind==0xaa:return []
        value=snapshot(s.account.store.path,s.account.uid) if getattr(s.account,'store',None)is not None else 0
        return [use_ack(s.account.uid,value,-1)]
