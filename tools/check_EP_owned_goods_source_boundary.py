"""Portable source-only boundary check. No game imports, SQL, network or Git."""
from pathlib import Path
import ast,hashlib,json
EXPECTED={'els_server/domain/ep_shop.py': 'a5c87fac7d1eeb54d3178bbf11eaed87b630264f773d26d11d9547d1e8bb45d0', 'els_server/storage/ep_shop.py': '5a03cbcae27d377d9ca6340d784d9e02beb4aea7bc5612e3ccf93c941db2c724', 'els_server/storage/ep_points.py': 'c1130156785e3acd924ad0fdde083106f88aecc999e00333b126d371ec497919', 'els_server/protocol/ep_shop_messages.py': '51bfaa7e2e73243982bb8da73108050eed0fb41ad3d5477ea4d74e001a86f4aa', 'els_server/domain/ep_shop_flow.py': 'dd67af5a42e751365074fe96e4dfec60b2b35f531f72fd5cbba8aee5c79fe4ec', 'els_server/domain/ep_conversion_flow.py': '1b790e3273ec85ace79731cb0d945357c381d192fd292228bd648b9c8b768578', 'els_server/protocol/ep_conversion_messages.py': 'ac6245736e944bf13f496a4455aa083096bad7e0f99d5b8e4dd8e9f83e1d7482'}
HELPERS={'els_server/storage/character_schema.py': {'character_uid': '034bbb737565884e8641e8ae1928b420cccd38cbfd218aa7ddcba39b22fe12b7'}, 'els_server/domain/ep_points.py': {'validate': '51f3382117ecd4f1dda5bcd5f59831bd989ec48cb101e379883452f182eb4627'}, 'els_server/storage/item_actor.py': {'require_active_character': '2a97c5d9e7ab72ca57d80f1c19e9928ed884bddbf481940cdaa59b42de354ca2'}, 'els_server/storage/inventory_state.py': {'ensure_inventory': '212745ea15c05cffd01f662f4290418635c6456bd9612deef1ee8c0cd0001567', 'grant_items': 'e9ecc7f55885a8ceef391522afa2efe24d802e64b6743b7011c76a8c44a0d462', 'load_items': '9a6b4192c3b854526fe3294a918d95b584d882a08d6bdaba3c5b3697140722de', 'validate_plan': 'fd5844e77ecbf68e9c05d2b3165345c5b231b1e4b61c68abd6e259662262c8c2'}, 'els_server/storage/bag_capacity.py': {'allowances': '809c91050b18bc7fc7725fafb7eb1345beb3a1d45a529909b23bb99f5e8e7493'}, 'els_server/storage/inventory_management.py': {'_updates': '855f301dee389920ee6150915777ad094db51d7e91f9aec7e6bb41beb8ed9de8'}, 'els_server/domain/inventory_items.py': {'inventory_payload': 'e2785d7ed38dba334bd17eb6514f40288d3dbaeaac5f55208d20b2b7404bf5e9'}, 'els_server/domain/consumables.py': {'catalog': '3869de9d447a5fc8f6a3b75d01ff4b866423e98d28e7903d698dc5ee83ed954c', 'manual_magic_potion_definition': '46916ed97058a5afc0232471cc5d8e2e5ec73985ea2624886b90c45745ebc48a'}, 'els_server/domain/dungeon_equipment_loot_flow.py': {'current_lease': 'cfb9d0facc52d888f38b92d8c013b0587a19e24b3cc24f1895fbb1374bf1a17d'}, 'els_server/domain/ep_conversion.py': {'Rate': 'cad8c6b30155051310dabd047a88a9cfe655ded95dc438a7dcda05a874208a2d', 'ConversionResult': '08f222575c658474ffc43a14dbd9f3c969021ef14ec46d2e9d4f1be46292c97e', 'ConversionRejected': 'f7ceeb9bc9d5184715371de24de463ef5ae77ffbbd1700acd3997dc58cb319fb', 'policy': 'a2c92f6dca92b228ee189683b389cb9e7b60abbe63c6b660245527affc316405'}, 'els_server/storage/ep_conversion.py': {'wallet': '611b57a574a5ff116c63f3caca846572b47b419b03a1ed77f595a7bc8b91682b', 'convert': 'a0bd87d2bc59b49bc0958a5260878ce0c7c312a2d72e91700613e33bacbfd3e7'}, 'els_server/protocol/protocol_codec.py': {'Event': '75c5234d10b68a7a3994490c00bbcbac237684b976bfc30be821a0e5ec747538', 'encode_event': '7ee6f44890c693c64ac201a4342dddedb1826b199c5e048ae702b5afcc14bab4'}}
DATA={'els_server/data/select_cubes.json': 'a1d6844860f4fc937f716e07335c1c200fded24beb3c9d83f10c2fe9ad8a2d75', 'els_server/data/ep_essence_bag.json': '12c2c87dcd4691b42fb68a1e1ed7c94f6bd9bbbc533881451c0ce85af24dcb34', 'els_server/domain/ep_essence_bag.py': '72ff0f635d1e2c13360271a589186dcaec8396fbe95fec67e321d7c8ce9a36e3', 'els_server/data/client/consumables.json': 'b84011dfb077a797f7126a0e96a87dc74641d13c57ad052081c07156e228f8d1', 'els_server/data/client/consumables.manifest.json': '12993971eadaa2bfea20eddb0745aacad3b7af52bf6fe1ef28dfff063a0bf1a0'}
CREDIT_PREFIX_LEN=1467
CREDIT_PREFIX_SHA='f595f872725238588e471add90c00d40eb0f8612a17d113bcbc15241be5d7bd5'
CALLER=["ImportFrom(module='els_server.domain.ep_conversion_flow', names=[alias(name='handle', asname='ep_conversion_handle')], level=0)", "Call(func=Name(id='ep_conversion_handle', ctx=Load()), args=[Name(id='self', ctx=Load()), Name(id='event', ctx=Load()), Name(id='request_sequence', ctx=Load())])"]
def digest(raw):return hashlib.sha256(raw).hexdigest()
def definitions(raw):
 tree=ast.parse(raw);nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
 assert len(nodes)==len({n.name for n in nodes})
 return {n.name:n for n in nodes}
def check(root):
 root=Path(root).resolve()
 for rel,want in EXPECTED.items():
  raw=(root/rel).read_bytes();assert digest(raw)==want,rel;compile(raw,rel,'exec');definitions(raw)
 raw=(root/'els_server/storage/ep_points.py').read_bytes();assert digest(raw[:CREDIT_PREFIX_LEN])==CREDIT_PREFIX_SHA
 for rel,names in HELPERS.items():
  rows=definitions((root/rel).read_bytes())
  for name,want in names.items():assert digest(ast.dump(rows[name],include_attributes=False).encode())==want,(rel,name)
 for rel,want in DATA.items():assert digest((root/rel).read_bytes())==want,rel
 tree=ast.parse((root/'els_server/domain/local_session.py').read_bytes())
 imports=[n for n in ast.walk(tree)if isinstance(n,ast.ImportFrom)and n.module=='els_server.domain.ep_conversion_flow']
 calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='ep_conversion_handle']
 assert len(imports)==len(calls)==1 and [ast.dump(n,include_attributes=False)for n in imports+calls]==CALLER
 return dict(passed=True,runtime_files=7,compile_static_only=True,helper_definitions=sum(map(len,HELPERS.values())),SQL_TLS_native_Git_network_actions=0)
if __name__=='__main__':print(json.dumps(check(Path(__file__).resolve().parents[1])))
