"""Retain an early native BB until its original committed part is ready.

Never advance a transaction shadow here. Replay through the existing session or
shared-room entry after its caller has committed and adopted the death state.
"""
import struct


def _binding(s):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    r=s.dungeon_run;a=s.account
    if getattr(s,'_c1_local_application',None) is not None:
        from els_server.domain.dungeon_hp_c1 import _lease
        if not _lease(s):return None
    if (r is None or a.store is None or s.role!='game' or s.client_build!='dx11_260923'
        or s.phase!='dungeon_active' or not s.dungeon_substage_synced
        or s.gate_stage_loading or s.clear_notified or getattr(s,'dungeon_failed',False)
        or getattr(s,'reward_transaction',None) is not None or not current_lease(s)):
        return None
    return (r,a,a.store,str(a.store.path),s.shop_session_id,a.account_id,a.uid,s.reward_run_id,
            r.run_id,r.identity,r.stage,r.part,r.visits)


def _request(s,event):
    return (event.event_id==0x202 and event.kind==0xbb and event.performers in ((),(0,))
            and event.uid==event.target_uid==2**64-1 and event.payload_mode==0
            and s.dungeon_run is not None
            and event.payload==struct.pack('>b',s.dungeon_run.part))


def _solo(s):
    b=_binding(s)
    if b is None:return None
    if (s.reward_run_id!=s.dungeon_run.run_id
        or getattr(s,'dungeon_participants',frozenset((s.account.uid,)))!=frozenset((s.account.uid,))
        or getattr(s,'_normal_fatigue_group_prepared',None) is not None):return None
    app=getattr(s,'application',None)
    if app is not None and app.world.dungeons.room(s) is not None:return None
    return b


def remember(s,event,sequence):
    if not _request(s,event) or s.part_end_notified:return
    b=_solo(s)
    if b is not None:s.pending_native_part_end=(b,event,sequence)


def finish(s,replies):
    pending=getattr(s,'pending_native_part_end',None)
    if pending is None or getattr(s,'reward_transaction',None) is not None:return replies
    if _solo(s)!=pending[0]:
        s.pending_native_part_end=None;return replies
    if not s.part_end_notified:return replies
    s.pending_native_part_end=None
    return replies+s.handle(pending[1],pending[2])


def _shared(dispatcher,r,s):
    from els_server.domain.friends_spawns import _checked_static_generation
    if (r.phase not in ('active','part_end') or s not in r.members
        or dispatcher.room(s) is not r or r.party.get('run') is not r
        or tuple(r.party['members'])!=tuple(r.members)):return None
    b=_binding(s)
    if b is None:return None
    try:generation=_checked_static_generation(dispatcher,r)
    except ValueError:return None
    return (r,tuple(r.members),r.seed,generation,b)


def remember_shared(dispatcher,r,s,event):
    if r.phase!='active' or not _request(s,event):return
    b=_shared(dispatcher,r,s)
    if b is not None:
        if not hasattr(r,'pending_native_part_ends'):r.pending_native_part_ends={}
        r.pending_native_part_ends[s]=(b,event)


def finish_shared(dispatcher,r):
    pending=getattr(r,'pending_native_part_ends',{})
    for s,(binding,event) in tuple(pending.items()):
        del pending[s]
        if _shared(dispatcher,r,s)==binding:
            dispatcher.send(s,dispatcher.end_part(r,s,event))
