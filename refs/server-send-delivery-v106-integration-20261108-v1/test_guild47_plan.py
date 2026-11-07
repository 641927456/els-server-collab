"""Oracle comparison against the accepted V106 planner, including native CP and banner."""
import test_achievement_plan as prior
import copy,types,unittest
from hypothesis import given,settings,example,strategies as st

def context(nodes,selected,power,unit,previous,banners):
 ns,db,state,now=prior.namespace(nodes,13,True,(1,2,3,4,5,2,1,2,0),selected)
 original_catalog=ns['catalog'];original_history=ns['history_counts'];old=list(db.execute('owned-existing-progress'))
 def catalog():
  values=original_catalog();values[17]=dict(unit_type=unit,conditions=[dict(type=17,id=1,parameters=dict(m_iLevel=10))]);values[59]=dict(unit_type=unit,conditions=[dict(type=59,id=1,parameters=dict(m_iCount=4))]);return values
 ns['catalog']=catalog;ns['history_counts']=lambda *args:dict(original_history(*args),**{})|{(59,0):banners}
 db.execute=lambda *args:old+[(17,1,previous,previous>=10),(59,1,0,False)]
 return ns,db,state,now

class Guild47Plan(prior.ProfilePlanTests):
 @settings(max_examples=220,deadline=None,database=None,derandomize=True)
 @example(None,1,0,0,frozenset((17,59)))
 @example((1,10),1,0,4,frozenset((17,59)))
 @example((14,2**31-1),1,9,3,frozenset((17,59,20,66)))
 @given(st.one_of(st.none(),st.tuples(st.sampled_from((1,14)),st.one_of(st.integers(0,2**31-1),st.sampled_from((0,9,10,11))))),st.sampled_from((1,14)),st.integers(0,20),st.integers(0,100),st.sampled_from((frozenset((17,)),frozenset((59,)),frozenset((17,59)),frozenset((17,59,20,66)))))
 def test_V106_CP_and_banner_keep_original_updates_receipts_and_due(self,power,unit,previous,banners,selected):
  a,db1,state1,now=context(prior.old,selected,power,unit,previous,banners)
  b,db2,state2,_=context(prior.new,selected,power,unit,previous,banners)
  expected=a['reconcile'](db1,1,1001,now,native_power=power)
  plan=b['pending_updates'](db2,1,1001,now,native_power=power)
  self.assertFalse(state2.calls)
  actual=b['reconcile'](db2,1,1001,now,native_power=power)
  self.assertEqual(actual,expected);self.assertEqual(state2.calls,state1.calls)
  self.assertEqual(plan['updates'],state1.calls[0][2]if state1.calls else [])
  if 'couple_due'in expected:self.assertEqual(plan['couple_due'],expected['couple_due'])

if __name__=='__main__':unittest.main()
