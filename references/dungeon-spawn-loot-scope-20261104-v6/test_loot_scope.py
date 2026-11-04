"""Portable behavior regression for the exact archived production function."""
import ast,copy,hashlib,json,random,sys,unittest
from pathlib import Path
from types import SimpleNamespace
W=Path(__file__).resolve().parent
SOURCE=W/('source'if(W/'source').is_dir()else'candidate')/'els_server/domain/dungeon_routes.py'
def function(path,data):
 tree=ast.parse(path.read_bytes());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='loot_scope_sha256')
 ns=dict(hashlib=hashlib,json=json,route_catalog=lambda:SimpleNamespace(_data=data))
 exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
 return ns['loot_scope_sha256']
def fixture():
 actor=dict(template=55,source_index=1,active=True,boss=True,no_drop=False,team=1,ally=False)
 return dict(routes={'1':dict(source='map.lua',npc_level=99)},graphs={'map.lua':dict(source='map.lua',source_sha256='a'*64,reachable_parts=[0],encounter={'gates':[1]},stages={'0':dict(allowed_summons=[7],parts={'0':dict(groups=[{'npcs':[actor]}],conditions=[{'kind':4}])}),'1':dict(allowed_summons=[],parts={})})})
class Scope(unittest.TestCase):
 def setUp(self):self.data=fixture();self.digest=function(SOURCE,self.data);self.base=self.digest(['1'])
 def test_dynamic_admission_never_changes_loot_identity(self):
  rng=random.Random(20261104)
  for _ in range(128):
   for s in self.data['graphs']['map.lua']['stages'].values():s['allowed_summons']=rng.sample(range(1,20000),rng.randrange(50))
   self.assertEqual(self.digest(['1']),self.base)
 def test_each_static_actor_authority_field_is_bound(self):
  actor=self.data['graphs']['map.lua']['stages']['0']['parts']['0']['groups'][0]['npcs'][0]
  for key,value in dict(template=56,source_index=2,active=False,boss=False,no_drop=True,team=0,ally=True).items():
   old=actor[key];actor[key]=value;self.assertNotEqual(self.digest(['1']),self.base,key);actor[key]=old
 def test_routes_transitions_source_and_future_economic_fields_are_bound(self):
  g=self.data['graphs']['map.lua'];s=g['stages']['0'];p=s['parts']['0']
  mutations=[(self.data['routes']['1'],'npc_level',100),(g,'source_sha256','b'*64),(g,'reachable_parts',[0,1]),(g,'encounter',{}),(s,'future_static_rule',1),(p,'conditions',[{'kind':2}]),(p,'groups',[])]
  for owner,key,value in mutations:
   present=key in owner;old=copy.deepcopy(owner.get(key));owner[key]=value;self.assertNotEqual(self.digest(['1']),self.base,key)
   if present:owner[key]=old
   else:del owner[key]
 def test_missing_declared_route_is_an_error(self):
  with self.assertRaises(KeyError):self.digest(['2'])
if __name__=='__main__':unittest.main()
