"""Pure codec reuse must preserve types, failures, copies and scope lifetime."""
import ast,contextvars,copy,pickle,threading,types,unittest
from pathlib import Path
from hypothesis import given,settings,strategies as st
H=Path(__file__).resolve().parent;SOURCE=H.parent/'source/els_server/storage/read_scope.py'
tree=ast.parse(SOURCE.read_text('utf8'))
names={'_ITEM_SCALARS','_flat_item','item_validation_projection'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in names or isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id in names for t in n.targets)]
assert len(nodes)==3
current=contextvars.ContextVar('test_scope',default=None)
clock=types.SimpleNamespace(time=lambda:100.)
ns=dict(_current=current,threading=threading,time=clock,pickle=pickle)
exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-flat-item-validation','exec'),ns)
project=ns['item_validation_projection']
def scope():return types.SimpleNamespace(thread=threading.get_ident(),item_validations={})
def validate(item):
 if type(item.get('uid'))is not int or not 1<=item['uid']<2**63:raise ValueError('UID')
 if type(item.get('count'))is not int or not 1<=item['count']<=99:raise ValueError('count')
 return copy.deepcopy(item)
class FlatValidationTests(unittest.TestCase):
 @settings(max_examples=150,deadline=None,database=None,derandomize=True)
 @given(st.one_of(st.integers(-2,2**64),st.booleans()),st.one_of(st.integers(-1,101),st.booleans()))
 def test_original_results_or_errors_after_valid_cache_entry(self,uid,count):
  token=current.set(scope())
  def outcome(fn,value):
   try:return ('value',fn(value))
   except ValueError as error:return('error',str(error))
  try:
   project(dict(uid=1,count=1),validate)
   item=dict(uid=uid,count=count)
   for _ in range(2):self.assertEqual(outcome(lambda x:project(x,validate),item),outcome(validate,item))
  finally:current.reset(token)
 def test_identical_flat_items_validate_once_and_returns_are_independent(self):
  token=current.set(scope());calls=[]
  def counted(item):calls.append(True);return validate(item)
  try:
   item=dict(uid=1,count=1);first=project(item,counted);first['count']=99
   self.assertEqual(project(item,counted),item);self.assertEqual(len(calls),1)
   clock.time=lambda:101.;project(item,counted);self.assertEqual(len(calls),2)
  finally:clock.time=lambda:100.;current.reset(token)
 def test_nested_and_provenance_models_always_validate(self):
  class Reader(dict):pass
  token=current.set(scope());calls=[]
  def counted(item):calls.append(True);return validate(item)
  try:
   for item in(Reader(uid=1,count=1),dict(uid=1,count=1,options=[0])):
    project(item,counted);project(item,counted)
   self.assertEqual(len(calls),4)
  finally:current.reset(token)
 def test_no_scope_and_other_worker_do_not_consume_cached_validation(self):
  calls=[]
  def counted(item):calls.append(True);return validate(item)
  item=dict(uid=1,count=1);project(item,counted);project(item,counted)
  wrong=scope();wrong.thread=-1;token=current.set(wrong)
  try:project(item,counted);project(item,counted);self.assertFalse(wrong.item_validations)
  finally:current.reset(token)
  self.assertEqual(len(calls),4)
 def test_invalid_items_are_never_cached_and_failures_propagate(self):
  calls=[];token=current.set(scope())
  def counted(item):calls.append(True);return validate(item)
  try:
   for _ in range(2):
    with self.assertRaisesRegex(ValueError,'UID'):project(dict(uid=True,count=1),counted)
   self.assertEqual(len(calls),2);self.assertFalse(current.get().item_validations)
  finally:current.reset(token)
if __name__=='__main__':unittest.main()
