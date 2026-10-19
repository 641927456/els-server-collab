"""Time sync is scoped to loaded DX11 dungeon sessions and has no save effect."""
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from local_session import LocalSession
from protocol_codec import Event,Keys,encode_event,decode_event,encode_frame,decode_frame

for build in ('legacy','dx11_260923'):
 for enabled in (False,True):
  for role in (None,'frontend','game'):
   for phase in ('new','game_connected','town_ready','dungeon_loading','dungeon_active','map_loading','closing'):
    for loaded in (False,True):
     session=LocalSession(enter_town=True,enter_dungeon=enabled,client_build=build)
     session.role=role;session.phase=phase;session.dungeon_substage_synced=loaded
     before=(session.phase,session.account.get_location(),session.account.get_skills(),set(session.completed))
     expected=[Event(0x201,kind=0x9c,payload=bytes(4))] if build=='dx11_260923' and enabled and role=='game' and phase=='dungeon_active' and loaded else []
     assert session.periodic_notifications()==expected
     assert session.periodic_notifications()==expected
     assert (session.phase,session.account.get_location(),session.account.get_skills(),session.completed)==before
keys=Keys(bytes(range(8)),bytes(range(8,16)))
for sequence,message in enumerate([Event(0x201,kind=0xb4,payload=bytes(4)),Event(0x201,kind=0x9c,payload=bytes(4)),Event(0x201,kind=0x68,payload=bytes(4))],2):
 wire=encode_frame(encode_event(message),keys,spi=123,sequence=sequence)
 assert decode_event(decode_frame(wire,keys,expected_sequence=sequence).plaintext)==message
print('PASS: dungeon time-sync phase/build/loading controls, repeated notifications, save isolation and interleaved authenticated frames.')
