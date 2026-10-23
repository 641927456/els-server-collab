"""Static receiving boundary only; never imports game modules or opens a DB.

Run against the actual staged source tree with an independently exported, read-only
actual Git-parent source directory. It cannot construct that directory or run Git.
Whole-byte/AST comparison verifies only the declared receiving hunks, preserving
all unrelated actual-parent changes. Drift requires renewed source review.
"""
from pathlib import Path
import argparse,ast,hashlib,json
RULES={'runtime': {'els_server/data/ep_pets.json': {'new': True, 'qualified_sha256': '8ada2750184a372a9fb644a71c378dac9ee41c90f48970fce56c782186d50a22', 'hunks': []}, 'els_server/domain/ep_pets.py': {'new': True, 'qualified_sha256': 'be5f8db349ee69082dad1cfed83303d570c98e1d8bb03b16bfb0fa5cba272130', 'hunks': []}, 'els_server/domain/ep_shop.py': {'new': False, 'qualified_sha256': '0d17f5a1c41108d967eabc6126aff8ab17685b44cb57ad12e461a475b7a9e4e0', 'hunks': [{'ordinal': 1, 'before': '    return (Offer(723602,100,1,classes,limit),\n            Offer(723603,10,1,classes,limit),\n            Offer(723604,5,1,classes,limit),\n', 'old': '            Offer(710022,15,100,classes,None))\n', 'new': "            Offer(710022,15,100,classes,None))+_pet_offers(classes)\n\n\ndef _pet_offers(classes):\n    from els_server.domain.ep_pets import definitions\n    return tuple(Offer(row['template'],row['price_ep'],row['quantity'],classes,None)\n                 for row in definitions())\n", 'after': ''}]}, 'els_server/domain/inventory_items.py': {'new': False, 'qualified_sha256': 'c52e2bfdd040f4b9f155c640c7d87a8b9dd4b4e4f77254ab3de61116ce049160', 'hunks': [{'ordinal': 1, 'before': "if _t in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t])!=_expected:raise ValueError('Conflicting manual magic potion definition')\r\nVERIFIED_TEMPLATES[_t],TEMPLATE_BAG_GROUPS[_t],TEMPLATE_MAX_STACKS[_t]=_expected\r\n\r\n", 'old': '', 'new': "# Four exact permanent EP pet acquisition items; no pet activation producer.\r\nfrom els_server.domain.ep_pets import definitions as _ep_pet_items\r\nfor _row in _ep_pet_items():\r\n if _row['template'] in VERIFIED_TEMPLATES:raise ValueError('Conflicting EP pet inventory definition')\r\n VERIFIED_TEMPLATES[_row['template']]=_row['metadata']\r\n TEMPLATE_BAG_GROUPS[_row['template']]=_row['group']\r\n TEMPLATE_MAX_STACKS[_row['template']]=_row['max_stack']\r\n\r\n", 'after': '# User policy (2026-10-18): raise existing stackable items to at least 999.\r\n# Original catalog evidence stays immutable. Equipment/singletons stay at one;\r\n# native material stacks already above 999 retain their larger limits.\r\n'}]}, 'els_server/protocol/ep_shop_messages.py': {'new': False, 'qualified_sha256': 'd2ba97651e53fb787e04b65ba165b32fcae89574b71b78482735938d45290f71', 'hunks': [{'ordinal': 1, 'before': "# server's display profile, not original retail catalogue values. Fields8/27\n# use the separately reviewed canonical-zero compatibility contract.\n_PROFILES={723602:(100,1,1),723603:(10,1,2),723604:(5,1,3),710022:(15,100,4)}\n", 'old': '', 'new': "from els_server.domain.ep_pets import definitions as _ep_pet_definitions\n_PROFILES.update({row['template']:(row['price_ep'],row['quantity'],row['display_rank'])\n                  for row in _ep_pet_definitions()})\n", 'after': '_LIMITED=frozenset((723602,723603,723604))\n\n\n'}, {'ordinal': 2, 'before': '\ndef catalogue_records(offers):\n    from els_server.domain.ep_shop import Offer\n', 'old': '    if type(offers) is not tuple or len(offers)>4 or any(type(o) is not Offer for o in offers):\n', 'new': '    if type(offers) is not tuple or len(offers)>8 or any(type(o) is not Offer for o in offers):\n', 'after': "        raise ValueError('Unqualified EP goods catalogue')\n    if len({o.template for o in offers})!=len(offers):raise ValueError('Duplicate EP goods')\n    rows=[]\n"}]}}, 'ABI': [{'path': 'els_server/game_data.py', 'name': 'client_data', 'binding_AST_sha256': 'f29d717ae3dd6dc34df91fb3c5d7c1c1b995b7308213b7f1d71530ca1f8b2c5d'}, {'path': 'els_server/game_data.py', 'name': 'CLIENT_SHA', 'binding_AST_sha256': '986a71930c1fd7be6e8ec1f2717cdc26804e08b40e905f98ae914057fe441105'}, {'path': 'els_server/domain/companions.py', 'name': 'catalog', 'binding_AST_sha256': 'd1f3919f6676d7d7ca80a6653db934673ef238e88e7cb90c0add196b39a07831'}, {'path': 'els_server/domain/character_rules.py', 'name': 'CLASSES', 'binding_AST_sha256': '6c424b0b1e31bcccc485d5dbff32e127a5ac2e6fc187174869e258f5b2382786'}, {'path': 'els_server/domain/ep_pets.py', 'name': 'definitions', 'binding_AST_sha256': '178e56bb4894e586dcde6fed40d9ad76a81068d009d1239ac469a98ff197f14c'}, {'path': 'els_server/domain/ep_points.py', 'name': 'validate', 'binding_AST_sha256': 'dd97714e7a06ed258e5d50e8db7c92f3a477f0c410c7fa913c3bfa157378bc4a'}, {'path': 'els_server/domain/inventory_items.py', 'name': 'inventory_payload', 'binding_AST_sha256': '239114e3153c3ea73a032acfe9f675e70a3c485ae3e215fa7126ad16a90b91b8'}, {'path': 'els_server/protocol/protocol_codec.py', 'name': 'Event', 'binding_AST_sha256': 'fc738d466208b6b9ba4a8e3b8273c228079c8bdc5c21158e1a857ab6f7241e8d'}, {'path': 'els_server/domain/ep_shop.py', 'name': 'Offer', 'binding_AST_sha256': 'e6eaa2ac6695d64c8a4b8d64d439d76c1ad669e0145b48665c0f08dd15e96288'}], 'prerequisite_exact_sha256': {'els_server/storage/ep_points.py': 'c1130156785e3acd924ad0fdde083106f88aecc999e00333b126d371ec497919', 'els_server/storage/ep_shop.py': '5a03cbcae27d377d9ca6340d784d9e02beb4aea7bc5612e3ccf93c941db2c724', 'els_server/domain/companion_flow.py': 'c52567598cbe1096f2a91e3a944d73512fdd87a9f4edfa373d279fa3a5bd350e', 'els_server/storage/companion_state.py': 'df12b8a065d61f2db82956f3d787d6fe342435cc155ace8bffa1f270698910bc', 'els_server/storage/boosting_2026_limited_pet.py': '8c569090015eb87f354bf205d6a539054cc29393e42a70dceadf7a59dfa318ac'}, 'data_path': 'els_server/data/ep_pets.json', 'policy_sha256': '9eb54d794fd080a9adf0813c09717864d39f26fe7581fa940e3b923a50a8cb86', 'templates': [723605, 723606, 723607, 723608]}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def binding(raw,name):
 result=[]
 for n in ast.parse(raw).body:
  names=[]
  if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):names=[n.name]
  elif isinstance(n,(ast.Assign,ast.AnnAssign)):
   ts=n.targets if isinstance(n,ast.Assign)else[n.target]
   names=[x.id for t in ts for x in ast.walk(t)if isinstance(x,ast.Name)]
  elif isinstance(n,(ast.ImportFrom,ast.Import)):names=[a.asname or a.name.split('.')[0]for a in n.names]
  if name in names:result.append(ast.dump(n,include_attributes=False))
 assert result,('Missing ABI',name)
 return sha(json.dumps(result,separators=(',',':')).encode())
