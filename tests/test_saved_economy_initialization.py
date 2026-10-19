"""Saved rewards override only the verified unit scalars in isolated profiles."""
import json,struct,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_messages import character_unit,character_list,client_economy_fields
from local_state import LocalState
from local_session import LocalAccount,LocalSession
from protocol_codec import Event
fields=json.loads((ROOT/'analysis/character-fixture.json').read_text(encoding='utf8'))['fields']
offsets={};pos=0
for f in fields:offsets[f['offset']]=pos;pos+=len(bytes.fromhex(f['wire_hex']))
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'save.sqlite3';account=LocalAccount(LocalState(path));account.enable_rewards().grant(str(uuid.uuid4()),b'local reward test',120,50,lambda _:b'receipt')
 reopened=LocalAccount(LocalState(path));balances=reopened.get_reward_balances()
 args={'enter_town':True,'enter_dungeon':True,'client_build':'dx11_260923','npc_slot_test':True,'gate_test':True,'population_test':True,'clear_test':True}
 reward=LocalSession(reopened,**args,reward_test=True);ordinary=LocalSession(reopened,**args)
 for session in (reward,ordinary):session.role='game';session.phase='characters_ready'
 payload=reward.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1001)))[0].payload[4:]
 assert struct.unpack_from('>Q',payload,offsets['0x5d'])[0]==120
 assert struct.unpack_from('>i',payload,offsets['0x66'])[0]==50
 ordinary_payload=ordinary.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1001)))[0].payload[4:]
 assert ordinary_payload[:pos]==character_unit(initialize_attributes=True)
 unit=character_unit(initialize_attributes=True,economy=balances);baseline=character_unit(initialize_attributes=True)
 allowed={i for off,n in [('0x5d',8),('0x66',4)] for i in range(offsets[off],offsets[off]+n)}
 assert len(unit)==len(baseline) and all(a==b or i in allowed for i,(a,b) in enumerate(zip(unit,baseline)))
 assert unit==payload[:pos]
 listed=character_list('dx11_260923',balances).payload
 assert unit[offsets['0x5d']:offsets['0x5d']+8] in listed
 assert reopened.get_reward_balances()==balances
 for invalid in ({'ed':True,'experience':50},{'ed':-1,'experience':0},{'ed':120,'experience':2**31},{'ed':120}):
  try:client_economy_fields(invalid)
  except ValueError:pass
  else:raise AssertionError('Invalid native scalar accepted')
 try:character_list('legacy',balances)
 except ValueError:pass
 else:raise AssertionError('Legacy economy schema accepted')
print('PASS: saved ED/EXP loaded into unit initialization, exact scalar-only change, normal-profile isolation and native width guards.')
