"""Source-bound NPC portal entry, exit and return for the native hot springs."""
import sqlite3,struct
from contextlib import closing
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.local_state import scene_ready_location,validate_location
from els_server.domain.town_travel_flow import _ordinary_actor,_ordinary_binding
from els_server.domain.town_travel import SPA_PORTALS,entry_failure_payload,require_destination

# Recovery closes new portal entry. Saved characters can still restore and leave.
ENTRY_ENABLED=True
NPC_SOURCE={'npc':7507,'house':40256,'village':1500,'scene':725}

def _identity(s,event,sequence,*,returning=False):
    return bool(_ordinary_actor(s) and s.account.characters is not None
        and s.enter_town and s.item_test and s.client_build=='dx11_260923'
        and s.role=='game' and event.performers==(0,) and event.uid==event.target_uid==2**64-1
        and event.payload_mode==0 and type(sequence)is int and 1<=sequence<2**32
        and bool(s.dungeon_return_pending)==returning and getattr(s,'town_warp_transition',None) is None)

def _saved(db,s):
    from els_server.storage.seal_quests import load_character
    character=load_character(db,s.account.uid,s.account.account_id)
    row=db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(s.account.uid,)).fetchone()
    if row is None:raise ValueError('Missing spa saved source')
    return character,row

def _eligible(db,s,character,destination):
    from els_server.storage.seal_quests import completed_ids
    records={row[0] for row in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(s.account.uid,))}
    require_destination(destination,character,completed_ids(db,s.account.uid),records)

def _reply(kind,result,requested=0):
    payload=struct.pack('>i',result)
    if kind==0x226:payload+=struct.pack('>4i',requested,0,0,0)
    return [Event(0x201,kind=kind,payload=payload)]

def _ready_reply(s,location,user):
    from els_server.protocol import dungeon_messages
    from els_server.domain.fashion_state import move_ack
    from els_server.domain.character_custom import restored
    answer=_reply(0x228,0)
    snapshot,skills,character=user
    if not s.inventory_town_sync_sent:
        answer.append(dungeon_messages.return_user_sync(location,skills,
            snapshot['balances'],snapshot['items'],character,inventory_updates=[]))
    if s.phase=='square_accepted':
        items=[i for i in snapshot['items'] if i['group']==9]
        if items:answer.append(Event(0x201,kind=0x105,payload=move_ack([((9,i['slot']),i)for i in items])))
        answer.extend(restored(character))
    for event in answer:encode_event(event)
    return answer

