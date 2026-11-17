"""Leader proposal, native AE5 member consent, then a roster-bound attempt."""
import struct
import logging
import sqlite3
import time
from pathlib import Path
from els_server.protocol.challenge_messages import phase_ack,phase_notice,phase_confirmation
from els_server.storage.challenge_state import phase_definition
from els_server.storage import challenge_group


def world_party(s):
    world=getattr(getattr(s,'application',None),'world',None)
    return world,world.party_of.get(s) if world else None


def limits(challenge,phase):
    from els_server.game_data import client_data
    nodes=phase_definition(challenge,phase)['nodes']
    definitions=[client_data().dungeon(n['dungeon']) for n in nodes]
    return max(d.get('m_MinPlayerCount',1) for d in definitions),min(6,*(d.get('m_MaxPlayerCount',4) for d in definitions))


def broadcast(world,party,event):
    for member in party['members']:world.send(member,event)


def _current_member(world,party,member):
    # Reuse the same owned-role lease as inventory/equipment operations.
    # Native AE5/AEA only carry a bool, so they cannot authorize an old role
    # or a different current connection on their own.
    from els_server.domain.equipment_chip_flow import current_lease
    app=getattr(member,'application',None)
    return bool(app is not None and app.world is world
        and world.party_of.get(member) is party and current_lease(member)
        and app.registry.enabled(member.account.account_id))


def validate(world,party,challenge,phase):
    minimum,maximum=limits(challenge,phase)
    members=tuple(party['members'])
    if not minimum<=len(members)<=maximum:raise ValueError('Challenge party size')
    if not all(_current_member(world,party,m) for m in members):raise ValueError('Challenge participant lease or account changed')
    if len({Path(m.account.store.path).resolve() for m in members})!=1:raise ValueError('Challenge database')
    from els_server.domain.region_quests import account_dungeon_allowed
    parent=(34120+phase*10) if challenge==4 else (34540+phase*10)
    if not all(m.phase=='town_ready' and m.role=='game' and not m.released and m in world.members and m.population_test and m.reward_test and m.account.character() is not None and account_dungeon_allowed(m.account,parent) for m in members):raise ValueError('Challenge participant')
    return members


def _authority(world,party,members,extra):
    leader=party['leader']
    captured=tuple((m,m.account,m.account.root,m.account.store,m.account.characters,
        m.account.uid,m.account.account_id,m.identity,Path(m.account.store.path).resolve()) for m in members)
    owners={uid:account_id for _,_,_,_,_,uid,account_id,_,_ in captured}
    if len(owners)!=len(members):raise ValueError('Challenge duplicate owned role')
    def guard():
        if (tuple(party['members'])!=members or party['leader'] is not leader
            or party['run'] is not None):raise ValueError('Challenge transaction party changed')
        for m,account,root,store,characters,uid,account_id,identity,path in captured:
            if (m.account is not account or account.root is not root or account.store is not store
                or account.characters is not characters or m.identity is not identity
                or (account.uid,account.account_id,store.uid)!=(uid,account_id,uid)
                or Path(store.path).resolve()!=path or m.phase!='town_ready'
                or m not in world.members or not _current_member(world,party,m)):
                raise ValueError('Challenge transaction actor changed')
        extra()
    guard();return owners,guard


def _force_cancel(world,party):
    # Existing FriendsWorld lifecycle calls this before it removes the party
    # member, but disconnect has already removed town membership. This is
    # server cleanup of the original attempt, not a native consent request.
    members=tuple(party['members']);leader=party['leader']
    state=party.get('challenge');start=party.get('challenge_pending');cancel_pending=party.get('challenge_cancel_pending')
    captured=tuple((m,m.account,m.account.uid,m.account.account_id,Path(m.account.store.path).resolve()) for m in members)
    owners={uid:account_id for _,_,uid,account_id,_ in captured}
    if len(owners)!=len(members) or leader not in members:raise ValueError('Challenge cleanup roster')
    paths={path for _,_,_,_,path in captured}
    if len(paths)!=1:raise ValueError('Challenge cleanup database')
    def guard():
        if (world.parties.get(party['id']) is not party or tuple(party['members'])!=members
            or party['leader'] is not leader or party.get('challenge') is not state
            or party.get('challenge_pending') is not start
            or party.get('challenge_cancel_pending') is not cancel_pending):
            raise ValueError('Challenge lifecycle cleanup changed')
        for m,account,uid,account_id,path in captured:
            if (world.party_of.get(m) is not party or m.account is not account
                or (account.uid,account.account_id)!=(uid,account_id)
                or Path(account.store.path).resolve()!=path):
                raise ValueError('Challenge lifecycle source identity changed')
    from els_server.protocol.protocol_codec import encode_event
    prepared=[]
    def precommit(_):
        notice=phase_notice();encode_event(notice);prepared.append(notice)
    guard()
    if state is not None:
        challenge_group.abandon(next(iter(paths)),state['attempt'],uids=tuple(owners),
            leader=leader.account.uid,owners=owners,prepare=guard,precommit=precommit,active=False)
    else:
        precommit(None);guard()
    party.pop('challenge',None);party.pop('challenge_pending',None);party.pop('challenge_cancel_pending',None)
    for member in members:
        if _current_member(world,party,member):world.send(member,prepared[0])


