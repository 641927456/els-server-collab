"""Permanent original guide entry and authenticated task synchronization."""
from contextlib import closing
from els_server.storage.sqlite_timing import write_transaction
import sqlite3,struct
from els_server.domain.quest_flow import enabled
from els_server.protocol import growth_guide_messages as wire
from els_server.protocol import quest_messages as quests
from els_server.protocol import activity_2026_entries as entries
from els_server.domain.growth_guide import catalog,contains
from els_server.storage.seal_quests import load_character,ensure,_state,completed_ids
from els_server.storage.inventory_state import load_items
from els_server.storage.growth_guide import enroll

def available(s,db):
    # Preserve the existing selected678 binding and its authoritative prefix.
    campaign=s.activity2026_awards
    from els_server.domain.selected_2026_growth_runtime import GrowthExtensionFlow
    if not isinstance(campaign,GrowthExtensionFlow) or not campaign.opened(s,campaign.participation.clock()):return True
    if not campaign.growth._participant(db,s):return True
    store=campaign.growth._store(db)
    return store.definition.pporu_available(event_active=True,is_bound_character=True,
        completed=store._completed(s.account.account_id,s.account.uid))

def synchronize(s,replies,*,force=False):
    if not enabled(s) or s.role!='game':return replies
    from els_server.domain.equipment_chip_flow import current_lease
    if s.account.store.uid!=s.account.uid or not current_lease(s):return replies
    cold=any(e.event_id==0x201 and e.kind==0x2a for e in replies)
    if not cold and not force and not getattr(s,'_growth_guide_started',False):return replies
    if not cold and s.phase not in ('town_ready','dungeon_active'):return replies
    kinds={e.kind for e in replies if e.event_id==0x201}
    if not (force or cold or kinds.intersection((0x2b,0x105,0x3a2,0xf3,0xf5,0xd9,0xd3,0x29f,0x4b9,0x1c5,0x8b2,0x6e8,0x9f0,0xb0f,0x8d6,0xbfd,0xad8,0x214,0x217,0x6d1,0x228))):return replies
    with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,write_transaction(db):
        character=load_character(db,s.account.uid,s.account.account_id);ensure(db)
        from els_server.storage.item_actor import require_active_character
        require_active_character(db,s.account.uid)
        allowed=available(s,db)
        items=load_items(db,s.account.uid)
        done=completed_ids(db,s.account.uid)
        graduated=all(int(q)in done for q in catalog()['quests'])
        new=enroll(db,s.account.uid,character,items,done) if allowed else ()
        snapshot=_state(db,s.account.uid,items)
        rows=[r for r in snapshot['active'] if contains(r['id'])]
        added=[quests.accepted(r) for r in rows if r['id'] in new]
        signature=(s.account.uid,allowed,tuple((r['id'],tuple(sorted(r['objectives'].items()))) for r in rows),
                   tuple(r['id'] for r in snapshot['completed'] if contains(r['id'])))
        changed=signature!=getattr(s,'_growth_guide_signature',None)
        progress=[quests.progress(rows)] if changed and rows and allowed else []
        # Encode every new projection while enrollment still belongs to this TX.
        from els_server.protocol.protocol_codec import encode_event
        for message in added+progress:encode_event(message)
    s._growth_guide_signature=signature
    s._growth_guide_started=True
    code_rows=dict(getattr(s,'_growth_guide_code_rows',{}));out=[];had_entries=False
    for event in replies:
        if event.event_id==0x201 and event.kind==0x4b9:
            had_entries=True;code_rows.update(entries.read(event.payload))
        else:out.append(event)
    code_rows[623]=entries.CodeEntry(allowed,0,0)
    s._growth_guide_code_rows=code_rows
    if cold or had_entries or changed or force:out.append(entries.notice(code_rows))
    out+=added+progress
    if cold or changed or force:out.append(wire.state(graduated))
    return out

def handle(s,event,sequence):
    if event.event_id!=0x202 or not enabled(s):return None
    if event.kind not in (0xcab,0xcad,0xd0d):return None
    kind={0xcab:0xcac,0xcad:0xcae,0xd0d:0xd0e}[event.kind]
    from els_server.domain.quest_flow import account_source_actor
    if (not account_source_actor(s)
            or type(sequence) is not int or not 1<=sequence<2**32
            or event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=0xffffffffffffffff or event.payload_mode!=0):
        return [wire.state(False,kind=kind,result=quests.QUEST_REWARD_UNAVAILABLE)]
    try:wire.request(event.kind,event.payload)
    except ValueError:return [wire.state(False,kind=kind,result=quests.QUEST_REWARD_UNAVAILABLE)]
    with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
        db.execute('BEGIN');load_character(db,s.account.uid,s.account.account_id);allowed=available(s,db)
        done=completed_ids(db,s.account.uid)
        finished=all(int(q) in done for q in catalog()['quests'])
    result=0 if allowed and (event.kind!=0xcad or finished) else quests.QUEST_REQUIREMENTS_NOT_MET
    return synchronize(s,[wire.state(finished,kind=kind,result=result)],force=True)
