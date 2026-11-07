"""Bind the four-file metadata delta and preserve all unrelated handlers/guards."""
import ast,hashlib,json,subprocess,sys
from pathlib import Path
A=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def tree(path):return ast.parse(path.read_bytes())
def cls(t,name):return next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name==name)
binding=read(A/'source-bindings.json');actual={}
for base in binding['base_refs']:
 root=(A/base).resolve()
 for path in root.rglob('*.py'):actual[path.relative_to(root).as_posix()]=sha(path)
assert actual==binding['base_source_files']and len(actual)==30
for name,row in binding['changed_files'].items():
 assert sha(A/'source'/name)==row['sha256']and sha(A/'parent'/name)==row['parent_sha256']==actual[name]
 actual[name]=row['sha256']
assert actual==binding['effective_source_files']and len(binding['changed_files'])==4
for name,digest in binding['portable_test_files'].items():assert sha(A/name)==digest
native=read(A/'native-metadata-peer.json');assert native['ok']and len(native['checks'])==5 and all(native['checks'].values())
assert {k.split('/',1)[1]:v for k,v in native['source'].items()}==actual
assert native['owned_runtime_removed']and not native['connections']and not native['errors']and native['GIL_enabled']is False
report=read(A/'twenty-town-five-minute.json');assert report['seconds']==300 and report['movement_requests']==35000 and report['all_sources_matched']==665000
assert report['metadata']['n']==report['metadata_queries_preserved']==20 and report['peer_coordinate_deliveries']==665000
assert not report['production_installed']and not report['public_network_qualified']and report['cleanup']==dict(owned_runtime_removed=True,connections=0,errors=[])
cause=read(A/'tail-cause.json');assert cause['original87ms_event_has_no_exact_pair']and not cause['original87ms_exact_cause_reconstructed']

name='els_server/application.py';before=tree(A/'parent'/name);after=tree(A/'source'/name)
handle=next(n for n in cls(after,'FriendsSession').body if isinstance(n,ast.FunctionDef)and n.name=='handle')
fast=ast.parse('if self.application.dungeon_workers.town_metadata(self.handle,(event,)):\n return super()._handle(event,request_sequence)').body[0]
found=[n for n in handle.body if ast.dump(n)==ast.dump(fast)];assert len(found)==1;handle.body.remove(found[0])
class Window(ast.NodeTransformer):
 count=0
 def visit_Call(self,node):
  if isinstance(node.func,ast.Attribute)and node.func.attr=='town_peer_delivery':
   assert ast.unparse(node.func.value)=='self.dungeon_workers';self.count+=1;node.func.attr='ordinary_town_move'
  return self.generic_visit(node)
normal=Window();normal.visit(after);assert normal.count==2 and ast.dump(before)==ast.dump(after)

name='els_server/dungeon_workers.py';before=tree(A/'parent'/name);after=tree(A/'source'/name);c=cls(after,'DungeonWorkers')
expected=ast.parse('''class Original:
 @staticmethod
 def town_metadata(function,args):
  return(bool(args)and getattr(args[0],'kind',None)==0x48d and DungeonWorkers.town_movement(function,args))
 @staticmethod
 def town_peer_delivery(function,args):
  return(DungeonWorkers.ordinary_town_move(function,args)or DungeonWorkers.town_metadata(function,args))
''').body[0].body
for node in expected:
 matches=[n for n in c.body if ast.dump(n)==ast.dump(node)];assert len(matches)==1;c.body.remove(matches[0])
assert ast.dump(before)==ast.dump(after),'Original eligibility, queues, locks and protected phases remain exact'

name='els_server/domain/local_session.py';before=tree(A/'parent'/name);after=tree(A/'source'/name)
def metadata(t):
 method=next(n for n in cls(t,'LocalSession').body if isinstance(n,ast.FunctionDef)and n.name=='_handle')
 return next(n for n in method.body if isinstance(n,ast.If)and ast.unparse(n.test)=='kind == 1165')
old,new=metadata(before),metadata(after)
assert ast.dump(new.body[0])==ast.dump(old.body[0])
assert ast.dump(new.body[-1])==ast.dump(ast.parse('return responses(kind,self.client_build,account_id=self.account.account_id)').body[0])
new.body[-1]=old.body[-1];assert ast.dump(before)==ast.dump(after),'All native handlers and original role/phase guard stay exact'

name='els_server/domain/session_auxiliary.py';before=tree(A/'parent'/name);after=tree(A/'source'/name)
class MetadataAuxiliary(ast.NodeTransformer):
 count=0
 def visit_BoolOp(self,node):
  if ast.dump(node)==ast.dump(ast.parse('friends_auxiliary_noop(session,args[0])or session.application.dungeon_workers.town_metadata(function,args)',mode='eval').body):
   self.count+=1;return node.values[0]
  return self.generic_visit(node)
normal=MetadataAuxiliary();normal.visit(after);assert normal.count==1 and ast.dump(before)==ast.dump(after)
subprocess.run([sys.executable,'-B',str(A/'test_metadata_peer_models.py'),'-v'],check=True)
print(json.dumps(dict(ok=True,source_files=30,changed_files=4,portable_checks=7,native_checks=5,original_builder_and_all_other_handlers_preserved=True)))
