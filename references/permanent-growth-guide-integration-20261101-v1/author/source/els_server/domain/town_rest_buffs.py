"""Continuous server-observed camp residence, independent of client counters."""
from contextlib import closing
import sqlite3,time
from els_server.domain.elixir_flow import enabled,ready,context,profiles
from els_server.storage import town_rest_buffs as store
from els_server.protocol import world_buff_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.domain.town_rest_rules import saved_wait,minimum_wait

def synchronize(s,replies,*,clock=time.monotonic,wall=time.time):
    if not enabled(s):
        s._town_rest_wait=None
        return replies
    now=int(wall());steady=clock();town=s.active_map
    stable=(s.phase=='town_ready' and s.enter_town and not s.dungeon_return_pending and s.pending_map==town
        and {0x225,0x227}<=s.completed and s.account.get_location()['map']==town and town in store.TOWNS)
    token=(str(s.account.store.path),s.account.uid,s.shop_session_id,town)
    wait=getattr(s,'_town_rest_wait',None)
    if not stable:s._town_rest_wait=None
    elif wait is None or wait[0]!=token:s._town_rest_wait=wait=(token,steady)
    elapsed=steady-wait[1]if stable else 0.
    eligible=stable and elapsed>=minimum_wait()
    cold=any(e.event_id==0x201 and e.kind==0x2a for e in replies)
    if not cold and not ready(s):return replies
    previous=getattr(s,'_town_rest_sent',None)
    if not cold:
        if previous is not None and previous[0]==context(s) and previous[1] and now<previous[1][0][1]:return replies
        if not eligible and (previous is None or not previous[1]):return replies
    with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,db:
        db.execute('BEGIN')
        from els_server.storage.profession_state import require_owner
        from els_server.storage.item_actor import require_active_character
        require_owner(db,s.account.uid,s.account.account_id);require_active_character(db,s.account.uid)
        if eligible:
            eligible=elapsed>=saved_wait(s,db,token,now)
            if not eligible and not cold and(previous is None or not previous[1]):return replies
        if eligible:
            db.rollback();db.execute('BEGIN IMMEDIATE')
            require_owner(db,s.account.uid,s.account.account_id);require_active_character(db,s.account.uid)
            # Recheck the revision/deadline after waiting for the real writer.
            eligible=elapsed>=saved_wait(s,db,token,now)
            if s._town_rest_wait!=wait:raise ValueError('Camp residence generation changed')
            operation=s.shop_session_id+':camp:'+str(s.account.uid)+':'+str(wait[1])
            if eligible:store.grant(db,s.account.uid,s.account.account_id,town,operation,now)
        rows=store.active(db,s.account.uid,now)
        signature=(context(s,cold),tuple((r['start'],r['end'])for r in rows))
        # No unsolicited empty world vector for characters who never had it.
        if not rows and previous is None:return replies
        if not cold and signature==previous:return replies
        from els_server.storage.world_elixirs import _state as elixirs
        ordinary=elixirs(db,s.account.uid,now)['rows']
        stats=profiles(s,db,None) if not cold and s.phase=='dungeon_active' else None
        event=wire.snapshot(s.account.uid,ordinary,profiles=stats,rest=rows)
        encode_event(event)
    s._town_rest_sent=signature
    return replies+[event]
