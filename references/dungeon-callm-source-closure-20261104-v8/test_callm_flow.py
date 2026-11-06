"""Fixed NPC identity is independent of a trailing multiple-return argument."""
import sys,unittest
from pathlib import Path
W=Path(__file__).resolve().parent;sys.path.insert(0,str(W/'source/tools'if(W/'source/tools').exists()else W/'candidate/tools'))
from npc_spawn_source_flow import Flow
def fixture(opcode=45,lookup='NUI_TARGET'):
 keys=['CreateNPCReq_LUA','NPC_UNIT_ID',lookup,'NUI_UNUSED','GetOwnerUID']
 code=[(12,5,1,0),(65,3,0,1),(62,6,1,0),(65,6,2,6),(12,9,1,0),(65,7,4,1),(46,7,2,0),(opcode,3,3,1),(75,0,1,0)]
 return dict(flags=10,root=0,prototypes=[dict(parameters=2,frame_size=16,upvalues='',kgc=keys,knum=[],instructions=code)]),{'NPC_UNIT_ID':{'NUI_TARGET':12585,'NUI_UNUSED':12582}}
class Callm(unittest.TestCase):
 def test_callm_includes_fixed_source_identity_before_dynamic_tail(self):
  d,e=fixture();rows=Flow(d,e).spawn_results();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['targets'],[12585]);self.assertFalse(rows[0]['unknown'])
 def test_normal_call_keeps_same_identity(self):
  d,e=fixture(46);self.assertEqual(Flow(d,e).spawn_results()[0]['targets'],[12585])
 def test_unused_enum_is_not_a_spawn_and_missing_key_has_no_alias(self):
  d,e=fixture();self.assertNotIn(12582,Flow(d,e).spawn_results()[0]['targets'])
  d,e=fixture(lookup='NUI_MISSING');row=Flow(d,e).spawn_results()[0];self.assertEqual(row['targets'],[]);self.assertTrue(row['unknown'])
if __name__=='__main__':unittest.main()