def _facts(s):
    saved=s.account.get_location()
    return (s.phase,s.active_map,s.pending_map,s.inventory_town_sync_sent,
        saved['map'],saved['board'],saved['progress'],tuple(saved['xyz']),saved['revision'])

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x225,0x227):return None
    # A paid Cobo transition already owns the durable location. Its existing
    # 225/227 path verifies the exact receipt and completes the shared arrival.
    if getattr(s,'town_warp_transition',None) is not None:
        s.fishing1500_transition=None
        return None
    pending=getattr(s,'fishing1500_transition',None)
    if event.kind==0x225:
        requested=struct.unpack_from('>i',event.payload)[0] if len(event.payload)>=4 else 0
        saved=s.account.get_location()['map']
        # Intercept portal exits as well as entries. Only the matching village
        # is a valid direct exit.
        if requested not in SPA_PORTALS and saved not in SPA_PORTALS and s.active_map not in SPA_PORTALS:
            s.fishing1500_transition=None
            return None
        from els_server.domain.town_travel_flow import authorize_festival_entry,authorize_festival_return
        festival=authorize_festival_entry(s,event,sequence) or authorize_festival_return(s,event,sequence)
        returning=bool(s.dungeon_return_pending and requested==saved and saved in SPA_PORTALS and s.phase=='map_loading'
            and s.pending_map in(None,saved) and event.payload==struct.pack('>iB',saved,0))
        try:
            if (len(event.payload)!=5 or not _identity(s,event,sequence,returning=returning)
                or s.phase not in ('map_loading','square_accepted','town_ready')):
                raise ValueError('Ruben spa entry actor or phase')
            binding=_ordinary_binding(s);source_phase=s.phase;source_active=s.active_map
            facts=_facts(s);prior_pending=getattr(s,'fishing1500_transition',None);prior_values=None if prior_pending is None else dict(prior_pending)
            with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
                db.execute('BEGIN')
                character,row=_saved(db,s)
                if row[0]!=saved:raise ValueError('Ruben spa memory differs from saved source')
                cold=requested==saved and saved in SPA_PORTALS and event.payload[4]==0 and s.active_map in (None,saved)
                enter=(ENTRY_ENABLED and SPA_PORTALS.get(requested)==saved and s.active_map==saved
                    and event.payload[4]==1 and s.phase in ('town_ready','square_accepted'))
                leave=(SPA_PORTALS.get(saved)==requested and s.active_map==saved
                    and event.payload[4]==0 and s.phase in ('town_ready','square_accepted'))
                if not(cold or enter or leave or returning or festival):raise ValueError('Spa exact current source portal')
                if enter or festival:_eligible(db,s,character,requested)
                answer=_reply(0x226,0,requested)
                for reply in answer:encode_event(reply)
                if not _identity(s,event,sequence,returning=returning)or _ordinary_binding(s)!=binding or s.phase!=source_phase or s.active_map!=source_active or _facts(s)!=facts or getattr(s,'fishing1500_transition',None)is not prior_pending or prior_pending!=prior_values or enter and not ENTRY_ENABLED:raise ValueError('Ruben spa entry actor changed')
                s.fishing1500_transition=dict(binding=binding,source=row,destination=requested,
                    source_active=source_active,entry=enter,returning=returning,payload=bytes(event.payload),ready=None)
            s.pending_map=requested;s.inventory_town_sync_sent=False
            s.phase='square_accepted';s.completed.add(0x225)
            return answer
        except (ValueError,OverflowError)as error:
            return [Event(0x201,kind=0x226,payload=entry_failure_payload(error))]
    if pending is None:
        if s.pending_map in SPA_PORTALS or s.active_map in SPA_PORTALS:return _reply(0x228,515)
        return None
    try:
        if (not _identity(s,event,sequence,returning=pending['returning']) or _ordinary_binding(s)!=pending['binding']
            or s.pending_map!=pending['destination'] or s.phase not in ('square_accepted','town_ready')):
            raise ValueError('Ruben spa ready actor or transition mismatch')
        source_phase=s.phase;facts=_facts(s);pending_values=dict(pending)
        if pending['ready'] is not None:
            if event.payload!=pending['ready']or s.active_map!=pending['destination']:
                raise ValueError('Ruben spa ready replay differs')
            with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
                _,row=_saved(db,s)
                if row!=pending['committed']:raise ValueError('Ruben spa replay changed location')
            return _reply(0x228,0)
        if s.active_map!=pending['source_active']:raise ValueError('Ruben spa source actor moved')
        board,progress,xyz=scene_ready_location(event.payload)
        destination=pending['destination'];validate_location(destination,board,progress,xyz)
        #Inventory restoration may commit legacy repair in its own writer.
        user=(s.account.get_inventory_snapshot(),s.account.get_skills(),s.account.character())
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
            db.execute('BEGIN IMMEDIATE')
            character,row=_saved(db,s)
            if row!=pending['source']:raise ValueError('Ruben spa saved source changed')
            if pending['entry']:
                if not ENTRY_ENABLED:raise ValueError('Ruben spa new entry closed')
                _eligible(db,s,character,destination)
            values=(destination,board,progress,*xyz)
            changed=values!=row[:6]
            location=dict(map=destination,board=board,progress=progress,xyz=xyz,revision=row[6]+int(changed))
            answer=_ready_reply(s,location,user)
            if (not _identity(s,event,sequence,returning=pending['returning'])or _ordinary_binding(s)!=pending['binding']
                or s.fishing1500_transition is not pending or s.active_map!=pending['source_active'] or s.phase!=source_phase or _facts(s)!=facts or pending!=pending_values or pending['entry']and not ENTRY_ENABLED):
                raise ValueError('Ruben spa precommit actor changed')
            if changed:
                if 1503 in (row[0],destination):
                    from els_server.storage.festival_origins import transition
                    transition(db,s.account.uid,row[0],destination)
                db.execute('UPDATE location SET town=?,board=?,progress=?,x=?,y=?,z=?,revision=revision+1 WHERE uid=?',(*values,s.account.uid))
        with s.account.lock:s.account.location=location
        pending['ready']=bytes(event.payload);pending['committed']=(*values,location['revision'])
        pending['returning']=False;s.dungeon_return_pending=False
        s.active_map=destination;s.inventory_town_sync_sent=True;s.phase='town_ready';s.completed.add(0x227)
        from els_server.domain.festival_return_sync import ready as festival_ready
        answer.extend(festival_ready(s))
        if s.shop_test:s.shop_available_pending=True
        return answer
    except (ValueError,OverflowError):return _reply(0x228,515)
