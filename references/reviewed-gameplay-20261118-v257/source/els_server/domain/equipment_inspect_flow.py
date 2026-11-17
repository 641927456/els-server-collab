"""On-demand native target statistics for the original equipment inspection UI."""
from dataclasses import dataclass,field
import struct
from time import monotonic,time
from uuid import uuid4

from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol import equipment_inspect_messages as wire
from els_server.protocol.inspection_stats import validate as validate_stats
from els_server.storage.friend_state import character as find_character
from els_server.storage.read_scope import snapshot_connection

CAPABILITY=0xff26
REPORT=0xff27
TIMEOUT=5


def actor(s):return s.account,s.account.uid,s.shop_session_id


def eligible(s):
    return (current_lease(s)and s.client_build=='dx11_260923'and 0x28 in s.completed
            and s.phase not in('closing','channels_ready')and not s.social_overflow
            and not s.coop_error and s.application.registry.enabled(s.identity['id']))


def envelope(s,event):
    return (eligible(s)and event.event_id==0x202 and event.performers in((),(0,))
            and event.uid==event.target_uid==2**64-1 and event.payload_mode==0)


def snapshot(s,db):
    from els_server.domain.client_power_inputs import snapshot as combat_inputs
    from els_server.storage.luciel_state import active_state,state as style_state
    inputs,source=combat_inputs(s,db=db)
    character=dict(inputs[0])
    # Combat binding omits Artifact EXP; the public profile needs the full DTO.
    if character.get('master'):
        character['artifact']=s.account.characters.artifact(s.account.uid,db=db)['artifact']
    if character['unit_type']==10:
        character['luciel_active_unit']=active_state(db,s.account.uid)['active_unit']
        character['luciel_style']=style_state(db,s.account.uid)['style']
    binding=(actor(s),s.phase,s.reward_run_id,source,
             character.get('luciel_active_unit',0),character.get('luciel_style',0))
    now=int(time())
    items=[i for i in inputs[1]if i.get('expires_at',now)>=now]
    return binding,character,items


@dataclass
class Pending:
    token:bytes
    binding:tuple
    deadline:float
    waiters:dict=field(default_factory=dict)


def finish(peer,pending,character=None,items=(),stats=None):
    if getattr(peer,'_inspection_pending',None)is pending:peer._inspection_pending=None
    for viewer,(owner,server)in pending.waiters.items():
        if (eligible(viewer)and actor(viewer)==owner
                and getattr(viewer,'_inspection_waiting',None)==(peer,pending.token)):
            viewer._inspection_waiting=None
            peer.application.world.send(viewer,wire.acknowledgement(character,items,server=server,stats=stats))
    pending.waiters.clear()


def periodic(peer):
    pending=getattr(peer,'_inspection_pending',None)
    if pending is not None and(not eligible(peer)or monotonic()>=pending.deadline):finish(peer,pending)


def close(peer):
    pending=getattr(peer,'_inspection_pending',None)
    if pending is not None:finish(peer,pending)
    peer._inspection_waiting=None


def handle(session,event):
    session._inspection_waiting=None
    if not envelope(session,event):return [wire.acknowledgement()]
    try:
        name,server=wire.request(event.payload)
        with snapshot_connection(session.account.store.path)as db:
            db.execute('BEGIN')
            target=find_character(db,name=name)
            peer=session.application.playing.get(target['account_id'])
            if peer is None or not eligible(peer)or peer.account.uid!=target['uid']:
                return [wire.acknowledgement()]
            support=getattr(peer,'_inspection_support',None)
            if support is None or support[0]!=actor(peer)or support[1]<=monotonic():
                return [wire.acknowledgement()]
            binding,_,_=snapshot(peer,db)
    except ValueError:return [wire.acknowledgement()]
    pending=getattr(peer,'_inspection_pending',None)
    if pending is not None and(pending.binding!=binding or pending.deadline<=monotonic()):
        finish(peer,pending);pending=None
    if pending is None:
        pending=Pending(uuid4().bytes,binding,monotonic()+TIMEOUT)
        peer._inspection_pending=pending
        from els_server.protocol.protocol_codec import Event
        session.application.world.send(peer,Event(0x201,kind=wire.REPLY,
            payload=b'IPQ1'+pending.token+struct.pack('>Q',peer.account.uid)))
    pending.waiters[session]=(actor(session),server)
    session._inspection_waiting=(peer,pending.token)
    return []


def support(session,event):
    if not envelope(session,event):raise ValueError('Inspection support actor/envelope')
    if event.kind==CAPABILITY:
        if event.payload!=b'ISV1'+struct.pack('>Q',session.account.uid):
            raise ValueError('Inspection support capability')
        session._inspection_support=(actor(session),monotonic()+10)
        return
    body=event.payload
    if not 29<=len(body)<=32797 or body[:4]!=b'IPR1':raise ValueError('Inspection report shape')
    token=body[4:20];owner=struct.unpack_from('>Q',body,20)[0]
    if owner!=session.account.uid:raise ValueError('Inspection report owner')
    pending=getattr(session,'_inspection_pending',None)
    if pending is None or pending.token!=token:return
    if body[28]not in(0,1):raise ValueError('Inspection report result')
    if body[28]==1:
        if len(body)!=29:raise ValueError('Failed inspection report has data')
        finish(session,pending);return
    with snapshot_connection(session.account.store.path)as db:
        db.execute('BEGIN');binding,character,items=snapshot(session,db)
    if monotonic()>=pending.deadline or pending.binding!=binding:
        finish(session,pending);return
    stats=body[29:]
    validate_stats(stats,luciel=character['unit_type']==10)
    finish(session,pending,character,items,stats)
