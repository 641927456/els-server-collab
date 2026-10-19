"""New schemas must remain opt-in and preserve the existing save/legacy path."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_messages import character_list
from local_session import LocalSession,LocalAccount
from protocol_codec import Event
from local_state import movement_location
native=bytes.fromhex('43f40efa43179375c4488fbe00000000010000000100000000900000000000013c29')
board,progress,xyz=movement_location(native,'dx11_260923')
assert board==0 and progress==0 and len(xyz)==3
assert movement_location(native[:-4])==(board,progress,xyz)
for payload,build in [(native,'legacy'),(native[:-4],'dx11_260923'),(native[:-5]+b'\2'+native[-4:],'dx11_260923'),(native+b'\0','dx11_260923')]:
 try:movement_location(payload,build)
 except ValueError:pass
 else:raise AssertionError('Wrong movement schema, bool or truncated tail accepted')
legacy=character_list();updated=character_list('dx11_260923')
assert len(legacy.payload)==814 and len(updated.payload)==826
assert legacy.payload==updated.payload[:814] and updated.payload[-12:]==bytes(12)
account=LocalAccount();before=(account.get_location(),account.get_skills(),account.get_layout(),account.get_bindings())
for name,size in [('legacy',814),('dx11_260923',826)]:
 s=LocalSession(account,client_build=name);s.role='game';s.phase='terms_ready'
 reply=s.handle(Event(0x202,kind=0x485));assert len(reply)==1 and reply[0].kind==0x488 and len(reply[0].payload)==size
 assert s.phase=='characters_ready'
assert before==(account.get_location(),account.get_skills(),account.get_layout(),account.get_bindings())
for fn in (character_list,lambda p:LocalSession(client_build=p)):
 try:fn('unverified-build')
 except ValueError:pass
 else:raise AssertionError('Unknown schema accepted')
print('PASS: opt-in updated character schema, legacy wire preservation, save isolation and unknown-build rejection.')
