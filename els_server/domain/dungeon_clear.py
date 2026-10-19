"""Isolated C1 prototype: one local result record; no rewards or persistence."""
from els_server.paths import PROJECT_ROOT
import json,struct
from pathlib import Path
from els_server.protocol.protocol_codec import Event
from els_server.domain.dungeon_population import SHA
from els_server.domain.reward_rules import dungeon_rewards
LOCAL_CLEAR_ED=dungeon_rewards(30000)['clear_ed']
LOCAL_CLEAR_EXPERIENCE=dungeon_rewards(30000)['clear_experience']
def prototype_clear_notice(reward_probe=False):
 name='clear-reward-marker-candidate.json' if reward_probe else 'clear-member-candidate.json'
 data=json.loads((PROJECT_ROOT/'analysis/client-6c6b5180'/name).read_text(encoding='utf8'))
 if reward_probe and (data.get('diagnostic_only') is not True or data.get('no_reward_persistence') is not True):raise ValueError('Reward markers require diagnostic isolation')
 if (data['client_sha256']!=SHA or data['reader']!='0xda64c0' or data['size']!=516 or
     data.get('local_uid')!=1001 or data.get('player_count')!=1 or data.get('rewards') is not False):raise ValueError('Unsupported clear prototype')
 payload=bytes.fromhex(data['wire_hex'])
 if len(payload)!=516 or struct.unpack_from('>I',payload,27)[0]!=1 or struct.unpack_from('>Q',payload,31)[0]!=1001:raise ValueError('Clear prototype identity/size')
 return Event(0x201,kind=0xc1,payload=payload)

def reward_clear_notice(ed,experience,uid=1001,*,elapsed_seconds=0,best_seconds=0):
 """Verified per-run display amounts; local policy, not retail reward formulas."""
 if any(type(v) is not int or not 0<=v<=2**63-1 for v in (ed,experience)):raise ValueError('Clear reward amount bound')
 payload=bytearray(prototype_clear_notice().payload)
 if any(type(v) is not int or not 0<=v<=2**31-1 for v in (elapsed_seconds,best_seconds)):raise ValueError('Clear time bound')
 # DA64C0 -> DTO+0/+AB -> 1046F20 result+0/+38 -> 379F5F0 UI.
 # Private native decode confirmed wire markers 83/61 at offsets 0/460.
 struct.pack_into('>i',payload,0,elapsed_seconds)
 struct.pack_into('>i',payload,460,best_seconds)
 struct.pack_into('>Q',payload,31,uid)
 # DA5DA0 member+31/+41 are uint64. Marker and isolated scalar runs200103
 # independently confirmed ED120/EXP50 in the actual result UI.
 struct.pack_into('>Q',payload,76,ed);struct.pack_into('>Q',payload,84,experience)
 return Event(0x201,kind=0xc1,payload=bytes(payload))

def failed_clear_notice(uid,elapsed_seconds=0):
 # DA64C0 reads the bool at wire+10h into DTO+10h; 1046F20
 # copies it to result+4. Preserve the result roster with no grant amounts.
 raw=bytearray(reward_clear_notice(0,0,uid,elapsed_seconds=elapsed_seconds).payload)
 raw[0x10]=0
 return Event(0x201,kind=0xc1,payload=bytes(raw))
