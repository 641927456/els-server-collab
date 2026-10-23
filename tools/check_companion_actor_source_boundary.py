"""Portable source-only regression boundary: no imports of game/SQL/network/Git."""
from pathlib import Path
import ast,hashlib,json,sys
EXPECTED={'els_server/domain/companion_flow.py': 'c52567598cbe1096f2a91e3a944d73512fdd87a9f4edfa373d279fa3a5bd350e', 'els_server/storage/companion_state.py': 'df12b8a065d61f2db82956f3d787d6fe342435cc155ace8bffa1f270698910bc', 'els_server/storage/boosting_2026_limited_pet.py': '8c569090015eb87f354bf205d6a539054cc29393e42a70dceadf7a59dfa318ac'}
BASE={'els_server/domain/companion_flow.py': 'fb13b0e32118c01eff1f975e4c062b6d0c49b1d28f9368115a31913f673f3c37', 'els_server/storage/companion_state.py': '883f75a8eea1e3b0902e3c136ec9701fd1e49528ca9a93ffeeb5a1d3702c6ba3', 'els_server/storage/boosting_2026_limited_pet.py': 'e686274511c3672ebc925314bbb75227daa66902e15ae5c4c19582955e4d8961'}
HELPERS={'els_server/domain/equipment_chip_flow.py': {'current_lease': 'bce8c2b27eb9467abc15fc61311019272081a788e3693ad728d64d195dbd9c72'}, 'els_server/storage/item_actor.py': {'require_active_character': '2a97c5d9e7ab72ca57d80f1c19e9928ed884bddbf481940cdaa59b42de354ca2'}, 'els_server/storage/profession_state.py': {'require_owner': '71481fab134df84535a76cd9525e4968fb1b25bf45dad73d4c221414ac5043d1'}, 'els_server/storage/character_schema.py': {'character_uid': '034bbb737565884e8641e8ae1928b420cccd38cbfd218aa7ddcba39b22fe12b7'}, 'els_server/storage/inventory_state.py': {'ensure_inventory': '212745ea15c05cffd01f662f4290418635c6456bd9612deef1ee8c0cd0001567', 'load_items': '9a6b4192c3b854526fe3294a918d95b584d882a08d6bdaba3c5b3697140722de'}, 'els_server/application.py': {'Application.call': '4af21d508e655512d28ba56eab942f3c72d62b0481b044b6b8fd090bdff9908c'}, 'els_server/domain/companions.py': {'catalog': '23d18609ce4f4ec810a5a4d053552da5054953a2457ad62744985b3452160b90'}, 'els_server/domain/boosting_2026_limited_pet.py': {'enabled': '3409b96400fa12687ff6d07618b1393b2f52d53d8491a2ff2ad471cb08d01066', 'definition': '6ddacdb38f357f72ef240c2603af12fc859ab53891954ff149c01234d345cf22'}}
FRAGMENT=["ImportFrom(module='els_server.domain.companion_flow', names=[alias(name='handle', asname='companion_handle')], level=0)", "Assign(targets=[Name(id='companion_reply', ctx=Store())], value=Call(func=Name(id='companion_handle', ctx=Load()), args=[Name(id='self', ctx=Load()), Name(id='event', ctx=Load()), Name(id='request_sequence', ctx=Load())]))", "If(test=Compare(left=Name(id='companion_reply', ctx=Load()), ops=[IsNot()], comparators=[Constant(value=None)]), body=[Return(value=Name(id='companion_reply', ctx=Load()))])"]
def digest(data):return hashlib.sha256(data).hexdigest()
def function(raw,name):
 nodes=ast.parse(raw).body
 for part in name.split('.'):
  matches=[n for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))and n.name==part];assert len(matches)==1,(name,part)
  node=matches[0];nodes=node.body
 return ast.dump(node,include_attributes=False)
def check(root,mode='after'):
 root=Path(root).resolve();assert mode in('before','after')
 for rel,want in (EXPECTED if mode=='after'else BASE).items():
  raw=(root/rel).read_bytes();assert digest(raw)==want,rel;compile(raw,rel,'exec')
 for rel,functions in HELPERS.items():
  raw=(root/rel).read_bytes()
  for name,want in functions.items():assert digest(function(raw,name).encode())==want,(rel,name)
 found=[]
 for n in ast.walk(ast.parse((root/'els_server/domain/local_session.py').read_bytes())):
  body=getattr(n,'body',None)
  if not isinstance(body,list):continue
  for i,k in enumerate(body):
   if isinstance(k,ast.ImportFrom)and k.module=='els_server.domain.companion_flow':found.append([ast.dump(x,include_attributes=False)for x in body[i:i+3]])
 assert found==[FRAGMENT],'Companion outer delegation ABI changed'
 return dict(ok=True,mode=mode,runtime_replacements=3,source_compile_static_only=True,SQL_TLS_native_network_Git_actions=0)
if __name__=='__main__':print(json.dumps(check(Path(__file__).resolve().parents[1],sys.argv[1]if len(sys.argv)>1 else'after')))
