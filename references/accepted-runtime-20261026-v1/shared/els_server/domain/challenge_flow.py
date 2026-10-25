"""Single-player challenge phase admission and original phase notifications."""
import struct,time,sqlite3
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

def _capture(s,event):
 from pathlib import Path
 from els_server.domain.equipment_chip_flow import current_lease
 account=s.account;root=account.root;store=account.store;characters=account.characters
 app=getattr(s,'application',None);identity=getattr(s,'identity',None)
 uid=account.uid;account_id=account.account_id
 if store is None or characters is None:raise ValueError('Challenge owned role missing')
 path=Path(store.path).resolve()
 def guard():
  if (s.account is not account or account.root is not root or account.store is not store
      or account.characters is not characters or root.root is not root
      or root.character_accounts.get(uid) is not account or root.characters is not characters or root.account_id!=account_id
      or (account.uid,account.account_id,store.uid,characters.account_id)!=(uid,account_id,uid,account_id)
      or Path(store.path).resolve()!=path or Path(characters.path).resolve()!=path
      or s.role!='game' or s.phase!='town_ready' or not s.population_test or not s.reward_test
      or s.client_build!='dx11_260923' or not current_lease(s)
      or event.performers not in ((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
      or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity):
   raise ValueError('Challenge current actor/phase/envelope')
  if app is not None and (not isinstance(identity,dict)or identity.get('id')!=account_id
      or app.accounts.get(account_id)is not root or not app.registry.enabled(account_id)):
   raise ValueError('Challenge current account root')
 guard();return account_id,guard

def _notice(state,uid):
 if state is None or state['complete']or state['deadline']<=int(time.time()):return phase_notice()
 return phase_notice(state['challenge'],state['phase'],state['progress'],state['deadline'],actor=uid)

def _abandon(s,event,ack=None):
 from els_server.protocol.protocol_codec import encode_event
 from els_server.protocol.social_messages import party_removed
 account_id,guard=_capture(s,event);messages=[]
 def precommit(state):
  if ack is not None:messages.append(ack)
  messages.append(phase_notice())
  for notice in messages:encode_event(notice)
  world=getattr(getattr(s,'application',None),'world',None)
  if (world and world.party_of.get(s,{}).get('solo_challenge'))or getattr(s,'solo_challenge_party',None)is not None:
   encode_event(party_removed(s.account.uid))
 store(s).abandon(account_id=account_id,prepare=guard,precommit=precommit)
 removed=release_room(s)
 return ([ack]if ack is not None else[])+removed+[messages[-1]]

def handle(s,event):
 from els_server.domain.group_challenge import handle as group_handle
 grouped=group_handle(s,event)
 if grouped is not None:return grouped
 if event.event_id!=0x202:return None
 if event.kind==0x13f and getattr(s,'solo_challenge_party',None)is not None:
  if len(event.payload)!=4:return []
  from els_server.protocol.protocol_codec import Event
  try:return _abandon(s,event,Event(0x201,kind=0x140,payload=bytes(4)))
  except (ValueError,AttributeError,sqlite3.Error):return []
 if event.kind not in (0xae2,0xae5,0xae7,0xaea):return None
 kind=event.kind;ack=0xae3 if kind in (0xae2,0xae5)else 0xae8
 try:
  account_id,guard=_capture(s,event)
  if kind==0xae2:
   if len(event.payload)!=8:raise ValueError('Challenge request size')
   challenge,phase=struct.unpack('>ii',event.payload);definition=phase_definition(challenge,phase)
   #Current Challenge4/5 are split/merged multiplayer stages, not the
   #modern normal-raid solo mode. Retain old saves/read/abandon; no new1p
   #attempt bypasses a known native minimum or an unclosed CP/source gate.
   from els_server.game_data import client_data
   for node in definition['nodes']:
    minimum=client_data().dungeon(node['dungeon']).get('m_MinPlayerCount')
    if type(minimum)is not int or minimum!=1:
     raise ValueError('Current challenge phase has no verified single-player entry')
   from els_server.domain.region_quests import account_dungeon_allowed
   if not account_dungeon_allowed(s.account,(34120+phase*10)if challenge==4 else(34540+phase*10)):
    raise ValueError('Challenge region is locked')
   world=getattr(getattr(s,'application',None),'world',None);party=world.party_of.get(s)if world else None
   if party is not None and not party.get('solo_challenge'):raise ValueError('Local challenge phase requires a solo room')
   if world:
    if party is None:party=dict(id=world.next_party,leader=s,members=[s],ready=set(),dungeon=definition['dummy'],run=None,solo_challenge=True)
    else:party=dict(party,dungeon=definition['dummy'])
   else:
    member=SoloMember(s.account);party=dict(id=900000+s.account.uid,leader=member,members=[member],ready=set(),dungeon=definition['dummy'],run=None,solo_challenge=True)
   from els_server.protocol.protocol_codec import encode_event
   from els_server.protocol.social_messages import party_snapshot
   prepared=[]
   def precommit(state):
    prepared.extend([phase_ack(ack),party_snapshot(party),_notice(state,s.account.uid)])
    for notice in prepared:encode_event(notice)
   store(s).begin(challenge,phase,account_id=account_id,prepare=guard,precommit=precommit)
   if world:
    if s not in world.party_of:world.next_party+=1
    world.parties[party['id']]=party;world.party_of[s]=party
   else:s.solo_challenge_party=party
   return prepared
  if kind==0xae7:
   if event.payload!=b'\xff'*8:raise ValueError('Challenge abandon payload')
   return _abandon(s,event,phase_ack(ack))
  if event.payload not in (b'\0',b'\1'):raise ValueError('Challenge confirmation payload')
  if kind==0xaea and event.payload==b'\1':return _abandon(s,event)
  notice=notification(s)
  from els_server.protocol.protocol_codec import encode_event
  encode_event(notice);guard();return [notice]
 except (ValueError,AttributeError,sqlite3.Error):return [phase_ack(ack,-1)]
