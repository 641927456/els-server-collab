"""Native selection Apply in a confirmed current village session only."""
from els_server.protocol.avatar_set_messages import acknowledgement

def enabled(s):
    return s.item_test and s.client_build=='dx11_260923' and s.role=='game' and s.account.characters is not None and s.account.store is not None

def context(s):
    from els_server.storage.local_state import TOWN_SCENES
    if (not enabled(s) or s.phase!='town_ready' or not s.enter_town or s.dungeon_return_pending
        or getattr(s,'released',False) or getattr(s,'social_overflow',False) or getattr(s,'coop_error',None)
        or not {0x225,0x227}.issubset(s.completed) or s.pending_map!=s.active_map
        or s.active_map not in range(20000,20015) or not 1<=TOWN_SCENES.get(s.active_map,0)<=1215
        or s.account.get_location()['map']!=s.active_map):raise ValueError('Avatar Apply requires a stable village')
    app=getattr(s,'application',None);refs=[s.account,s.account.store,s.account.characters,app]
    values=[s.shop_session_id,s.account.account_id,s.account.uid,s.active_map,s.pending_map,repr(s.account.get_location())]
    if app is not None:
        if s.identity['id']!=s.account.account_id or app.playing.get(s.identity['id']) is not s:raise ValueError('Avatar current game lease')
        room=app.world.room(s);entry=room.get(s)
        if app.world.members.get(s)!=(1,s.active_map) or entry is None or entry[0]['uid']!=s.account.uid:raise ValueError('Avatar current village actor')
        refs.extend((app.playing,app.world,app.world.members,room,entry,entry[0],entry[1],entry[2]));values.append(repr(entry))
    return tuple(refs),tuple(values)

def validate(s,captured):
    refs,values=context(s)
    if values!=captured[1] or len(refs)!=len(captured[0]) or any(a is not b for a,b in zip(refs,captured[0])):raise ValueError('Avatar current context changed')

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0xbfc:return None
    try:
        if (event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Avatar Apply envelope')
        captured=context(s)
        from els_server.storage.avatar_sets import apply
        extra=[];flow=getattr(s,'activity2026_awards',None)
        observe=getattr(flow,'observe_avatar_apply',None)
        def effect(db,rows,side,operation):
            if observe is not None:extra.extend(observe(db,s,rows,side,operation))
        answer=apply(s.account.store.path,s.account.uid,event.payload,account_id=s.account.account_id,session_id=s.shop_session_id,sequence=sequence,validate=lambda:validate(s,captured),effect=effect if observe is not None else None)
        return [answer]+extra
    except ValueError:return [acknowledgement()]

def initialization(s,replies):
    if not enabled(s) or not any(e.kind==0x2a for e in replies):return []
    from els_server.storage.avatar_sets import restore
    return restore(s.account.store.path,s.account.uid,s.account.account_id)
