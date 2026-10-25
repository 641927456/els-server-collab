"""Self owned world state only; peer world synchronization is not admitted."""
from els_server.protocol import world_buff_messages as wire
from els_server.protocol.career_messages import use_ack
from els_server.storage import world_elixirs as store
from els_server.domain.equipment_chip_flow import current_lease

def enabled(s):
    return (s.item_test and s.client_build=='dx11_260923' and s.account.characters is not None
        and s.account.store is not None and s.account.store.uid==s.account.uid and s.role=='game' and current_lease(s))

def ready(s):
    return s.phase=='town_ready' or(s.phase=='dungeon_active' and s.dungeon_substage_synced and not s.dungeon_return_pending)

def context(s,cold=False):
    if cold:return(s.account.uid,'selected')
    run=getattr(s,'dungeon_run',None)
    return(s.account.uid,s.phase,getattr(s,'active_map',None),getattr(run,'run_id',None),getattr(run,'stage',None),getattr(run,'part',None),getattr(run,'visits',None),getattr(s,'gate_stage',None))

def signature(s,state,cold=False):
    return(context(s,cold),state['revision'],tuple((r['template'],r['start'],r['end'])for r in state['rows']))

def profiles(s,db,items):
    # Invoke the existing pure builder with its supported capture callback.
    # Never monkeypatch a module/global encoder. Keep both original 28B slices,
    # including existing LuCiel HP policy; no final-stat estimate is introduced.
    from els_server.protocol.dungeon_messages import member
    from els_server.storage.inventory_state import load_items
    character=s.account.character()
    if character is None or character['uid']!=s.account.uid:raise ValueError('Elixir profile actor')
    current=db.execute('SELECT unit_class,level,revision FROM characters WHERE uid=?',(s.account.uid,)).fetchone()
    if current!=(character['unit_class'],character['level'],character['revision']):raise ValueError('Changed elixir profile')
    if items is None:items=load_items(db,s.account.uid)
    captured={}
    def capture(payload,spans):
        for key in('0x198','0x1b4'):
            offset,size=spans[key]
            if size!=28 or offset<0 or offset+size>len(payload):raise ValueError('Original elixir profile bounds')
            captured[key]=bytes(payload[offset:offset+size])
    member(s.account.get_skills(),character,items,capture=capture)
    if set(captured)!=set(('0x198','0x1b4')):raise ValueError('Missing original elixir profile')
    return(captured['0x198'],captured['0x1b4'])

def prepare(s,*,cold=False,assembly_override=None):
    from pathlib import Path
    account=s.account;root=account.root;store=account.store;identity=(account.uid,account.account_id,s.shop_session_id,context(s,cold));path=Path(store.path).resolve()
    def build(db,state,items):
        from els_server.domain.equipment_chip_flow import reset_authority
        reset_authority(s)
        main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
        if(not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=path or s.account is not account or account.root is not root or account.store is not store
            or identity!=(account.uid,account.account_id,s.shop_session_id,context(s,cold))or not enabled(s)or(not cold and not ready(s))):raise ValueError('Elixir current original writer/actor generation')
        stats=profiles(s,db,items)if not cold and s.phase=='dungeon_active' else None
        rows=list(state['rows'])
        from els_server.storage.assembly_state import view,clock
        assembly=view(db,s.account.uid,state['_moment'])if assembly_override is None else assembly_override
        if assembly['owner']!=s.account.uid:raise ValueError('Assembly snapshot owner')
        rows+=assembly['rows']
        run=getattr(s,'dungeon_run',None)
        if not cold and s.phase=='dungeon_active' and run is not None:
            from els_server.domain.silver_mirror_policy import ALL
            if run.identity in ALL and run.identity<35800:
                from els_server.storage.silver_mirror_state import world_rows
                rows+=world_rows(db,s.account.uid,now=state['_moment'])
        return[wire.snapshot(s.account.uid,rows,profiles=stats)]
    return build

def cold(s):
    if not enabled(s):return[]
    try:out=store.notice(s.account.store.path,s.account.uid,s.account.account_id,prepare(s,cold=True))
    except ValueError:return[]
    if out['events']:s._world_elixir_sent=signature(s,out['state'],True)
    return out['events']

def periodic(s):
    if not enabled(s)or not ready(s):return[]
    try:
        out=store.expire(s.account.store.path,s.account.uid,s.account.account_id,prepare(s))
        if out is None:
            state=store.snapshot(s.account.store.path,s.account.uid,s.account.account_id)
            if not state['revision']or signature(s,state)==getattr(s,'_world_elixir_sent',None):return[]
            out=store.notice(s.account.store.path,s.account.uid,s.account.account_id,prepare(s))
        s._world_elixir_sent=signature(s,out['state'])
        return out['events']
    except ValueError:
        # Pending/deleted actors or an unqualified stored row gain no effects.
        # Keep the previous delivery cursor so a later valid state can retry.
        return[]

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219 or not s.item_test or s.client_build!='dx11_260923' or s.account.characters is None or s.account.store is None:return None
    if type(sequence)is not int or not 1<=sequence<2**32:return None
    operation=s.shop_session_id+':elixir-v1:'+str(s.account.uid)+':'+str(sequence)
    if not store.candidate(s.account.store.path,s.account.uid,event.payload,operation):return None
    if (not enabled(s)or not ready(s)or(s.phase=='dungeon_active'and(getattr(s,'dungeon_failed',False)or s.clear_notified or s.part_end_notified))):return[use_ack(result=-1)]
    try:
        if event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0:raise ValueError('Elixir native envelope')
        out=store.use(s.account.store.path,s.account.uid,s.account.account_id,event.payload,operation,prepare(s))
        if out['result']==0:s._world_elixir_sent=signature(s,out['state'])
        return out['events']
    except ValueError:return[use_ack(result=-1)]
