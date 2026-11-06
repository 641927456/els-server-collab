"""Native Quick Start entry/state and guarded career requests."""
import sqlite3,struct
from contextlib import closing
from els_server.protocol import quick_start_messages as wire
from els_server.domain.quick_start import CODE,QUESTS
from els_server.storage.quick_start import enrollment,participant

def enabled(s):
    return (s.client_build=='dx11_260923' and s.item_test and s.account.store is not None
            and s.account.characters is not None and s.role=='game')

def state(s):
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        db.execute('BEGIN')
        uid=enrollment(db,s.account.account_id)
        finished=False
        if uid:
            row=db.execute('SELECT master FROM characters WHERE uid=?',(uid,)).fetchone()
            finished=bool(row and row[0] and db.execute(
                'SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(uid,QUESTS[-1])).fetchone())
        return uid or 0,finished

def synchronize(s,replies):
    if not enabled(s):return replies
    restoring=any(e.event_id==0x201 and e.kind in(0x488,0x25,0x2a,0x2b)for e in replies)
    if s.phase not in('characters_ready','channels_ready','town_ready','dungeon_active')and not restoring:return replies
    from els_server.protocol.activity_2026_entries import read,notice,CodeEntry
    rows=dict(getattr(s,'_quick_start_code_rows',{}));out=[];had=False
    for e in replies:
        if e.event_id==0x201 and e.kind==0x4b9:
            rows.update(read(e.payload));had=True
        else:out.append(e)
    # Original2F93E70 consumes parameters[0] as the one-based quest cycle.
    rows[CODE]=CodeEntry(True,1793462400,253402214400,parameters=(1,))
    uid,finished=state(s);signature=(uid,finished)
    if restoring or had or getattr(s,'_quick_start_signature',None)!=signature:
        # Entry precedes C55 so the original manager can resolve code578.
        out.insert(0,notice(rows));out.insert(1,wire.user_state(uid,finished))
        s._quick_start_signature=signature
    s._quick_start_code_rows=rows
    return out

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0xc56,0xc58):return None
    if not enabled(s):return []
    from els_server.domain.quest_flow import account_source_guard,account_source_actor
    if (not account_source_actor(s) or s.phase!='town_ready' or type(sequence)is not int or not 1<=sequence<2**32
        or event.performers!=(0,) or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):return []
    uid=s.account.uid;account=s.account.account_id
    if event.kind==0xc58:
        if event.payload:return []
        owner,finished=state(s)
        return [wire.finish_ack(owner,result=0 if owner==uid and finished else 187,finished=finished)]
    from els_server.storage.quick_start import change_career
    from els_server.storage.career_shop import notifications
    from els_server.protocol.protocol_codec import encode_event
    binding=(s.account,s.account.store,s.shop_session_id,account,uid)
    def prepare(db):
        if (s.account is not binding[0] or s.account.store is not binding[1]
            or (s.shop_session_id,s.account.account_id,s.account.uid)!=binding[2:]
            or s.phase!='town_ready'):raise ValueError('Quick Start selected actor changed')
        account_source_guard(s,db)
    def encode(db,before,after,replayed,retired):
        packets=notifications(db,uid,before,s.account.get_location(),before,after,replayed)+[wire.career_ack(retired)]
        for packet in packets:encode_event(packet)
        return packets
    try:
        target=wire.career_request(event.payload)
        return change_career(s.account.store.path,uid,account,target,
            s.shop_session_id+':quick-career:'+str(uid)+':'+str(sequence),prepare,encode)
    except ValueError:return [wire.career_ack(result=187)]