def cancel(world,party,pending=None):
    if pending is None:return _force_cancel(world,party)
    state=party.get('challenge');members=tuple(party['members'])
    def extra():
        if (party.get('challenge_cancel_pending') is not pending
            or not _valid_pending(world,party,pending,abandon=True)
            or pending['accepted']!=set(members)):
            raise ValueError('Challenge cancellation consent changed')
    owners,guard=_authority(world,party,members,extra)
    from els_server.protocol.protocol_codec import encode_event
    prepared=[]
    def precommit(_):
        notice=phase_notice();encode_event(phase_ack(0xae8));encode_event(notice);prepared.append(notice)
    challenge_group.abandon(party['leader'].account.store.path,state['attempt'],
        uids=tuple(owners),leader=party['leader'].account.uid,owners=owners,prepare=guard,precommit=precommit)
    party.pop('challenge',None)
    party.pop('challenge_pending',None)
    party.pop('challenge_cancel_pending',None)
    broadcast(world,party,prepared[0])


def _context(world,party,pending):
    """Current owned connections must still match the original proposal."""
    members=tuple(party['members'])
    if (party['run'] is not None or party['leader'] is not pending['leader']
        or members!=pending['members'] or len(set(members))!=len(members)
        or tuple(m.account.uid for m in members)!=pending['uids']
        or time.monotonic()>=pending['expires']):return False
    for member in members:
        app=member.application
        if (member.role!='game' or member.phase!='town_ready' or member.released
            or member not in world.members or world.party_of.get(member) is not party
            or app.world is not world or app.playing.get(member.account.account_id) is not member
            or member.identity['id']!=member.account.account_id
            or not _current_member(world,party,member)):return False
    return True


def _valid_pending(world,party,pending,*,abandon):
    if not _context(world,party,pending):return False
    state=party.get('challenge')
    actual=None if state is None else (state['attempt'],state['challenge'],state['phase'])
    if actual!=pending['previous']:return False
    return not abandon or state is not None


def _proposal(party,challenge,phase):
    state=party.get('challenge')
    return dict(challenge=challenge,phase=phase,leader=party['leader'],
        members=tuple(party['members']),uids=tuple(m.account.uid for m in party['members']),
        previous=None if state is None else (state['attempt'],state['challenge'],state['phase']),
        accepted={party['leader']},expires=time.monotonic()+30)


def _drop_invalid(world,party,key,*,abandon):
    pending=party.get(key)
    if pending and not _valid_pending(world,party,pending,abandon=abandon):party.pop(key,None)


def _begin(world,party,challenge,phase,pending=None):
    members=validate(world,party,challenge,phase);leader=party['leader'];previous=party.get('challenge')
    def extra():
        if validate(world,party,challenge,phase)!=members or party.get('challenge') is not previous:
            raise ValueError('Challenge transaction context changed')
        if pending is not None and (party.get('challenge_pending') is not pending
            or not _valid_pending(world,party,pending,abandon=False)
            or pending['accepted']!=set(members)):
            raise ValueError('Challenge start consent changed')
    owners,guard=_authority(world,party,members,extra)
    from els_server.protocol.protocol_codec import encode_event
    prepared=[]
    def precommit(state):
        notice=phase_notice(**{k:state[k] for k in ('challenge','phase','progress','deadline')},
            actor=leader.account.uid,members=[m.account.uid for m in members])
        encode_event(phase_ack(0xae3));encode_event(notice);prepared.append(notice)
    state=challenge_group.begin(leader.account.store.path,tuple(owners),leader.account.uid,
        challenge,phase,owners=owners,prepare=guard,precommit=precommit)
    return state,prepared[0]


def _commit_start(world,party,pending):
    state,notice=_begin(world,party,pending['challenge'],pending['phase'],pending)
    party.pop('challenge_pending',None);party['challenge']=state
    broadcast(world,party,notice)


