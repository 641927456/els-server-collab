"""Single-player challenge phase admission and original phase notifications."""
import struct,time
from els_server.protocol.challenge_messages import phase_ack,phase_notice
from els_server.storage.challenge_state import ChallengeState,phase_definition

class SoloMember:
 def __init__(self,account):
  self.account=account;self.identity={'id':account.account_id}

def store(s):
 if s.account.store is None:return None
 return ChallengeState(s.account.store.path,s.account.uid)

def notification(s):
 state=store(s).current()
 if state is None or state['complete'] or state['deadline']<=int(time.time()):return phase_notice()
 return phase_notice(state['challenge'],state['phase'],state['progress'],state['deadline'],actor=s.account.uid)

def allowed(s,identity):
 ledger=store(s)
 return ledger.admit(identity) if ledger is not None else None

def release_room(s):
 from els_server.protocol.social_messages import party_removed
 world=getattr(getattr(s,'application',None),'world',None)
 if world and world.party_of.get(s,{}).get('solo_challenge'):
  world.leave_party(s);return []
 if getattr(s,'solo_challenge_party',None) is not None:
  s.solo_challenge_party=None;return [party_removed(s.account.uid)]
 return []

def ordinary_entry(s):
 world=getattr(getattr(s,'application',None),'world',None)
 owns=bool(getattr(s,'solo_challenge_party',None)) or bool(world and world.party_of.get(s,{}).get('solo_challenge'))
 if not owns:return True,[]
 state=store(s).current()
 if state and not state['complete'] and state['deadline']>int(time.time()):return False,[]
 return True,release_room(s)

def handle(s,event):
 from els_server.domain.group_challenge import handle as group_handle
 grouped=group_handle(s,event)
 if grouped is not None:return grouped
 if event.event_id!=0x202:return None
 if event.kind==0x13f and getattr(s,'solo_challenge_party',None) is not None:
  if s.phase!='town_ready' or len(event.payload)!=4:return []
  store(s).abandon()
  from els_server.protocol.protocol_codec import Event
  return release_room(s)+[Event(0x201,kind=0x140,payload=bytes(4)),notification(s)]
 if event.kind not in (0xae2,0xae5,0xae7,0xaea):return None
 kind=event.kind;ack=0xae3 if kind in (0xae2,0xae5) else 0xae8
 if s.role!='game' or s.phase!='town_ready' or not s.population_test or not s.reward_test or s.account.store is None:return [phase_ack(ack,-1)]
 ledger=store(s)
 if kind==0xae2:
  try:
   if len(event.payload)!=8:raise ValueError('Challenge request size')
   challenge,phase=struct.unpack('>ii',event.payload);phase_definition(challenge,phase)
   from els_server.domain.region_quests import account_dungeon_allowed
   if not account_dungeon_allowed(s.account,(34120+phase*10) if challenge==4 else (34540+phase*10)):raise ValueError('Challenge region is locked')
   world=getattr(getattr(s,'application',None),'world',None)
   party=world.party_of.get(s) if world else None
   if party is not None and not party.get('solo_challenge'):raise ValueError('Local challenge phase requires a solo room')
   ledger.begin(challenge,phase)
  except ValueError:return [phase_ack(ack,-1)]
  messages=[phase_ack(ack)]
  if world and s.account.character() is not None:
   if party is None:
    party=dict(id=world.next_party,leader=s,members=[s],ready=set(),dungeon=phase_definition(challenge,phase)['dummy'],run=None,solo_challenge=True)
    world.next_party+=1;world.parties[party['id']]=party;world.party_of[s]=party
   party['dungeon']=phase_definition(challenge,phase)['dummy']
   from els_server.protocol.social_messages import party_snapshot
   messages.append(party_snapshot(party))
  elif s.account.character() is not None:
   party=getattr(s,'solo_challenge_party',None)
   if party is not None and party['members'][0].account.uid!=s.account.uid:
    from els_server.protocol.social_messages import party_removed
    messages.append(party_removed(party['members'][0].account.uid));party=None
   if party is None:
    member=SoloMember(s.account)
    party=dict(id=900000+s.account.uid,leader=member,members=[member],ready=set(),dungeon=phase_definition(challenge,phase)['dummy'],run=None,solo_challenge=True)
    s.solo_challenge_party=party
   party['dungeon']=phase_definition(challenge,phase)['dummy']
   from els_server.protocol.social_messages import party_snapshot
   messages.append(party_snapshot(party))
  return messages+[notification(s)]
 if kind==0xae7:
  if event.payload!=bytes([255])*8:return [phase_ack(ack,-1)]
  ledger.abandon()
  return [phase_ack(ack),*release_room(s),notification(s)]
 # AE5 and AEA are native party confirmation replies (one bool). The local
 # initiator commits immediately; duplicate confirmations are read-only.
 if event.payload not in (b'\0',b'\1'):return [phase_ack(ack,-1)]
 if kind==0xaea and event.payload==b'\1':
  ledger.abandon();return [*release_room(s),notification(s)]
 return [notification(s)]
