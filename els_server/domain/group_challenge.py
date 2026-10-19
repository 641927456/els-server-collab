"""Leader proposal, native AE5 member consent, then a roster-bound attempt."""
import struct
import time
from pathlib import Path
from els_server.protocol.challenge_messages import phase_ack,phase_notice
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


def validate(world,party,challenge,phase):
    minimum,maximum=limits(challenge,phase)
    members=tuple(party['members'])
    if not minimum<=len(members)<=maximum:raise ValueError('Challenge party size')
    if len({Path(m.account.store.path).resolve() for m in members})!=1:raise ValueError('Challenge database')
    from els_server.domain.region_quests import account_dungeon_allowed
    parent=(34120+phase*10) if challenge==4 else (34540+phase*10)
    if not all(m.phase=='town_ready' and m.role=='game' and not m.released and m in world.members and m.population_test and m.reward_test and m.account.character() is not None and account_dungeon_allowed(m.account,parent) for m in members):raise ValueError('Challenge participant')
    return members


def cancel(world,party):
    state=party.pop('challenge',None)
    party.pop('challenge_pending',None)
    if state:challenge_group.abandon(party['leader'].account.store.path,state['attempt'])
    broadcast(world,party,phase_notice())


def handle(s,event):
    if event.event_id!=0x202 or event.kind not in (0xae2,0xae5,0xae7,0xaea):return None
    world,party=world_party(s)
    if not party or party.get('solo_challenge') or len(party['members'])<2:return None
    kind=event.kind;ack=0xae3 if kind in (0xae2,0xae5) else 0xae8
    if (not s.application.config.friends_coop_enabled or s.role!='game' or s.phase!='town_ready'
        or party['run'] is not None):return [phase_ack(ack,-1)]
    if kind==0xae2:
        if s is not party['leader'] or len(event.payload)!=8:return [phase_ack(ack,-1)]
        challenge,phase=struct.unpack('>ii',event.payload)
        try:
            definition=phase_definition(challenge,phase)
            members=validate(world,party,challenge,phase)
            if party.get('challenge') and not party['challenge']['complete'] and party['challenge']['deadline']>int(time.time()):
                state=party['challenge']
                if (state['challenge'],state['phase'])!=(challenge,phase):raise ValueError('Abandon the current phase first')
                challenge_group.begin(s.account.store.path,[m.account.uid for m in members],s.account.uid,challenge,phase)
                broadcast(world,party,phase_notice(**{k:state[k] for k in ('challenge','phase','progress','deadline')},actor=s.account.uid,members=[m.account.uid for m in members]))
                return [phase_ack(ack)]
            party.pop('challenge',None)
            old=party.get('challenge_pending')
            if old and (old['challenge'],old['phase'])!=(challenge,phase):raise ValueError('Another proposal is pending')
            if not old:
                party['challenge_pending']=dict(challenge=challenge,phase=phase,members=members,accepted={s},expires=time.monotonic()+30)
                broadcast(world,party,phase_notice(challenge,phase,0,int(time.time())+definition['seconds'],result=0x3ff,actor=s.account.uid,members=[m.account.uid for m in members]))
        except (ValueError,AttributeError):return [phase_ack(ack,-1)]
        return [phase_ack(ack)]
    if kind==0xae7:
        if s is not party['leader'] or event.payload!=bytes([255])*8:return [phase_ack(ack,-1)]
        cancel(world,party);return [phase_ack(ack)]
    if event.payload not in (b'\0',b'\1'):return [phase_ack(ack,-1)]
    pending=party.get('challenge_pending')
    if not pending:return [phase_ack(ack)] if party.get('challenge') else [phase_ack(ack,-1)]
    if tuple(party['members'])!=pending['members'] or time.monotonic()>=pending['expires']:
        cancel(world,party);return [phase_ack(ack,-1)]
    if kind==0xaea or event.payload==b'\0':
        cancel(world,party);return [phase_ack(ack)]
    pending['accepted'].add(s)
    if pending['accepted']==set(pending['members']):
        try:
            leader=party['leader'];members=party['members']
            validate(world,party,pending['challenge'],pending['phase'])
            state=challenge_group.begin(leader.account.store.path,[m.account.uid for m in members],leader.account.uid,pending['challenge'],pending['phase'])
        except ValueError:
            cancel(world,party);return [phase_ack(ack,-1)]
        party.pop('challenge_pending',None);party['challenge']=state
        broadcast(world,party,phase_notice(**{k:state[k] for k in ('challenge','phase','progress','deadline')},actor=leader.account.uid,members=[m.account.uid for m in members]))
    return [phase_ack(ack)]


def refresh(party):
    if not party.get('challenge'):return
    from els_server.storage.challenge_state import ChallengeState
    m=party['leader'];party['challenge']=ChallengeState(m.account.store.path,m.account.uid).current()


def tick(s):
    world,party=world_party(s)
    if not party or party['leader'] is not s:return
    pending=party.get('challenge_pending')
    if pending and time.monotonic()>=pending['expires']:cancel(world,party)