def _handle(s,event):
    if event.event_id!=0x202 or event.kind not in (0xae2,0xae5,0xae7,0xaea):return None
    world,party=world_party(s)
    if not party or party.get('solo_challenge') or len(party['members'])<2:return None
    kind=event.kind;ack=0xae3 if kind in (0xae2,0xae5) else 0xae8
    if (not s.application.config.friends_coop_enabled or s.role!='game' or s.phase!='town_ready'
        or party['run'] is not None or s not in party['members']):return [phase_ack(ack,-1)]
    _drop_invalid(world,party,'challenge_pending',abandon=False)
    _drop_invalid(world,party,'challenge_cancel_pending',abandon=True)
    if kind==0xae2:
        if s is not party['leader'] or len(event.payload)!=8 or party.get('challenge_cancel_pending'):return [phase_ack(ack,-1)]
        challenge,phase=struct.unpack('>ii',event.payload)
        try:
            phase_definition(challenge,phase);members=validate(world,party,challenge,phase)
            state=party.get('challenge')
            if state and not state['complete'] and state['deadline']>int(time.time()):
                if (state['challenge'],state['phase'])!=(challenge,phase):raise ValueError('Abandon the current phase first')
                state,notice=_begin(world,party,challenge,phase)
                party['challenge']=state
                broadcast(world,party,notice)
                return [phase_ack(ack)]
            old=party.get('challenge_pending')
            if old:
                if (old['challenge'],old['phase'])!=(challenge,phase):raise ValueError('Another proposal is pending')
                if old['accepted']==set(old['members']):_commit_start(world,party,old)
            else:
                pending=_proposal(party,challenge,phase)
                if not _context(world,party,pending):raise ValueError('Challenge proposal context')
                party['challenge_pending']=pending
                broadcast(world,party,phase_confirmation(0xae4,challenge,phase,s.account.uid))
        except (ValueError,AttributeError):return [phase_ack(ack,-1)]
        return [phase_ack(ack)]
    if kind==0xae7:
        if s is not party['leader'] or event.payload!=b'\xff'*8 or party.get('challenge_pending'):return [phase_ack(ack,-1)]
        state=party.get('challenge')
        if state is None:return [phase_ack(ack)]
        old=party.get('challenge_cancel_pending')
        if old:
            if old['accepted']==set(old['members']):
                try:cancel(world,party,old)
                except ValueError:return [phase_ack(ack,-1)]
        else:
            pending=_proposal(party,state['challenge'],state['phase'])
            if not _valid_pending(world,party,pending,abandon=True):return [phase_ack(ack,-1)]
            party['challenge_cancel_pending']=pending
            broadcast(world,party,phase_confirmation(0xae9,state['challenge'],state['phase'],s.account.uid))
        return [phase_ack(ack)]
    if event.payload not in (b'\0',b'\1'):return [phase_ack(ack,-1)]
    if kind==0xae5 and party.get('challenge_cancel_pending'):return [phase_ack(ack,-1)]
    if kind==0xaea and party.get('challenge_pending'):return [phase_ack(ack,-1)]
    key='challenge_pending' if kind==0xae5 else 'challenge_cancel_pending'
    pending=party.get(key)
    if pending is None:
        duplicate=(party.get('challenge') is not None) if kind==0xae5 else (party.get('challenge') is None and not party.get('challenge_pending'))
        return [phase_ack(ack,0 if duplicate else -1)]
    if event.payload==b'\0':
        party.pop(key,None);return [phase_ack(ack)]
    pending['accepted'].add(s)
    if pending['accepted']==set(pending['members']):
        if kind==0xaea:
            try:cancel(world,party,pending)
            except ValueError:return [phase_ack(ack,-1)]
        else:
            try:_commit_start(world,party,pending)
            except ValueError:
                if not _valid_pending(world,party,pending,abandon=False):party.pop(key,None)
                return [phase_ack(ack,-1)]
    return [phase_ack(ack)]


def refresh(party):
    if not party.get('challenge'):return
    from els_server.storage.challenge_state import ChallengeState
    m=party['leader'];party['challenge']=ChallengeState(m.account.store.path,m.account.uid).current()


def tick(s):
    world,party=world_party(s)
    if not party or party['leader'] is not s:return
    # Proposal expiry is not consent to abandon a durable attempt.
    _drop_invalid(world,party,'challenge_pending',abandon=False)
    _drop_invalid(world,party,'challenge_cancel_pending',abandon=True)


def handle(s,event):
    try:
        return _handle(s,event)
    except sqlite3.OperationalError as error:
        code=getattr(error,'sqlite_errorcode',None)
        if type(code) is not int or code & 255 not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):
            raise
        logging.getLogger(__name__).warning('Group challenge SQLite lock: kind=%s code=%s',event.kind,code,exc_info=True)
        ack=0xae3 if event.kind in (0xae2,0xae5) else 0xae8
        return [phase_ack(ack,-1)]
