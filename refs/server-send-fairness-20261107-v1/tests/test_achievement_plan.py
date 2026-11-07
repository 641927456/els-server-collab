"""Extracted real planners: preserve original updates, operation digest and due metadata."""
import ast,copy,hashlib,json,os,types,unittest
from pathlib import Path
from hypothesis import given,settings,strategies as st
H=Path(__file__).resolve().parent;S=H.parent/'source/els_server';B=H.parent/'runtime-parent/els_server'
def functions(path):return[n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name in('pending_updates','reconcile')]
old=functions(B/'storage/achievement_profiles.py');new=functions(S/'storage/achievement_profiles.py')
class FakeState:
 def __init__(self):self.calls=[]
 def exists(self,db):return True
 def record(self,db,account,owner,updates,operation,now):
  self.calls.append((account,owner,copy.deepcopy(updates),operation,now))
  return dict(completed=[r['achievement']for r in updates if r['complete']],replayed=False)
def namespace(nodes,days,active,previous,selected):
 now=2000000000;threshold={7:10,10:10,18:10,20:100,29:10,50:6,34:4,49:20,66:1};state=FakeState()
 parameters={7:dict(m_eBuffTempletID=503),34:dict(m_iItemID=200),49:dict(m_iDungeonID=100),66:dict(m_iNpcId=17)}
 catalog=lambda:{kind:dict(conditions=[dict(type=kind,id=1,parameters=dict(m_iCount=target,**parameters.get(kind,{})))])for kind,target in threshold.items()}
 rows=[(kind,1,value,value>=threshold[kind])for kind,value in zip(threshold,previous)]
 db=types.SimpleNamespace(in_transaction=True,execute=lambda *unused:rows)
 ns=dict(hashlib=hashlib,json=json,CONDITION_TYPES=selected,catalog=catalog,state=state,
  profession_state=types.SimpleNamespace(exists=lambda db:False),resonance_state=None,
  collection_counts=lambda *args:{(50,50):5},history_counts=lambda *args:{(7,503):8,(10,0):3,(18,0):4,(29,0):9,(34,200):3,(49,100):19,(66,17):1},
  couple_duration=lambda *args:(days,now-days*86400-123 if active else None))
 exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-achievement-profile','exec'),ns)
 return ns,db,state,now
class ProfilePlanTests(unittest.TestCase):
 @settings(max_examples=180,deadline=None,database=None,derandomize=True)
 @given(st.integers(0,3650),st.booleans(),st.tuples(st.integers(0,15),st.integers(0,15),st.integers(0,15),st.integers(0,3650),st.integers(0,15),st.integers(0,10),st.integers(0,6),st.integers(0,25),st.integers(0,1)),st.sampled_from((frozenset((7,10,18,20,29,50,34,49,66)),frozenset((7,)),frozenset((10,)),frozenset((50,)),frozenset((20,)),frozenset((18,29)),frozenset((34,49,66)),frozenset((66,)),frozenset((49,)))))
 def test_original_writer_and_readonly_plan_have_identical_semantics(self,days,active,previous,selected):
  a,db1,state1,now=namespace(old,days,active,previous,selected)
  b,db2,state2,_=namespace(new,days,active,previous,selected)
  expected=a['reconcile'](db1,1,1001,now)
  plan=b['pending_updates'](db2,1,1001,now)
  self.assertFalse(state2.calls)
  actual=b['reconcile'](db2,1,1001,now)
  self.assertEqual(actual,expected);self.assertEqual(state2.calls,state1.calls)
  self.assertEqual(plan['updates'],state1.calls[0][2]if state1.calls else [])
  self.assertEqual('couple_due'in plan,'couple_due'in expected)
  if 'couple_due'in plan:self.assertEqual(plan['couple_due'],expected['couple_due'])
 def test_inactive_timer_is_explicitly_cleared_only_when_its_source_is_selected(self):
  for selected in(frozenset((20,)),frozenset((29,))):
   ns,db,state,now=namespace(new,0,False,(0,0,0,0,0,0,0,0,0),selected)
   plan=ns['pending_updates'](db,1,1001,now)
   self.assertFalse(state.calls);self.assertEqual('couple_due'in plan,20 in selected)
   if 20 in selected:self.assertIsNone(plan['couple_due'])
if __name__=='__main__':unittest.main()
