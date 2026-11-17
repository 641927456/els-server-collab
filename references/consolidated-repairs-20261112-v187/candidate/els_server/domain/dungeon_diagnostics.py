"""Describe a refused dungeon request without payloads or player identities."""
from collections import Counter
import struct


def refusal(session,event,replies,request_sequence=None):
    if event.event_id!=0x202:return None
    expected={0xad:0xae,0x30a:0x30b,0x471:0x472,0xb8:0xb9,0xbb:0xbc,0x2ce:0x2cf}.get(event.kind)
    if expected is None:return None
    run=getattr(session,'dungeon_run',None)
    if run is None:return None
    ack=next((m for m in replies if m.event_id==0x201 and m.kind==expected),None)
    if ack is not None and len(ack.payload)>=4 and struct.unpack_from('>i',ack.payload)[0]==0:return None
    pending=[n for n in run.current['npcs']if n['active']and n.get('team',1)!=0 and n['key']not in run.defeated]
    result=dict(dungeon=run.identity,stage=run.stage,part=run.part,request=event.kind,
        outcome='missing_ack'if ack is None else'refused',phase=session.phase,
        synced=session.dungeon_substage_synced,part_end=session.part_end_notified,
        cleared=session.clear_notified,failed=getattr(session,'dungeon_failed',False),
        pending_templates=dict(Counter(n['template']for n in pending)))
    if event.kind==0xad:
        from els_server.domain.dungeon_lifecycle import death_report
        try:d=death_report(event.payload)
        except ValueError:
            result['death_shape']='malformed'
            return result
        actor=next((n for n in run.current['npcs']if n['key']==d['index']),None)
        participants=frozenset(getattr(session,'dungeon_participants',(session.account.uid,)))
        def role(uid):
            if uid in participants:return'participant'
            if uid in(0,2**64-1,2**64-4):return{0:'zero',2**64-1:'none',2**64-4:'native_minus4'}[uid]
            return'other'
        result.update(npc_key=d['index'],template=actor['template']if actor else None,
            source_index=actor.get('source_index')if actor else None,
            reported_hp_bits=d['hp_bits'],
            initial_hp_bits=struct.unpack('>I',struct.pack('>f',actor['hp']))[0]if actor else None,
            dynamic=bool(actor and actor.get('dynamic')),flag=d['flag'],status=d['status'],
            source_role=role(d['source']),killer_role=role(d['killer']),last_role=role(d['last_uid']),
            readiness_count=len(d['readiness']),readiness_matches=set(d['readiness'])==set(participants),
            hp_matches_initial=actor is not None and d['hp_bits']==struct.unpack('>I',struct.pack('>f',actor['hp']))[0])
    elif event.kind==0x30a and len(event.payload)==4:
        result['trigger']=struct.unpack('>i',event.payload)[0]
    elif event.kind==0x471 and len(event.payload)>=15:
        stage,part,reserved,count=struct.unpack_from('>iiHI',event.payload)
        result.update(request_stage=stage,request_part=part,native_stage=run.native_stage,
            condition_count=count,condition_shape_ok=len(event.payload)==15+count,
            native_flag=event.payload[-1])
    elif event.kind==0x2ce:
        # Reuse this request's actual scene decoder; do not try twenty modes
        # again or label a valid layout's qualification failure as malformed.
        decoded=getattr(session,'_spawn_diagnostic',None)
        if request_sequence is not None and decoded is not None and decoded[0]==request_sequence:
            result.update(decoded[1])
        else:result['spawn_shape']='not_decoded_by_scene_handler'
    return result