def apply(raw,hunks):
 pairs=[]
 for h in hunks:
  a=h['before']+h['old']+h['after'];b=h['before']+h['new']+h['after'];hits=[]
  for eol in(b'\r\n',b'\n'):
   aa=a.encode().replace(b'\r\n',b'\n').replace(b'\n',eol)
   bb=b.encode().replace(b'\r\n',b'\n').replace(b'\n',eol)
   if raw.count(aa)==1 and(aa,bb)not in hits:hits.append((aa,bb))
  assert len(hits)==1,('Ambiguous/drifted receiving hunk',h['ordinal'])
  aa,bb=hits[0];raw=raw.replace(aa,bb,1);pairs.append((aa,bb))
 return raw,pairs
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--before-root',type=Path,required=True);a=p.parse_args()
 assert a.root.resolve()!=a.before_root.resolve()
 for name,rule in RULES['runtime'].items():
  target=a.root/name;assert target.is_file()and not target.is_symlink()and not target.is_junction();raw=target.read_bytes()
  if rule['new']:
   assert not(a.before_root/name).exists()and sha(raw)==rule['qualified_sha256'],('New source drift',name)
  else:
   before=(a.before_root/name).read_bytes();expected,pairs=apply(before,rule['hunks']);assert raw==expected,('Whole-file receiving scope',name)
   inverse=raw
   for old,new in reversed(pairs):assert inverse.count(new)==1;inverse=inverse.replace(new,old,1)
   assert inverse==before and ast.dump(ast.parse(inverse))==ast.dump(ast.parse(before))
  if name.endswith('.py'):compile(raw,name,'exec')
 for row in RULES['ABI']:
  assert binding((a.root/row['path']).read_bytes(),row['name'])==row['binding_AST_sha256'],('ABI source drift',row['path'],row['name'])
 for name,expected in RULES['prerequisite_exact_sha256'].items():assert sha((a.root/name).read_bytes())==expected,('Missing prerequisite source',name)
 # Only the source-owned server data is parsed, never raw client resources.
 data=json.loads((a.root/RULES['data_path']).read_bytes());assert data['policy_authorization_sha256']==RULES['policy_sha256']
 assert [r['template']for r in data['inventory']]==RULES['templates']
 print(json.dumps(dict(ok=True,source_boundary_only=True,runtime_files=len(RULES['runtime']),whole_actual_parent_hunks_preserved=True,ABI_bindings=len(RULES['ABI']),SQL_TLS_native_or_game_imports=0)))
if __name__=='__main__':main()
