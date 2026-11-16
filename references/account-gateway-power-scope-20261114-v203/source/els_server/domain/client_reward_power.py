"""Client-origin raw CP. This is a freshness check, not independent attestation."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path
import math
import struct

from els_server.domain.client_power_inputs import snapshot

ENTRY=frozenset((0x6be,0x7d4,0x14c,0x37f,0x382))
REWARDS=frozenset((0xad,0xbb))
FOOTER=struct.Struct('>4sQffB3s')
_current=ContextVar('client_reward_power',default=None)


@dataclass(frozen=True)
class Report:
    actor: tuple
    powers: tuple
    side: int
    source: str
    run_id: str | None = None
    dungeon: int | None = None


def actor(session):
    return session.account,session.account.uid,session.shop_session_id


def participants(session):
    world=session.application.world
    room=world.dungeons.room(session)
    if room is not None:
        return tuple(m for m in room.members if world.dungeons.room(m) is room)
    party=world.party_of.get(session)
    return tuple(party['members']) if party is not None else (session,)


def receive(session,event):
    if event.kind in ENTRY:
        session._client_reward_power=None
    payload=event.payload
    if len(payload)<FOOTER.size or payload[-FOOTER.size:-FOOTER.size+4]!=b'GRP2':
        return event
    _,owner,first,second,side,padding=FOOTER.unpack(payload[-FOOTER.size:])
    from els_server.domain.equipment_chip_flow import current_lease
    if (event.event_id!=0x202 or event.payload_mode or event.performers not in ((),(0,))
            or event.uid!=event.target_uid or event.uid!=2**64-1
            or owner!=session.account.uid or not current_lease(session)
            or padding!=bytes(3) or side not in (0,1)
            or any(not math.isfinite(p) or not 0<=p<=4294967040 for p in (first,second))):
        raise ValueError('Client raw CP actor/envelope/number')
    inputs,source=snapshot(session)
    character=inputs[0]
    if character['unit_type']!=10 and (side or first!=second):
        raise ValueError('Client raw CP non-LuCiel sides')
    body=payload[:-FOOTER.size]
    if event.kind in ENTRY:
        if session.phase!='town_ready' and event.kind!=0x6be:
            raise ValueError('Client raw CP entry phase')
        if len(body)<16 or body[-16:-12]!=b'RCP1':
            raise ValueError('Client raw CP entry footer missing')
        _,cached_owner,cached=struct.unpack('>4sQf',body[-16:])
        rounded=struct.unpack('>f',struct.pack('>f',max(first,second)+.5))[0]
        rounded=struct.unpack('>f',struct.pack('>f',math.floor(rounded)))[0]
        if cached_owner!=owner or cached!=rounded:
            raise ValueError('Client raw/display CP disagree')
    bound=event.kind in REWARDS
    session._client_reward_power=Report(actor(session),(first,second),side,source,
        session.reward_run_id if bound else None,session.dungeon_id if bound else None)
    return replace(event,payload=body)


@contextmanager
def scope(function,args):
    from els_server.application import FriendsSession
    session=getattr(function,'__self__',None)
    if type(session) is not FriendsSession:
        yield args
        return
    report_request=(function.__name__=='handle' and len(args)==1
        and args[0].event_id==0x202 and args[0].kind in ENTRY|REWARDS)
    run_call=(function.__name__ in ('handle','periodic_notifications')
        and session.phase=='dungeon_active' and session.account is not None)
    if not (report_request or run_call):
        yield args
        return
    call_args=(receive(session,args[0]),) if report_request else args
    members={m.account.uid:m for m in participants(session)}
    token=_current.set((members,{}))
    try:
        yield call_args
    finally:
        _current.reset(token)


def checked(db,owner,context):
    current=_current.get()
    if current is None or owner not in current[0]:return None
    session=current[0][owner]
    report=getattr(session,'_client_reward_power',None)
    from els_server.domain.equipment_chip_flow import current_lease
    if (report is None or report.actor!=actor(session) or not current_lease(session)
            or context['owner']!=owner or context['run_id']!=session.reward_run_id
            or context['dungeon']!=session.dungeon_id):return None
    path=next(path for _,name,path in db.execute('PRAGMA database_list') if name=='main')
    if not db.in_transaction or Path(path).resolve()!=Path(session.account.store.path).resolve():
        raise ValueError('Client raw CP needs the original owner reward transaction')
    if report.run_id is None:
        report=replace(report,run_id=session.reward_run_id,dungeon=session.dungeon_id)
        session._client_reward_power=report
    if report.run_id!=context['run_id'] or report.dungeon!=context['dungeon']:return None
    inputs,source=snapshot(session,db=db)
    if source!=report.source:return None
    stored_side=0
    if inputs[0]['unit_type']==10:
        from els_server.storage.luciel_state import active_state
        stored_side=active_state(db,owner)['active_unit']
    # Keep the latest native selector for immediate and deferred rewards.
    # A form-changing skill can report damage before its periodic 38E.
    return report,report.side,stored_side


def remember_active(session,side):
    """Advance an existing snapshot after a new native 38E has committed."""
    report=getattr(session,'_client_reward_power',None)
    if report is not None and report.actor==actor(session):
        session._client_reward_power=replace(report,side=side)


def freeze_kill_power(db,owner,context):
    current=_current.get()
    if current is None:return
    from els_server.domain.reward_attributes import greed_rank
    if not greed_rank(db,owner):return
    value=checked(db,owner,context)
    if value is not None:current[1][db,owner]=value


def reward_power(db,owner,context):
    current=_current.get()
    if current is None:return None
    saved=current[1].get((db,owner))
    if saved is None:
        saved=checked(db,owner,context)
    else:
        session=current[0][owner]
        report,side,stored_side=saved
        if (getattr(session,'_client_reward_power',None) is not report
                or actor(session)!=report.actor or context['run_id']!=report.run_id
                or context['dungeon']!=report.dungeon):
            raise ValueError('Client raw CP reward actor/run changed')
        from els_server.storage.luciel_state import active_state
        if active_state(db,owner)['active_unit']!=stored_side:
            raise ValueError('Client raw CP reward form changed')
    if saved is None:return None
    report,side,_=saved
    return report.powers[side],side,report.source


def enabled():
    return _current.get() is not None
