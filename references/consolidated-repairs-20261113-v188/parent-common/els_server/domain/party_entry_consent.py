"""Native ordinary-party entry opinions, separate from invitation answers."""
import struct
import time

from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32, wstring


def _selection(party):
    return (party['leader'], tuple(party['members']), party['dungeon'],
            party.get('difficulty', 0), party.get('mode', 0))


def _ack(result=0):
    return [Event(0x201, kind=0x383, payload=i32(result)+wstring('')*3)]


def cancel(dungeons, party, *, failed=None, reason=1022):
    pending=party.pop('entry_consent', None)
    if pending is None:return
    party['ready'].clear()
    party.pop('admission', None)
    # Native 2D6BEF0 reads reason, failed UID, bool, name, bool.
    payload=struct.pack('>iQB',reason,failed.account.uid if failed else 0,0)+wstring('')+b'\0'
    notice=Event(0x201,kind=0x14d,payload=payload)
    for member in pending['members']:
        if member in dungeons.world.members and not member.released:
            dungeons.world.send(member,notice)


def _current(dungeons,party,pending):
    return (pending['selection']==_selection(party) and party['run'] is None
        and pending['actors']==tuple((m.account,m.account.uid,m.shop_session_id)for m in pending['members'])
        and all(not member.released and member.phase=='town_ready'
            and member in dungeons.world.members
            and dungeons.world.party_of.get(member) is party
            for member in pending['members']))


def begin(dungeons,party,leader,identity,event,mode):
    existing=party.get('entry_consent')
    if existing is not None:
        if _current(dungeons,party,existing) and time.monotonic()<existing['expires']:
            return _ack()
        cancel(dungeons,party)
    # 2D6AEA0: map, difficulty, mode, special=false, optional level, optional UID.
    notice=Event(0x201,kind=0x14b,payload=struct.pack('>ibbBiQ',identity,
        party.get('difficulty',0),party.get('mode',0),0,0,0))
    response=_ack()
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.domain.local_session import SessionOrderError
    try:boxes=_prepared_boxes([(m,[notice])for m in party['members']],response)
    except SessionOrderError:return _ack(-1)
    party['ready'].clear()
    party['entry_consent']=dict(selection=_selection(party),members=tuple(party['members']),
        actors=tuple((m.account,m.account.uid,m.shop_session_id)for m in party['members']),
        # The leader's 382 is its consent. Native type-1 leader skips the 14B
        # dialog and does not send 14C again (2D6B232 -> 2D6BD50).
        leader=leader,identity=identity,event=event,mode=mode,expires=time.monotonic()+30,accepted={leader})
    for member,box in boxes.items():member.mailbox=box
    return response


def reply(dungeons,session,event):
    if event.event_id!=0x202 or event.payload_mode!=0:return []
    party=dungeons.world.party_of.get(session)
    pending=party.get('entry_consent') if party else None
    if pending is None:return []
    if not _current(dungeons,party,pending):
        cancel(dungeons,party,failed=session)
        return []
    if time.monotonic()>=pending['expires']:
        cancel(dungeons,party,reason=1023)
        return []
    from els_server.domain.raid_native_power import request
    try:payload=request(session,event.payload,fresh=True)
    except ValueError:return []
    if len(payload)!=5 or payload[0] not in (0,1):return []
    accepted,reason=struct.unpack('>Bi',payload)
    if not accepted:
        # Client-provided reasons are not admission authority.
        cancel(dungeons,party,failed=session)
        return []
    pending['accepted'].add(session)
    if pending['accepted']!=set(pending['members']):return []
    party['ready'].update(pending['members'])
    leader=pending['leader'];identity=pending['identity']
    result=dungeons.admission_result(party,leader,identity)
    if result:
        cancel(dungeons,party,reason=result)
        return []
    for member in pending['members']:member._environment_entry_mode=pending['mode']
    if not dungeons.start_selected(party,leader,identity,pending['event']):
        cancel(dungeons,party,reason=2224)
        return []
    party.pop('entry_consent',None)
    return []


def tick(dungeons,session):
    party=dungeons.world.party_of.get(session)
    pending=party.get('entry_consent') if party else None
    if pending is None:return
    if not _current(dungeons,party,pending):cancel(dungeons,party,failed=session)
    elif time.monotonic()>=pending['expires']:cancel(dungeons,party,reason=1023)
