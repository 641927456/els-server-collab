"""Exact AST delta for the own-end handoff; shared ordering and business stay fixed."""
import ast,copy
def normalize_solo_end(before,after):
 def actor(tree):return next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='FriendsSession')
 def method(cls,name):return next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name==name)
 old=actor(before);new=actor(after);original=method(old,'handle');updated=method(new,'handle')
 block=next(n for n in original.body if isinstance(n,ast.With)and any(isinstance(v,ast.Call)and ast.unparse(v.func)=='self._shared_request'for v in ast.walk(n)))
 helper=method(new,'_shared_reply');assert ast.dump(ast.Module(body=helper.body,type_ignores=[]))==ast.dump(ast.Module(body=block.body[1].body,type_ignores=[]))
 assert ast.unparse(helper.args)=='self, event, result';new.body.remove(helper)
 expected=ast.parse('''own_end=(event.event_id==0x202 and event.kind==0x67
 and self.application.dungeon_workers.solo_transition(self.handle,(event,)))
with self.application.world_lock:
 result=self._shared_request(event,request_sequence,defer_solo_end=own_end)
 if result is not None:return self._shared_reply(event,result)
if own_end:
 from els_server.domain.luciel_native_end import handle as luciel_end_handle
 result=luciel_end_handle(self,event,request_sequence)
 if result is not None:
  with self.application.world_lock:
   return self._shared_reply(event,self.activity_reply(result+self._mailbox_messages()))
''').body
 index=next(i for i,n in enumerate(updated.body)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='own_end'for t in n.targets))
 assert [ast.dump(n)for n in updated.body[index:index+3]]==[ast.dump(n)for n in expected]
 updated.body[index:index+3]=[copy.deepcopy(block)]
 shared=method(new,'_shared_request');assert len(shared.args.kwonlyargs)==1 and shared.args.kwonlyargs[0].arg=='defer_solo_end'and shared.args.kw_defaults[0].value is False
 shared.args.kwonlyargs=[];shared.args.kw_defaults=[]
 guards=[n for n in shared.body if isinstance(n,ast.If)and isinstance(n.test,ast.Name)and n.test.id=='defer_solo_end']
 assert len(guards)==1 and ast.dump(guards[0])==ast.dump(ast.parse('if defer_solo_end:return None').body[0]);shared.body.remove(guards[0])
